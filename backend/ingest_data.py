"""
Data Ingestion Script for Frammer AI Analytics Platform
Populates PostgreSQL database from synthetic_data CSV
"""

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
from config import DATABASE_URL

# Reproducibility
np.random.seed(42)
random.seed(42)

SYNTHETIC_CSV = '../synthetic_data/video_list_data_synthetic_final.csv'


def connect_db():
    return psycopg2.connect(DATABASE_URL)


def populate_dimensions(conn, df):
    """Populate all dimension tables from synthetic CSV data."""
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

    # 2. dim_channel — extracted from CSV, strip trailing spaces
    print("  - dim_channel")
    channels = sorted(df['Channel'].str.strip().unique())
    for code in channels:
        cursor.execute("""
            INSERT INTO dim_channel (client_id, channel_name, channel_code, primary_language, is_active)
            VALUES (%s, %s, %s, 'en', TRUE)
            RETURNING channel_id;
        """, (client_id, f'Channel {code}', code))

    # 3. dim_user — extracted from CSV
    print("  - dim_user")
    users = sorted(df['Created By'].str.strip().unique())
    for user_name in users:
        is_bot = user_name == 'Auto Upload'
        role = 'auto' if is_bot else 'editor'
        cursor.execute("""
            INSERT INTO dim_user (client_id, user_name, role, is_bot, is_active)
            VALUES (%s, %s, %s, %s, TRUE);
        """, (client_id, user_name, role, is_bot))

    # 4. dim_input_type — extracted from CSV
    print("  - dim_input_type")
    input_type_categories = {
        'interview': 'recorded', 'news bulletin': 'live',
        'special reports': 'recorded', 'speech': 'recorded',
        'debate': 'recorded', 'press conference': 'recorded',
        'discussion-show': 'recorded', 'sports show': 'recorded',
        'podcast': 'recorded', 'drama': 'scripted', 'in-brief': 'scripted',
    }
    input_types = sorted(df['Type'].str.strip().unique())
    for t in input_types:
        if t == 'Unknown':
            continue
        category = input_type_categories.get(t, 'recorded')
        cursor.execute("""
            INSERT INTO dim_input_type (type_name, category)
            VALUES (%s, %s);
        """, (t, category))

    # 5. dim_output_type — hardcoded (not in CSV)
    print("  - dim_output_type")
    output_types = [
        ('Full package', 600, False),
        ('Key moments', 120, True),
        ('My Key moments', 90, True),
        ('Chapters', 300, False),
        ('Summary', 60, True),
    ]
    for name, length, is_short in output_types:
        cursor.execute("""
            INSERT INTO dim_output_type (type_name, typical_length_secs, is_short_form)
            VALUES (%s, %s, %s);
        """, (name, length, is_short))

    # 6. dim_language — hardcoded
    print("  - dim_language")
    languages = [('en', 'English'), ('hi', 'Hindi'), ('mix', 'Mixed'),
                 ('es', 'Spanish'), ('ar', 'Arabic'), ('mr', 'Marathi')]
    for code, name in languages:
        cursor.execute("""
            INSERT INTO dim_language (language_code, language_name)
            VALUES (%s, %s);
        """, (code, name))

    # 7. dim_platform — from CSV unique published platforms + extras
    print("  - dim_platform")
    csv_platforms = df['Published Platform'].dropna().str.strip().unique().tolist()
    all_platforms = list(set(csv_platforms + ['YouTube', 'Reels', 'Shorts', 'Instagram', 'Facebook', 'LinkedIn', 'X', 'Threads']))
    platform_types = {
        'YouTube': 'video', 'Reels': 'short_form', 'Shorts': 'short_form',
        'Instagram': 'social', 'Facebook': 'social', 'LinkedIn': 'professional',
        'X': 'social', 'Threads': 'social',
    }
    for p in sorted(all_platforms):
        cursor.execute("""
            INSERT INTO dim_platform (platform_name, platform_type)
            VALUES (%s, %s);
        """, (p, platform_types.get(p, 'social')))

    # 8. dim_team
    print("  - dim_team")
    cursor.execute("""
        INSERT INTO dim_team (client_id, team_name)
        VALUES (%s, 'Default Team');
    """, (client_id,))

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

    cursor.execute("SELECT team_id FROM dim_team WHERE client_id = %s LIMIT 1", (client_id,))
    team_id = cursor.fetchone()[0]

    return user_map, channel_map, input_type_map, output_type_map, language_map, platform_map, team_id


