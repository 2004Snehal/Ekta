import pandas as pd
import psycopg2
from config import DATABASE_URL
from datetime import datetime, timedelta
import random

def populate_dimensions():
    """Populate dimension tables from org_data CSV files."""
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    try:
        print("=" * 60)
        print("POPULATING DIMENSION TABLES")
        print("=" * 60)
        
        # 1. CLIENT
        print("\n1. Populating dim_client...")
        cursor.execute("""
            INSERT INTO dim_client (client_name, plan_type, industry, region)
            VALUES ('CLIENT_1', 'enterprise', 'news', 'india')
            ON CONFLICT DO NOTHING
            RETURNING client_id;
        """)
        result = cursor.fetchone()
        client_id = result[0] if result else 1
        print(f"   ✓ Created client: CLIENT_1 (id={client_id})")
        
        # 2. CHANNELS
        print("\n2. Populating dim_channel...")
        channel_df = pd.read_csv('../org_data/CLIENT 1 combined_data(2025-3-1-2026-2-28).csv')
        channels = {}
        for _, row in channel_df.iterrows():
            channel_code = row['Channel']
            cursor.execute("""
                INSERT INTO dim_channel (client_id, channel_name, channel_code, primary_language)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING channel_id;
            """, (client_id, f'Channel {channel_code}', channel_code, 'en'))
            conn.commit()
            cursor.execute("SELECT channel_id FROM dim_channel WHERE channel_code = %s AND client_id = %s", 
                          (channel_code, client_id))
            channels[channel_code] = cursor.fetchone()[0]
            print(f"   ✓ Created channel: {channel_code} (id={channels[channel_code]})")
        
        # 3. USERS
        print("\n3. Populating dim_user...")
        user_df = pd.read_csv('../org_data/combined_data(2025-3-1-2026-2-28) by user.csv')
        users = {}
        for user_name in user_df['User'].unique():
            is_bot = user_name == 'Auto Upload'
            role = 'auto' if is_bot else 'editor'
            cursor.execute("""
                INSERT INTO dim_user (client_id, user_name, role, is_bot)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING user_id;
            """, (client_id, user_name, role, is_bot))
            conn.commit()
            cursor.execute("SELECT user_id FROM dim_user WHERE user_name = %s AND client_id = %s", 
                          (user_name, client_id))
            users[user_name] = cursor.fetchone()[0]
            print(f"   ✓ Created user: {user_name} (id={users[user_name]})")
        
        # 4. INPUT TYPES
        print("\n4. Populating dim_input_type...")
        input_type_df = pd.read_csv('../org_data/combined_data(2025-3-1-2026-2-28) by input type.csv')
        input_types = {}
        for _, row in input_type_df.iterrows():
            type_name = row['Input Type']
            if type_name == 'Unknown':
                continue
            cursor.execute("""
                INSERT INTO dim_input_type (type_name)
                VALUES (%s)
                ON CONFLICT (type_name) DO NOTHING
                RETURNING input_type_id;
            """, (type_name,))
            conn.commit()
            cursor.execute("SELECT input_type_id FROM dim_input_type WHERE type_name = %s", (type_name,))
            input_types[type_name] = cursor.fetchone()[0]
            print(f"   ✓ Created input type: {type_name} (id={input_types[type_name]})")
        
        # 5. OUTPUT TYPES
        print("\n5. Populating dim_output_type...")
        output_type_df = pd.read_csv('../org_data/combined_data(2025-3-1-2026-2-28) by output type.csv')
        output_types = {}
        for _, row in output_type_df.iterrows():
            type_name = row['Output Type']
            is_short = type_name in ['Key moments', 'My Key moments']
            cursor.execute("""
                INSERT INTO dim_output_type (type_name, is_short_form)
                VALUES (%s, %s)
                ON CONFLICT (type_name) DO NOTHING
                RETURNING output_type_id;
            """, (type_name, is_short))
            conn.commit()
            cursor.execute("SELECT output_type_id FROM dim_output_type WHERE type_name = %s", (type_name,))
            output_types[type_name] = cursor.fetchone()[0]
            print(f"   ✓ Created output type: {type_name} (id={output_types[type_name]})")
        
        # 6. LANGUAGES
        print("\n6. Populating dim_language...")
        language_df = pd.read_csv('../org_data/combined_data(2025-3-1-2026-2-28) by language.csv')
        languages = {}
        lang_names = {
            'en': 'English',
            'hi': 'Hindi',
            'mix': 'Mixed',
            'es': 'Spanish',
            'ar': 'Arabic',
            'mr': 'Marathi'
        }
        for _, row in language_df.iterrows():
            lang_code = row['Language']
            lang_name = lang_names.get(lang_code, lang_code.upper())
            cursor.execute("""
                INSERT INTO dim_language (language_code, language_name)
                VALUES (%s, %s)
                ON CONFLICT (language_code) DO NOTHING
                RETURNING language_id;
            """, (lang_code, lang_name))
            conn.commit()
            cursor.execute("SELECT language_id FROM dim_language WHERE language_code = %s", (lang_code,))
            languages[lang_code] = cursor.fetchone()[0]
            print(f"   ✓ Created language: {lang_name} ({lang_code}) (id={languages[lang_code]})")
        
        # 7. PLATFORMS
        print("\n7. Populating dim_platform...")
        platforms = {}
        platform_list = [
            ('YouTube', 'video'),
            ('Reels', 'short_form'),
            ('Shorts', 'short_form'),
            ('Instagram', 'social'),
            ('Facebook', 'social'),
            ('LinkedIn', 'social'),
            ('X', 'social'),
            ('Threads', 'social')
        ]
        for platform_name, platform_type in platform_list:
            cursor.execute("""
                INSERT INTO dim_platform (platform_name, platform_type)
                VALUES (%s, %s)
                ON CONFLICT (platform_name) DO NOTHING
                RETURNING platform_id;
            """, (platform_name, platform_type))
            conn.commit()
            cursor.execute("SELECT platform_id FROM dim_platform WHERE platform_name = %s", (platform_name,))
            platforms[platform_name] = cursor.fetchone()[0]
            print(f"   ✓ Created platform: {platform_name} (id={platforms[platform_name]})")
        
        conn.commit()
        
        print("\n" + "=" * 60)
        print("DIMENSION TABLES POPULATED SUCCESSFULLY")
        print("=" * 60)
        
        return {
            'client_id': client_id,
            'channels': channels,
            'users': users,
            'input_types': input_types,
            'output_types': output_types,
            'languages': languages,
            'platforms': platforms
        }
        
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def populate_user_channel_map(mappings):
    """Create user-channel relationships from aggregated data."""
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    try:
        print("\n8. Populating user_channel_map...")
        channel_user_df = pd.read_csv('../org_data/combined_data(2025-3-1-2026-2-28) by channel and user.csv')
        
        for _, row in channel_user_df.iterrows():
            channel_code = row['Channel']
            user_name = row['User']
            
            channel_id = mappings['channels'].get(channel_code)
            user_id = mappings['users'].get(user_name)
            
            if channel_id and user_id:
                cursor.execute("""
                    INSERT INTO user_channel_map (user_id, channel_id, is_primary)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, channel_id) DO NOTHING;
                """, (user_id, channel_id, False))
        
        conn.commit()
        print(f"   ✓ Created {len(channel_user_df)} user-channel mappings")
        
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    print("\nStarting data ingestion from org_data...\n")
    mappings = populate_dimensions()
    populate_user_channel_map(mappings)
    print("\n✓ All dimension tables populated successfully!\n")
