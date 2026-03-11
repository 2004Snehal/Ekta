"""
Data Ingestion Script for Frammer AI Analytics Platform
Populates PostgreSQL database from video_list_data_final_with_dates.csv
"""

import psycopg2
import pandas as pd
from datetime import datetime
from config import DATABASE_URL

CSV_PATH = '../synthetic_data/video_list_data_final_with_dates.csv'


def connect_db():
    return psycopg2.connect(DATABASE_URL)


def parse_timestamp(ts_str):
    """Parse '10:00:40, 06, Apr, 2025' → datetime."""
    if pd.isna(ts_str):
        return None
    return datetime.strptime(ts_str.strip(), '%H:%M:%S, %d, %b, %Y')


def duration_to_secs(dur_str):
    """Parse 'HH:MM:SS' → total seconds."""
    if pd.isna(dur_str):
        return None
    parts = dur_str.strip().split(':')
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def truncate_all(conn):
    """Remove all existing data so ingestion is idempotent."""
    cursor = conn.cursor()
    print("Truncating all tables...")
    cursor.execute("""
        TRUNCATE TABLE
            fact_created_videos,
            user_channel_map,
            dim_team,
            dim_platform,
            dim_language,
            dim_output_type,
            dim_input_type,
            dim_user,
            dim_channel,
            dim_client
        CASCADE;
    """)
    conn.commit()
    print("✓ All tables truncated\n")


def populate_dimensions(conn, df):
    """Populate all dimension tables from CSV data."""
    cursor = conn.cursor()
    print("Populating dimension tables...")

    # 1. dim_client
    print("  - dim_client")
    cursor.execute("""
        INSERT INTO dim_client (client_name, plan_type, industry, region, is_active)
        VALUES ('CLIENT_1', 'enterprise', 'news', 'india', TRUE)
        RETURNING client_id;
    """)
    client_id = cursor.fetchone()[0]

    # 2. dim_channel
    print("  - dim_channel")
    channels = sorted(df['Channel'].str.strip().unique())
    for code in channels:
        cursor.execute("""
            INSERT INTO dim_channel (client_id, channel_name, channel_code, primary_language, is_active)
            VALUES (%s, %s, %s, 'en', TRUE);
        """, (client_id, f'Channel {code}', code))

    # 3. dim_user — column is 'Uploaded By' in new CSV
    print("  - dim_user")
    users = sorted(df['Uploaded By'].str.strip().unique())
    for user_name in users:
        is_bot = user_name == 'Auto Upload'
        role = 'auto' if is_bot else 'editor'
        cursor.execute("""
            INSERT INTO dim_user (client_id, user_name, role, is_bot, is_active)
            VALUES (%s, %s, %s, %s, TRUE);
        """, (client_id, user_name, role, is_bot))

    # 4. dim_input_type — from CSV 'Type' column, skip nulls
    print("  - dim_input_type")
    input_type_categories = {
        'interview': 'recorded', 'news bulletin': 'live',
        'special reports': 'recorded', 'speech': 'recorded',
        'debate': 'recorded', 'press conference': 'recorded',
        'discussion-show': 'recorded', 'sports show': 'recorded',
        'podcast': 'recorded', 'drama': 'scripted', 'in-brief': 'scripted',
    }
    input_types = sorted(df['Type'].dropna().str.strip().unique())
    for t in input_types:
        category = input_type_categories.get(t, 'recorded')
        cursor.execute("""
            INSERT INTO dim_input_type (type_name, category)
            VALUES (%s, %s);
        """, (t, category))

    # 5. dim_output_type — from CSV 'Output Type' column
    print("  - dim_output_type")
    output_types_csv = sorted(df['Output Type'].dropna().str.strip().unique())
    short_form_types = {'Key moments', 'My Key moments', 'Summary'}
    for name in output_types_csv:
        is_short = name in short_form_types
        cursor.execute("""
            INSERT INTO dim_output_type (type_name, is_short_form)
            VALUES (%s, %s);
        """, (name, is_short))

    # 6. dim_language — from CSV 'Language' column
    print("  - dim_language")
    lang_names = {
        'en': 'English', 'hi': 'Hindi', 'mix': 'Mixed',
        'es': 'Spanish', 'ar': 'Arabic', 'mr': 'Marathi',
    }
    languages = sorted(df['Language'].dropna().str.strip().unique())
    for code in languages:
        cursor.execute("""
            INSERT INTO dim_language (language_code, language_name)
            VALUES (%s, %s);
        """, (code, lang_names.get(code, code.title())))

    # 7. dim_platform — from CSV + common extras
    print("  - dim_platform")
    csv_platforms = df['Published Platform'].dropna().str.strip().unique().tolist()
    extras = ['YouTube', 'Reels', 'Shorts', 'Instagram', 'Facebook',
              'LinkedIn', 'X', 'Threads']
    all_platforms = sorted(set(csv_platforms + extras))
    platform_types = {
        'YouTube': 'video', 'Reels': 'short_form', 'Shorts': 'short_form',
        'Instagram': 'social', 'Facebook': 'social', 'Facebook-Reels': 'short_form',
        'LinkedIn': 'professional', 'X': 'social', 'Threads': 'social',
    }
    for p in all_platforms:
        cursor.execute("""
            INSERT INTO dim_platform (platform_name, platform_type)
            VALUES (%s, %s);
        """, (p, platform_types.get(p, 'social')))

    # 8. dim_team — from CSV 'Team Name' column
    print("  - dim_team")
    teams = sorted(df['Team Name'].dropna().str.strip().unique())
    for team_name in teams:
        cursor.execute("""
            INSERT INTO dim_team (client_id, team_name)
            VALUES (%s, %s);
        """, (client_id, team_name))

    conn.commit()
    print("✓ Dimension tables populated")
    return client_id


