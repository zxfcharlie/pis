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
    ("generation_jobs", "batch_id", "VARCHAR(64)"),
    ("generation_jobs", "remix_template_id", "INTEGER"),
    ("relay_providers", "image_model", "VARCHAR(100) DEFAULT 'gpt-image-2'"),
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

        # Backfill: every generation_jobs row needs a non-null batch_id so the
        # history/download grouping logic never has to special-case old rows.
        # Each pre-existing job (created before "batches" existed) becomes its
        # own singleton batch. Idempotent -- only touches rows still NULL.
        if "generation_jobs" in existing_tables:
            cols = {row[1] for row in cur.execute("PRAGMA table_info(generation_jobs)").fetchall()}
            if "batch_id" in cols:
                cur.execute("UPDATE generation_jobs SET batch_id = 'legacy-' || id WHERE batch_id IS NULL")
                if cur.rowcount:
                    logger.warning("auto-migration: backfilled batch_id for %d legacy generation_jobs row(s)", cur.rowcount)

        conn.commit()
    finally:
        conn.close()


def migrate_legacy_relay_provider(db):
    """One-time data migration / convenience seed for RelayProvider, tried in
    this order:
    1. An earlier version of this app stored a single relay base_url/api_key
       directly on GlobalConfig -- carry that forward (kind="sync_edit", the
       only kind that existed back then) so admins who already configured it
       don't have to re-enter it after upgrading to the multi-provider setup.
    2. REMOTE_RELAY_BASE_URL / REMOTE_RELAY_API_KEY env vars, for a brand-new
       install that wants a provider pre-configured without touching the
       admin panel.
    No-op once at least one RelayProvider row exists, or if neither source
    has anything set."""
    from . import models  # local import to avoid a circular import at module load time
    from .config import settings

    if db.query(models.RelayProvider).count() > 0:
        return

    base_url, api_key, name = "", "", ""

    cfg = db.query(models.GlobalConfig).filter(models.GlobalConfig.id == 1).first()
    if cfg and cfg.remote_relay_base_url and cfg.remote_relay_api_key:
        base_url, api_key, name = cfg.remote_relay_base_url, cfg.remote_relay_api_key, "迁移自旧版设置"
    elif settings.REMOTE_RELAY_BASE_URL and settings.REMOTE_RELAY_API_KEY:
        base_url, api_key, name = settings.REMOTE_RELAY_BASE_URL, settings.REMOTE_RELAY_API_KEY, "来自 .env 的默认供应商"

    if not (base_url and api_key):
        return

    provider = models.RelayProvider(name=name, kind="sync_edit", base_url=base_url, api_key=api_key, is_active=True)
    db.add(provider)
    db.commit()
    logger.warning("auto-migration: created RelayProvider '%s' (%s)", name, base_url)
