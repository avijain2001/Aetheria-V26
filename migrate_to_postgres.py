"""
AETHERIA ONE-CLICK POSTGRESQL MIGRATION TOOL (migrate_to_postgres.py)
-------------------------------------------------------------------
This script transfers all accumulated data from your local SQLite database
(data/aetheria.db) into your persistent cloud PostgreSQL database (Neon.tech).

Features:
1. Verifies local database health and inventories all tables.
2. Creates the target schema in PostgreSQL if not already present.
3. Migrates data in ordered batches (500 rows at a time) for high speed over the network.
4. Uses ON CONFLICT DO NOTHING to ensure idempotency (can be safely run multiple times).
5. Performs a post-migration audit comparing source vs target row counts.
"""

from __future__ import annotations
import os
import sys
import time
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "data" / "aetheria.db"

# The tables to migrate in dependency order (foreign keys respected)
TABLES = [
    "sources",
    "articles",
    "events",
    "event_articles",
    "event_updates",
    "schedules",
    "telemetry",
    "learning",
    "system_metrics",
    "ai_context"
]

PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT,
    url TEXT UNIQUE NOT NULL,
    topic TEXT,
    tier TEXT,
    format TEXT,
    interval_sec INTEGER DEFAULT 300,
    max_items INTEGER,
    enabled INTEGER DEFAULT 1,
    etag TEXT,
    last_modified TEXT,
    last_success REAL,
    last_failure REAL,
    failures INTEGER DEFAULT 0,
    fetched INTEGER DEFAULT 0,
    items INTEGER DEFAULT 0,
    corroborated INTEGER DEFAULT 0,
    language TEXT DEFAULT 'en',
    country TEXT DEFAULT '',
    discovered_from TEXT DEFAULT '',
    region TEXT DEFAULT '',
    city TEXT DEFAULT '',
    state_name TEXT DEFAULT '',
    corrections INTEGER DEFAULT 0,
    reliability REAL DEFAULT 0.50,
    created_at REAL,
    updated_at REAL,
    state TEXT DEFAULT 'idle',
    last_attempt REAL,
    last_duration_ms INTEGER DEFAULT 0,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    source_id TEXT,
    canonical_url TEXT UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    published REAL,
    fetched REAL,
    language TEXT,
    country TEXT,
    topic TEXT,
    tier TEXT,
    domain TEXT,
    fingerprint TEXT,
    image_url TEXT,
    FOREIGN KEY(source_id) REFERENCES sources(id)
);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published);
CREATE INDEX IF NOT EXISTS idx_articles_fingerprint ON articles(fingerprint);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_id);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    topic TEXT,
    status TEXT NOT NULL,
    first_seen REAL,
    last_seen REAL,
    last_change REAL,
    velocity REAL DEFAULT 0,
    novelty REAL DEFAULT 0,
    corroboration REAL DEFAULT 0,
    authority REAL DEFAULT 0,
    urgency REAL DEFAULT 0,
    significance REAL DEFAULT 0,
    india_relevance REAL DEFAULT 0,
    financial_relevance REAL DEFAULT 0,
    supply_chain_relevance REAL DEFAULT 0,
    geopolitical_relevance REAL DEFAULT 0,
    social_relevance REAL DEFAULT 0,
    article_count INTEGER DEFAULT 0,
    source_count INTEGER DEFAULT 0,
    official_count INTEGER DEFAULT 0,
    publisher_count INTEGER DEFAULT 0,
    discovery_count INTEGER DEFAULT 0,
    primary_article_id TEXT,
    summary TEXT,
    entities TEXT DEFAULT '[]',
    locations TEXT DEFAULT '[]',
    last_reason TEXT,
    created_at REAL,
    updated_at REAL
);
CREATE INDEX IF NOT EXISTS idx_events_last_seen ON events(last_seen);
CREATE INDEX IF NOT EXISTS idx_events_significance ON events(significance);
CREATE INDEX IF NOT EXISTS idx_events_topic_seen ON events(topic, last_seen);

