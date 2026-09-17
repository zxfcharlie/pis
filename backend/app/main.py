import logging
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models
from .config import settings
from .database import Base, SessionLocal, engine
from .routers import admin, auth, generate, relay, templates
from .seed import seed_system_templates
from .services.storage import cleanup_expired

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(title="套图生成服务", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(templates.router)
app.include_router(generate.router)
app.include_router(admin.router)
app.include_router(relay.router)

scheduler = BackgroundScheduler()


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_system_templates(db)
    finally:
        db.close()

    def cleanup_job():
        db = SessionLocal()
        try:
            cleanup_expired(db)
        finally:
            db.close()

    scheduler.add_job(cleanup_job, "interval", hours=settings.CLEANUP_INTERVAL_HOURS, next_run_time=None)
    scheduler.start()
    logger.info("startup complete - cleanup job scheduled every %sh", settings.CLEANUP_INTERVAL_HOURS)


@app.on_event("shutdown")
def on_shutdown():
    scheduler.shutdown(wait=False)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---- serve the static frontend last, so it never shadows /api or /v1 routes ----
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    logger.warning("frontend directory not found at %s - API-only mode", FRONTEND_DIR)