def load_id_maps(cursor, client_id):
    """Load dimension ID lookups."""
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

    cursor.execute("SELECT team_id, team_name FROM dim_team WHERE client_id = %s", (client_id,))
    team_map = {name: tid for tid, name in cursor.fetchall()}

    return user_map, channel_map, input_type_map, output_type_map, language_map, platform_map, team_map


def load_fact_created_videos(conn, df, client_id):
    """Insert into fact_created_videos — one row per CSV row."""
    cursor = conn.cursor()
    maps = load_id_maps(cursor, client_id)
    user_map, channel_map, input_type_map, output_type_map, language_map, platform_map, team_map = maps

    print("\nLoading fact_created_videos...")
    inserted = 0
    skipped = 0

    for idx, row in df.iterrows():
        user_name = row['Uploaded By'].strip()
        channel_code = row['Channel'].strip()

        user_id = user_map.get(user_name)
        channel_id = channel_map.get(channel_code)
        if not user_id or not channel_id:
            skipped += 1
            continue

        input_type_name = row['Type'].strip() if pd.notna(row['Type']) else None
        input_type_id = input_type_map.get(input_type_name) if input_type_name else None

        output_type_name = row['Output Type'].strip() if pd.notna(row['Output Type']) else None
        output_type_id = output_type_map.get(output_type_name) if output_type_name else None

        lang_code = row['Language'].strip() if pd.notna(row['Language']) else None
        language_id = language_map.get(lang_code) if lang_code else None

        team_name = row['Team Name'].strip() if pd.notna(row['Team Name']) else None
        team_id = team_map.get(team_name) if team_name else None

        headline = row['Headline'] if pd.notna(row['Headline']) else None
        source_url = row['Source'] if pd.notna(row['Source']) else None
        video_id_ext = str(row['Video ID']).strip()

        uploaded_at = parse_timestamp(row['Uploaded at'])
        uploaded_dur = duration_to_secs(row['Uploaded Duration'])
        created_dur = duration_to_secs(row['Created Duration'])
        published_dur = duration_to_secs(row['Published Duration'])

        published = row['Published'] == 'Yes'
        pub_platform = row['Published Platform'].strip() if pd.notna(row['Published Platform']) else None
        pub_url = row['Published URL'] if pd.notna(row['Published URL']) else None
        pub_platform_id = platform_map.get(pub_platform) if pub_platform else None

        cursor.execute("""
            INSERT INTO fact_created_videos (
                video_id, client_id, channel_id, user_id, team_id,
                input_type_id, output_type_id, language_id,
                headline, source_url,
                uploaded_duration_secs, created_duration_secs, published_duration_secs,
                uploaded_at,
                published_flag, published_platform_id, published_url
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
        """, (
            video_id_ext, client_id, channel_id, user_id, team_id,
            input_type_id, output_type_id, language_id,
            headline, source_url,
            uploaded_dur, created_dur, published_dur,
            uploaded_at,
            published, pub_platform_id, pub_url,
        ))
        inserted += 1

        if (idx + 1) % 3000 == 0:
            conn.commit()
            print(f"  {idx + 1}/{len(df)} rows inserted...")

    conn.commit()
    print(f"✓ Inserted {inserted} rows (skipped {skipped})")


