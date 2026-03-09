"""
Data Ingestion Script for Frammer AI Analytics Platform
Populates PostgreSQL database from CLIENT_1 real data CSV files
"""

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
from config import DATABASE_URL

# Set random seed for reproducibility
np.random.seed(42)
random.seed(42)

def connect_db():
    """Create database connection."""
    return psycopg2.connect(DATABASE_URL)

def populate_dimension_tables(conn):
    """Populate all dimension tables with reference data."""
    cursor = conn.cursor()
    
    print("Populating dimension tables...")
    
    # 1. dim_client - CLIENT_1
    print("  - dim_client")
    cursor.execute("""
        INSERT INTO dim_client (client_name, plan_type, industry, region, is_active)
        VALUES ('CLIENT_1', 'enterprise', 'news', 'india', TRUE)
        RETURNING client_id;
    """)
    client_id = cursor.fetchone()[0]
    
    # 2. dim_input_type - from real data
    print("  - dim_input_type")
    input_types = [
        ('interview', 'recorded', 11.25),
        ('news bulletin', 'live', 10.05),
        ('special reports', 'recorded', 10.57),
        ('speech', 'recorded', 10.73),
        ('debate', 'recorded', 13.17),
        ('press conference', 'recorded', 10.95),
        ('discussion-show', 'recorded', 14.57),
        ('sports show', 'recorded', 10.25),
        ('podcast', 'recorded', 30.0),
        ('drama', 'scripted', 25.0),
        ('in-brief', 'scripted', 3.0),
    ]
    for type_name, category, avg_duration in input_types:
        cursor.execute("""
            INSERT INTO dim_input_type (type_name, category, avg_duration_mins)
            VALUES (%s, %s, %s);
        """, (type_name, category, avg_duration))
    
    # 3. dim_output_type - from real data
    print("  - dim_output_type")
    output_types = [
        ('Full package', 600, False),
        ('Key moments', 120, True),
        ('My Key moments', 90, True),
        ('Chapters', 300, False),
        ('Summary', 60, True),
    ]
    for type_name, typical_length, is_short in output_types:
        cursor.execute("""
            INSERT INTO dim_output_type (type_name, typical_length_secs, is_short_form)
            VALUES (%s, %s, %s);
        """, (type_name, typical_length, is_short))
    
    # 4. dim_language - from real data
    print("  - dim_language")
    languages = [
        ('en', 'English'),
        ('hi', 'Hindi'),
        ('mix', 'Mixed'),
        ('es', 'Spanish'),
        ('ar', 'Arabic'),
        ('mr', 'Marathi'),
    ]
    for code, name in languages:
        cursor.execute("""
            INSERT INTO dim_language (language_code, language_name)
            VALUES (%s, %s);
        """, (code, name))
    
    # 5. dim_platform - from real data
    print("  - dim_platform")
    platforms = [
        ('YouTube', 'video'),
        ('Reels', 'short_form'),
        ('Shorts', 'short_form'),
        ('Instagram', 'social'),
        ('Facebook', 'social'),
        ('LinkedIn', 'professional'),
        ('X', 'social'),
        ('Threads', 'social'),
    ]
    for pname, ptype in platforms:
        cursor.execute("""
            INSERT INTO dim_platform (platform_name, platform_type)
            VALUES (%s, %s);
        """, (pname, ptype))
    
    # 6. dim_channel - from combined data by channel
    print("  - dim_channel")
    df_channel = pd.read_csv('../org_data/CLIENT 1 combined_data(2025-3-1-2026-2-28).csv')
    
    for _, row in df_channel.iterrows():
        channel_code = row['Channel']
        cursor.execute("""
            INSERT INTO dim_channel (client_id, channel_name, channel_code, primary_language, is_active)
            VALUES (%s, %s, %s, %s, TRUE);
        """, (client_id, f'CLIENT_1_Channel_{channel_code}', channel_code, 'en'))
    
    # 7. dim_user - from combined data by user
    print("  - dim_user")
    df_user = pd.read_csv('../org_data/combined_data(2025-3-1-2026-2-28) by user.csv')
    
    for _, row in df_user.iterrows():
        user_name = row['User']
        is_bot = user_name == 'Auto Upload'
        role = 'auto' if is_bot else 'editor'
        
        cursor.execute("""
            INSERT INTO dim_user (client_id, user_name, role, is_bot, is_active)
            VALUES (%s, %s, %s, %s, TRUE);
        """, (client_id, user_name, role, is_bot))
    
    # 8. dim_team
    print("  - dim_team")
    cursor.execute("""
        INSERT INTO dim_team (client_id, team_name)
        VALUES (%s, 'Default Team');
    """, (client_id,))
    
    conn.commit()
    print("✓ Dimension tables populated")
    return client_id

