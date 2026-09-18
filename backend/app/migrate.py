"""
Extremely lightweight, dependency-free SQLite "migration": this project has
no Alembic setup, and SQLAlchemy's Base.metadata.create_all() only creates
tables that don't exist yet -- it never adds new columns to a table that's
already there. So every time we add a column to an existing model (like
User.is_approved, GlobalConfig.remote_relay_base_url/api_key), anyone
upgrading in place on a persisted ./data volume gets `no such column`
errors (which surface as 500s) until that column is added by hand.

This runs once at startup, after create_all(), and just ADD COLUMNs that
are missing. It's a no-op on a fresh database (create_all already created
the right schema) and a no-op on an already-migrated one.
"""
import logging
import sqlite3

from .config import settings

logger = logging.getLogger("migrate")

# (table, column, ddl_type_and_default)
REQUIRED_COLUMNS = [
    ("users", "is_approved", "BOOLEAN DEFAULT 1"),
    ("global_config", "remote_relay_base_url", "TEXT DEFAULT ''"),
    ("global_config", "remote_relay_api_key", "TEXT DEFAULT ''"),
]


def run_sqlite_migrations():
    if not settings.DATABASE_URL.startswith("sqlite"):
        logger.info("non-sqlite DATABASE_URL, skipping built-in auto-migration (run your own)")
        return
    if not settings.DB_PATH.exists():
        return  # brand-new db: create_all() already produced the up-to-date schema

    conn = sqlite3.connect(str(settings.DB_PATH))
    try:
        cur = conn.cursor()
        existing_tables = {
            row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for table, column, ddl in REQUIRED_COLUMNS:
            if table not in existing_tables:
                continue  # table itself doesn't exist yet -> create_all() will make it fresh/correct
            cols = {row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}
            if column not in cols:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
                logger.warning("auto-migration: added missing column %s.%s", table, column)
        conn.commit()
    finally:
        conn.close()