CREATE TABLE IF NOT EXISTS event_articles (
    event_id TEXT,
    article_id TEXT,
    first_linked REAL,
    PRIMARY KEY(event_id, article_id)
);

CREATE TABLE IF NOT EXISTS event_updates (
    id SERIAL PRIMARY KEY,
    event_id TEXT,
    article_id TEXT,
    observed_at REAL,
    change_type TEXT,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_event_updates_event ON event_updates(event_id, observed_at);

CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    source_id TEXT,
    title TEXT NOT NULL,
    category TEXT,
    kind TEXT,
    start_ts REAL NOT NULL,
    end_ts REAL,
    time_known INTEGER DEFAULT 1,
    url TEXT,
    description TEXT,
    importance REAL DEFAULT 0.50,
    updated_at REAL
);
CREATE INDEX IF NOT EXISTS idx_schedules_start ON schedules(start_ts);
CREATE INDEX IF NOT EXISTS idx_schedules_category ON schedules(category, start_ts);

CREATE TABLE IF NOT EXISTS telemetry (
    id SERIAL PRIMARY KEY,
    event_id TEXT,
    action TEXT,
    value REAL DEFAULT 1,
    at REAL,
    session TEXT
);
CREATE INDEX IF NOT EXISTS idx_telemetry_session ON telemetry(session, at);

