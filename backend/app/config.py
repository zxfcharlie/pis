import os
from pathlib import Path


class Settings:
    # --- Server ---
    PORT: int = int(os.getenv("PORT", "8411"))
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-secret-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    ALGORITHM: str = "HS256"

    # --- Storage paths (all under /data so a single volume mount persists everything) ---
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "/data"))
    DB_PATH: Path = DATA_DIR / "db" / "app.db"
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    GENERATED_DIR: Path = DATA_DIR / "generated"

    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

    # --- Business defaults (overridable by admin at runtime via /api/admin/config) ---
    DEFAULT_COST_PER_IMAGE: float = float(os.getenv("DEFAULT_COST_PER_IMAGE", "0.3"))
    DEFAULT_DAILY_QUOTA: float = float(os.getenv("DEFAULT_DAILY_QUOTA", "50"))
    IMAGE_EXPIRE_DAYS: int = int(os.getenv("IMAGE_EXPIRE_DAYS", "15"))
    CLEANUP_INTERVAL_HOURS: int = int(os.getenv("CLEANUP_INTERVAL_HOURS", "6"))

    # --- Upstream: this service does NOT hold raw OpenAI/Anthropic keys itself.
    # Instead it calls out to an existing remote relay (e.g. the user's own
    # ai-relay project at http://<server>:8511/v1) using a single rk-... key
    # issued by that relay. These env vars only seed the GlobalConfig row on
    # first boot; from then on the admin edits them from 设置 -> 中转访问 in the
    # admin panel (persisted in the DB, no redeploy needed). ---
    REMOTE_RELAY_BASE_URL: str = os.getenv("REMOTE_RELAY_BASE_URL", "")
    REMOTE_RELAY_API_KEY: str = os.getenv("REMOTE_RELAY_API_KEY", "")
    # Model used to actually render product photo-sets via the remote relay's
    # /v1/images/edits. Swap for whatever image model your relay exposes.
    IMAGE_GEN_MODEL: str = os.getenv("IMAGE_GEN_MODEL", "gpt-image-2")
    # Default chat model used if a relay chat call doesn't specify one.
    CHAT_MODEL: str = os.getenv("CHAT_MODEL", "claude-sonnet-4-6")

    RELAY_PUBLIC_BASE_URL: str = os.getenv("RELAY_PUBLIC_BASE_URL", "https://dailybonushub.com")


settings = Settings()

for p in (settings.DB_PATH.parent, settings.UPLOAD_DIR, settings.GENERATED_DIR):
    p.mkdir(parents=True, exist_ok=True)