def load_fact_videos(conn, df, client_id):
    """Insert fact_videos from synthetic CSV (one row per video)."""
    cursor = conn.cursor()
    user_map, channel_map, input_type_map, _, language_map, _, team_id = load_id_maps(cursor, client_id)

    print("\nLoading fact_videos...")

    start_date = datetime(2025, 3, 1)
    end_date = datetime(2026, 2, 28)
    total_secs = int((end_date - start_date).total_seconds())

    video_id_map = {}  # external Video ID -> internal video_id
    skipped = 0

    for idx, row in df.iterrows():
        user_name = row['Created By'].strip()
        channel_code = row['Channel'].strip()
        input_type_name = row['Type'].strip() if pd.notna(row['Type']) else 'Unknown'

        user_id = user_map.get(user_name)
        channel_id = channel_map.get(channel_code)

        if not user_id or not channel_id:
            skipped += 1
            continue

        input_type_id = input_type_map.get(input_type_name)  # None for 'Unknown'

        # Weighted random language
        lang_code = np.random.choice(['en', 'hi', 'mix'], p=[0.59, 0.40, 0.01])
        language_id = language_map[lang_code]

        # Generate synthetic timestamp spread across 12 months
        uploaded_at = start_date + timedelta(seconds=random.randint(0, total_secs))
        processing_secs = random.randint(30, 300)
        processed_at = uploaded_at + timedelta(seconds=processing_secs)
        duration_secs = random.randint(120, 5400)

        headline = row['Headline'] if pd.notna(row['Headline']) else None
        source_url = row['Source'] if pd.notna(row['Source']) else None

        cursor.execute("""
            INSERT INTO fact_videos (
                client_id, channel_id, user_id, team_id, input_type_id, language_id,
                uploaded_at, processed_at, processing_secs,
                headline, source_url, duration_secs, billable_flag
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
            RETURNING video_id;
        """, (
            client_id, channel_id, user_id, team_id, input_type_id, language_id,
            uploaded_at, processed_at, processing_secs,
            headline, source_url, duration_secs
        ))
        video_id_map[row['Video ID']] = cursor.fetchone()[0]

        if (idx + 1) % 2000 == 0:
            conn.commit()
            print(f"  {idx + 1}/{len(df)} videos inserted...")

    conn.commit()
    print(f"✓ Inserted {len(video_id_map)} videos (skipped {skipped})")
    return video_id_map


