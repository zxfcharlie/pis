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

    # --- Upstream AI providers used by the relay (/v1/*) and by image generation.
    # These are server-side secrets set by whoever deploys the container; end users
    # only ever see their own rk-... relay key, never these. ---
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_BASE_URL: str = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
    # Model used to actually render product photo-sets. Swap for whatever
    # image-generation model/provider you have access to.
    IMAGE_GEN_MODEL: str = os.getenv("IMAGE_GEN_MODEL", "gpt-image-1")

    RELAY_PUBLIC_BASE_URL: str = os.getenv("RELAY_PUBLIC_BASE_URL", "https://dailybonushub.com")


settings = Settings()

for p in (settings.DB_PATH.parent, settings.UPLOAD_DIR, settings.GENERATED_DIR):
    p.mkdir(parents=True, exist_ok=True)