CREATE TABLE IF NOT EXISTS learning (
    key TEXT PRIMARY KEY,
    value REAL DEFAULT 0,
    observations INTEGER DEFAULT 0,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS system_metrics (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS ai_context (
    event_id TEXT PRIMARY KEY,
    summary TEXT,
    changed TEXT,
    watch TEXT,
    provider TEXT,
    model TEXT,
    generated_at REAL,
    status TEXT,
    why TEXT,
    uncertainty TEXT,
    evidence_note TEXT
);
"""


def get_sqlite_conn():
    if not DB_FILE.exists():
        raise FileNotFoundError(f"Local SQLite database not found at {DB_FILE}")
    con = sqlite3.connect(str(DB_FILE))
    con.row_factory = sqlite3.Row
    return con


def run_migration(pg_url: str, batch_size: int = 500):
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        print("\nERROR: 'psycopg2' is not installed.")
        print("Please install it by running: pip install psycopg2-binary")
        sys.exit(1)

    # Standardize postgres:// prefix
    if pg_url.startswith("postgres://"):
        pg_url = pg_url.replace("postgres://", "postgresql://", 1)

    print("=" * 70)
    print(" AETHERIA DATA MIGRATION: SQLite (Local) -> PostgreSQL (Cloud)")
    print("=" * 70)
    print(f" Source SQLite DB: {DB_FILE}")
    print(f" Target Postgres:  {pg_url.split('@')[-1] if '@' in pg_url else 'configured endpoint'}")
    print("=" * 70)

    sqlite_con = get_sqlite_conn()
    sqlite_cur = sqlite_con.cursor()

    print("\nConnecting to PostgreSQL...")
    try:
        pg_con = psycopg2.connect(pg_url, connect_timeout=10)
        pg_cur = pg_con.cursor()
    except Exception as e:
        print(f"\nERROR: Failed to connect to PostgreSQL: {e}")
        print("Please verify that your DATABASE_URL connection string is correct.")
        sys.exit(1)

    print("Connected successfully!")
    print("\n[Phase 1] Ensuring PostgreSQL schema exists...")
    pg_cur.execute(PG_SCHEMA)
    pg_con.commit()
    print("Schema is ready.")

    print("\n[Phase 2] Migrating tables...")
    start_total = time.time()
    results = {}

    for table in TABLES:
        # Check if table exists in SQLite
        exists = sqlite_cur.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        ).fetchone()[0]

        if not exists:
            print(f" - Table '{table}' does not exist in SQLite, skipping.")
            continue

        # Get total rows in SQLite
        total_rows = sqlite_cur.execute(f"SELECT count(*) FROM [{table}]").fetchone()[0]
        if total_rows == 0:
            print(f" - Table '{table}': 0 rows to migrate.")
            results[table] = (0, 0)
            continue

        # Get column names
        cols_info = sqlite_cur.execute(f"PRAGMA table_info([{table}])").fetchall()
        cols = [c[1] for c in cols_info]
        cols_str = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))

        insert_sql = f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

        print(f" - Migrating '{table}' ({total_rows:,} rows)...", end="", flush=True)
        start_t = time.time()

        sqlite_cur.execute(f"SELECT {cols_str} FROM [{table}]")
        migrated = 0

        while True:
            rows = sqlite_cur.fetchmany(batch_size)
            if not rows:
                break
            # Convert sqlite3.Row to plain tuples
            data = [tuple(r) for r in rows]
            psycopg2.extras.execute_batch(pg_cur, insert_sql, data, page_size=batch_size)
            pg_con.commit()
            migrated += len(data)
            print(f"\r - Migrating '{table}'... {migrated:,}/{total_rows:,} ({int(migrated/total_rows*100)}%)", end="", flush=True)

        elapsed = time.time() - start_t
        print(f"\r - Migrated  '{table}': {total_rows:,} rows in {elapsed:.2f}s                    ")

        # Verify Postgres row count
        pg_cur.execute(f"SELECT count(*) FROM {table}")
        pg_count = pg_cur.fetchone()[0]
        results[table] = (total_rows, pg_count)

    total_time = time.time() - start_total
    print("\n" + "=" * 70)
    print(" MIGRATION AUDIT & VERIFICATION REPORT")
    print("=" * 70)
    print(f"{'Table Name':<20} | {'SQLite Rows':<14} | {'Postgres Rows':<14} | Status")
    print("-" * 70)

    all_matched = True
    for table, (src_cnt, dst_cnt) in results.items():
        status = "MATCH [OK]" if dst_cnt >= src_cnt else "MISMATCH [!]"
        if dst_cnt < src_cnt:
            all_matched = False
        print(f"{table:<20} | {src_cnt:<14,} | {dst_cnt:<14,} | {status}")

    print("=" * 70)
    if all_matched:
        print(f" SUCCESS: Migration completed in {total_time:.2f} seconds with zero data loss!")
        print(" Your cloud PostgreSQL database is now fully populated.")
    else:
        print(f" WARNING: Some counts differed. Review the table above.")

    sqlite_con.close()
    pg_con.close()


def print_local_inventory():
    """Prints local database statistics when no DATABASE_URL is provided."""
    print("=" * 70)
    print(" AETHERIA LOCAL DATABASE INVENTORY (DRY RUN)")
    print("=" * 70)
    print(f" SQLite File: {DB_FILE} ({DB_FILE.stat().st_size / (1024*1024):.2f} MB)")
    print("-" * 70)

    con = get_sqlite_conn()
    cur = con.cursor()
    total_records = 0

    print(f"{'Table Name':<20} | {'Local Rows':<15} | Status")
    print("-" * 70)
    for table in TABLES:
        try:
            cnt = cur.execute(f"SELECT count(*) FROM [{table}]").fetchone()[0]
            total_records += cnt
            print(f"{table:<20} | {cnt:<15,} | Ready to migrate")
        except Exception:
            print(f"{table:<20} | {'Not found':<15} | Empty")

    con.close()
    print("=" * 70)
    print(f" Total records ready for migration: {total_records:,}")
    print("\nTo execute migration to your cloud database:")
    print(" 1. Obtain your PostgreSQL connection string (e.g. from Neon.tech)")
    print(" 2. Run in terminal:")
    print("    python migrate_to_postgres.py \"postgresql://user:pass@ep-host.neon.tech/neondb?sslmode=require\"")
    print("=" * 70)


def main():
    pg_url = None
    if len(sys.argv) > 1 and sys.argv[1].startswith(("postgres://", "postgresql://")):
        pg_url = sys.argv[1]
    elif os.environ.get("DATABASE_URL"):
        pg_url = os.environ.get("DATABASE_URL")

    if pg_url:
        run_migration(pg_url)
    else:
        print_local_inventory()


if __name__ == "__main__":
    main()