def load_fact_outputs(conn, df, client_id, video_id_map):
    """Generate fact_outputs: 1-4 outputs per video, distribute publish status from CSV."""
    cursor = conn.cursor()
    _, channel_map, _, output_type_map, _, platform_map, _ = load_id_maps(cursor, client_id)

    print("\nGenerating fact_outputs...")

    output_type_names = ['Full package', 'Key moments', 'Chapters', 'My Key moments', 'Summary']
    output_type_probs = [0.298, 0.427, 0.134, 0.083, 0.058]

    outputs_created = 0

    for idx, row in df.iterrows():
        ext_vid = row['Video ID']
        internal_vid = video_id_map.get(ext_vid)
        if not internal_vid:
            continue

        channel_code = row['Channel'].strip()
        channel_id = channel_map.get(channel_code)
        if not channel_id:
            continue

        # Get video timestamps
        cursor.execute("SELECT processed_at FROM fact_videos WHERE video_id = %s", (internal_vid,))
        processed_at = cursor.fetchone()[0]

        published = row['Published'] == 'Yes'
        pub_platform = row['Published Platform'] if pd.notna(row.get('Published Platform')) else None
        pub_url = row['Published URL'] if pd.notna(row.get('Published URL')) else None

        # Each video produces 1-4 outputs
        n_outputs = np.random.choice([1, 2, 3, 4], p=[0.15, 0.35, 0.35, 0.15])
        chosen_types = np.random.choice(output_type_names, size=n_outputs, replace=False, p=output_type_probs)

        for i, otype in enumerate(chosen_types):
            otype_id = output_type_map[otype]
            created_at = processed_at + timedelta(seconds=random.randint(5, 120))

            if otype == 'Full package':
                dur = random.randint(300, 900)
            elif otype == 'Key moments':
                dur = random.randint(60, 180)
            elif otype == 'Chapters':
                dur = random.randint(180, 600)
            elif otype == 'My Key moments':
                dur = random.randint(45, 120)
            else:
                dur = random.randint(30, 90)

            # First output of a published video carries the publish info
            is_pub = published and i == 0
            pub_at = None
            pub_pid = None
            pub_u = None
            ttp = None

            if is_pub:
                pname = pub_platform if pub_platform else 'YouTube'
                pub_pid = platform_map.get(pname)
                pub_u = pub_url
                ttp = random.randint(3600, 604800)
                pub_at = created_at + timedelta(seconds=ttp)

            cursor.execute("""
                INSERT INTO fact_outputs (
                    video_id, client_id, channel_id, output_type_id,
                    created_at, duration_secs,
                    published_flag, published_at, published_platform_id,
                    published_url, time_to_publish_secs
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """, (
                internal_vid, client_id, channel_id, otype_id,
                created_at, dur,
                is_pub, pub_at, pub_pid,
                pub_u, ttp
            ))
            outputs_created += 1

        if (idx + 1) % 2000 == 0:
            conn.commit()
            print(f"  {idx + 1}/{len(df)} videos processed ({outputs_created} outputs)...")

    conn.commit()
    print(f"✓ Created {outputs_created} outputs")


def populate_user_channel_map(conn, df, client_id):
    """Build user-channel bridge from the synthetic CSV itself."""
    cursor = conn.cursor()

    print("\nPopulating user_channel_map...")

    cursor.execute("SELECT user_id, user_name FROM dim_user WHERE client_id = %s", (client_id,))
    user_map = {name: uid for uid, name in cursor.fetchall()}

    cursor.execute("SELECT channel_id, channel_code FROM dim_channel WHERE client_id = %s", (client_id,))
    channel_map = {code: cid for cid, code in cursor.fetchall()}

    pairs = df[['Created By', 'Channel']].drop_duplicates()
    inserted = 0
    for _, row in pairs.iterrows():
        uid = user_map.get(row['Created By'].strip())
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
    print(f"Source: {SYNTHETIC_CSV}")
    print("=" * 60)

    # Load CSV once
    df = pd.read_csv(SYNTHETIC_CSV)
    print(f"Loaded {len(df)} rows from CSV\n")

    conn = connect_db()

    try:
        # 1. Dimensions
        client_id = populate_dimensions(conn, df)

        # 2. Fact videos
        video_id_map = load_fact_videos(conn, df, client_id)

        # 3. Fact outputs
        load_fact_outputs(conn, df, client_id, video_id_map)

        # 4. User-channel bridge
        populate_user_channel_map(conn, df, client_id)

        # 5. Materialized views
        refresh_materialized_views(conn)

        # Summary
        cursor = conn.cursor()
        for tbl in ['dim_client', 'dim_channel', 'dim_user', 'dim_input_type',
                     'dim_output_type', 'dim_language', 'dim_platform', 'dim_team',
                     'fact_videos', 'fact_outputs', 'user_channel_map']:
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