def populate_user_channel_map(conn, df, client_id):
    """Build user-channel bridge from CSV."""
    cursor = conn.cursor()
    print("\nPopulating user_channel_map...")

    cursor.execute("SELECT user_id, user_name FROM dim_user WHERE client_id = %s", (client_id,))
    user_map = {name: uid for uid, name in cursor.fetchall()}

    cursor.execute("SELECT channel_id, channel_code FROM dim_channel WHERE client_id = %s", (client_id,))
    channel_map = {code: cid for cid, code in cursor.fetchall()}

    pairs = df[['Uploaded By', 'Channel']].drop_duplicates()
    inserted = 0
    for _, row in pairs.iterrows():
        uid = user_map.get(row['Uploaded By'].strip())
        cid = channel_map.get(row['Channel'].strip())
        if uid and cid:
            cursor.execute("""
                INSERT INTO user_channel_map (user_id, channel_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, channel_id) DO NOTHING;
            """, (uid, cid))
            inserted += 1

    conn.commit()
    print(f"✓ Inserted {inserted} user-channel mappings")


def refresh_materialized_views(conn):
    cursor = conn.cursor()
    print("\nRefreshing materialized views...")
    for view in ['mv_monthly_kpis', 'mv_channel_health', 'mv_user_performance']:
        print(f"  - {view}")
        cursor.execute(f"REFRESH MATERIALIZED VIEW {view};")
    conn.commit()
    print("✓ Materialized views refreshed")


def main():
    print("=" * 60)
    print("FRAMMER AI ANALYTICS — DATA INGESTION")
    print(f"Source: {CSV_PATH}")
    print("=" * 60)

    df = pd.read_csv(CSV_PATH)
    print(f"Loaded {len(df)} rows from CSV\n")

    conn = connect_db()

    try:
        # 0. Clear old data
        truncate_all(conn)

        # 1. Dimensions
        client_id = populate_dimensions(conn, df)

        # 2. Fact table
        load_fact_created_videos(conn, df, client_id)

        # 3. User-channel bridge
        populate_user_channel_map(conn, df, client_id)

        # 4. Materialized views
        refresh_materialized_views(conn)

        # Summary
        cursor = conn.cursor()
        tables = [
            'dim_client', 'dim_channel', 'dim_user', 'dim_input_type',
            'dim_output_type', 'dim_language', 'dim_platform', 'dim_team',
            'fact_created_videos', 'user_channel_map',
        ]
        print("\nRow counts:")
        for tbl in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
            print(f"  {tbl}: {cursor.fetchone()[0]} rows")

        print("\n" + "=" * 60)
        print("✓ DATA INGESTION COMPLETE")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