def load_video_data(conn, client_id):
    """
    Load fact_videos and fact_outputs from video_list_data_obfuscated.csv
    This CSV actually contains OUTPUT-level data, not video-level data.
    We need to deduplicate by Video ID to create fact_videos.
    """
    cursor = conn.cursor()
    
    print("\nLoading video list data...")
    df = pd.read_csv('../org_data/video_list_data_obfuscated.csv')
    print(f"  Total rows: {len(df)}")
    
    # Get dimension ID mappings
    cursor.execute("SELECT user_id, user_name FROM dim_user WHERE client_id = %s", (client_id,))
    user_map = {name: uid for uid, name in cursor.fetchall()}
    
    cursor.execute("SELECT channel_id, channel_code FROM dim_channel WHERE client_id = %s", (client_id,))
    channel_map = {code: cid for cid, code in cursor.fetchall()}
    
    cursor.execute("SELECT input_type_id, type_name FROM dim_input_type")
    input_type_map = {name: tid for tid, name in cursor.fetchall()}
    
    cursor.execute("SELECT output_type_id, type_name FROM dim_output_type")
    output_type_map = {name: tid for tid, name in cursor.fetchall()}
    
    cursor.execute("SELECT language_id, language_code FROM dim_language")
    language_map = {code: lid for lid, code in cursor.fetchall()}
    
    cursor.execute("SELECT platform_id, platform_name FROM dim_platform")
    platform_map = {name: pid for pid, name in cursor.fetchall()}
    
    cursor.execute("SELECT team_id FROM dim_team WHERE client_id = %s LIMIT 1", (client_id,))
    default_team_id = cursor.fetchone()[0]
    
    # Load channel-user mapping to assign channels to videos
    df_channel_user = pd.read_csv('../org_data/combined_data(2025-3-1-2026-2-28) by channel and user.csv')
    
    # Create user -> primary channel mapping
    user_channel_map = {}
    for _, row in df_channel_user.iterrows():
        user = row['User']
        channel = row['Channel']
        if user not in user_channel_map:
            user_channel_map[user] = channel
    
    # Generate upload timestamps distributed across 12 months (Mar 2025 - Feb 2026)
    start_date = datetime(2025, 3, 1)
    end_date = datetime(2026, 2, 28)
    
    # Group by Video ID to create fact_videos (deduplicate)
    print("\nCreating fact_videos...")
    video_groups = df.groupby('Video ID')
    
    video_id_map = {}  # maps external Video ID -> internal video_id
    
    for ext_video_id, group in video_groups:
        # Take first row for video-level attributes
        first_row = group.iloc[0]
        
        user_name = first_row['Uploaded By']
        input_type_name = first_row['Type'] if pd.notna(first_row['Type']) else 'Unknown'
        
        # Get user_id
        user_id = user_map.get(user_name)
        if not user_id:
            continue
        
        # Get channel from user mapping
        channel_code = user_channel_map.get(user_name, 'A')  # default to A
        channel_id = channel_map.get(channel_code, list(channel_map.values())[0])
        
        # Get input_type_id
        input_type_id = input_type_map.get(input_type_name)
        
        # Assign random language (weighted by real distribution)
        language_code = np.random.choice(['en', 'hi', 'mix'], p=[0.59, 0.40, 0.01])
        language_id = language_map[language_code]
        
        # Generate upload timestamp
        uploaded_at = start_date + timedelta(
            seconds=random.randint(0, int((end_date - start_date).total_seconds()))
        )
        
        # Random processing time (30 sec - 5 min)
        processing_secs = random.randint(30, 300)
        processed_at = uploaded_at + timedelta(seconds=processing_secs)
        
        # Random duration (2 min - 90 min)
        duration_secs = random.randint(120, 5400)
        
        # Insert into fact_videos
        cursor.execute("""
            INSERT INTO fact_videos (
                client_id, channel_id, user_id, team_id, input_type_id, language_id,
                uploaded_at, processed_at, processing_secs,
                headline, source_url, duration_secs, billable_flag
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
            RETURNING video_id;
        """, (
            client_id, channel_id, user_id, default_team_id, input_type_id, language_id,
            uploaded_at, processed_at, processing_secs,
            first_row['Headline'], first_row['Source'], duration_secs
        ))
        
        internal_video_id = cursor.fetchone()[0]
        video_id_map[ext_video_id] = internal_video_id
    
    print(f"✓ Created {len(video_id_map)} videos in fact_videos")
    
    # Create fact_outputs - one per row in CSV
    print("\nCreating fact_outputs...")
    
    # Need to infer output type from the data
    # Since the CSV doesn't have output_type column, we'll distribute based on real ratios:
    # Full package: 29.8%, Key moments: 42.7%, Chapters: 13.4%, My Key moments: 8.3%, Summary: 5.6%
    output_type_names = ['Full package', 'Key moments', 'Chapters', 'My Key moments', 'Summary']
    output_type_probs = [0.298, 0.427, 0.134, 0.083, 0.056]
    
    outputs_created = 0
    
    for _, row in df.iterrows():
        ext_video_id = row['Video ID']
        internal_video_id = video_id_map.get(ext_video_id)
        
        if not internal_video_id:
            continue
        
        # Randomly assign output type
        output_type_name = np.random.choice(output_type_names, p=output_type_probs)
        output_type_id = output_type_map[output_type_name]
        
        # Get video's upload time
        cursor.execute("SELECT uploaded_at, processed_at FROM fact_videos WHERE video_id = %s", (internal_video_id,))
        uploaded_at, processed_at = cursor.fetchone()
        
        # Output created shortly after processing
        created_at = processed_at + timedelta(seconds=random.randint(5, 60))
        
        # Random output duration based on type
        if output_type_name == 'Full package':
            duration_secs = random.randint(300, 900)
        elif output_type_name == 'Key moments':
            duration_secs = random.randint(60, 180)
        elif output_type_name == 'Chapters':
            duration_secs = random.randint(180, 600)
        elif output_type_name == 'My Key moments':
            duration_secs = random.randint(45, 120)
        else:  # Summary
            duration_secs = random.randint(30, 90)
        
        # Published status
        published_flag = row['Published'] == 'Yes'
        published_at = None
        published_platform_id = None
        published_url = None
        time_to_publish_secs = None
        
        if published_flag:
            platform_name = row['Published Platform'] if pd.notna(row['Published Platform']) else 'YouTube'
            published_platform_id = platform_map.get(platform_name)
            published_url = row['Published URL'] if pd.notna(row['Published URL']) else None
            
            # Time to publish: random between 1 hour and 7 days
            time_to_publish_secs = random.randint(3600, 604800)
            published_at = created_at + timedelta(seconds=time_to_publish_secs)
        
        # Get channel_id from video
        cursor.execute("SELECT channel_id FROM fact_videos WHERE video_id = %s", (internal_video_id,))
        channel_id = cursor.fetchone()[0]
        
        # Insert into fact_outputs
        cursor.execute("""
            INSERT INTO fact_outputs (
                video_id, client_id, channel_id, output_type_id,
                created_at, duration_secs,
                published_flag, published_at, published_platform_id, 
                published_url, time_to_publish_secs
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (
            internal_video_id, client_id, channel_id, output_type_id,
            created_at, duration_secs,
            published_flag, published_at, published_platform_id,
            published_url, time_to_publish_secs
        ))
        
        outputs_created += 1
        
        if outputs_created % 1000 == 0:
            print(f"  Processed {outputs_created} outputs...")
            conn.commit()
    
    conn.commit()
    print(f"✓ Created {outputs_created} outputs in fact_outputs")

def populate_user_channel_map(conn, client_id):
    """Populate bridge table from channel-user data."""
    cursor = conn.cursor()
    
    print("\nPopulating user_channel_map...")
    
    df = pd.read_csv('../org_data/combined_data(2025-3-1-2026-2-28) by channel and user.csv')
    
    # Get mappings
    cursor.execute("SELECT user_id, user_name FROM dim_user WHERE client_id = %s", (client_id,))
    user_map = {name: uid for uid, name in cursor.fetchall()}
    
    cursor.execute("SELECT channel_id, channel_code FROM dim_channel WHERE client_id = %s", (client_id,))
    channel_map = {code: cid for cid, code in cursor.fetchall()}
    
    for _, row in df.iterrows():
        user_name = row['User']
        channel_code = row['Channel']
        
        user_id = user_map.get(user_name)
        channel_id = channel_map.get(channel_code)
        
        if user_id and channel_id:
            cursor.execute("""
                INSERT INTO user_channel_map (user_id, channel_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, channel_id) DO NOTHING;
            """, (user_id, channel_id))
    
    conn.commit()
    print("✓ user_channel_map populated")

def refresh_materialized_views(conn):
    """Refresh all materialized views."""
    cursor = conn.cursor()
    
    print("\nRefreshing materialized views...")
    
    views = ['mv_monthly_kpis', 'mv_channel_health', 'mv_user_performance']
    
    for view in views:
        print(f"  - {view}")
        cursor.execute(f"REFRESH MATERIALIZED VIEW {view};")
    
    conn.commit()
    print("✓ Materialized views refreshed")

def main():
    """Main ingestion pipeline."""
    print("=" * 60)
    print("FRAMMER AI ANALYTICS - DATA INGESTION")
    print("=" * 60)
    
    conn = connect_db()
    
    try:
        # Step 1: Populate dimensions
        client_id = populate_dimension_tables(conn)
        
        # Step 2: Load video and output data
        load_video_data(conn, client_id)
        
        # Step 3: Populate user-channel bridge
        populate_user_channel_map(conn, client_id)
        
        # Step 4: Refresh materialized views
        refresh_materialized_views(conn)
        
        print("\n" + "=" * 60)
        print("✓ DATA INGESTION COMPLETE")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Error during ingestion: {e}")
        conn.rollback()
        raise
    
    finally:
        conn.close()

if __name__ == "__main__":
    main()
