import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from . import models

logger = logging.getLogger("seed")

SEED_FILE = Path(__file__).resolve().parent.parent / "seed_data" / "templates.json"


def seed_system_templates(db: Session) -> int:
    """Loads seed_data/templates.json as read-only system templates, once.
    Safe to call on every startup - skips templates that already exist
    (matched by name) so re-running never creates duplicates."""
    if not SEED_FILE.exists():
        logger.info("no seed file at %s, skipping", SEED_FILE)
        return 0

    with open(SEED_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)

    existing_names = {
        n for (n,) in db.query(models.Template.name).filter(models.Template.is_system == True)  # noqa: E712
    }

    created = 0
    for item in items:
        if item["name"] in existing_names:
            continue
        tpl = models.Template(
            owner_id=None,
            is_system=True,
            name=item["name"],
            season=item.get("season", ""),
            scene=item.get("scene", ""),
            product=item.get("product", ""),
            region=item.get("region", ""),
            subject=item.get("subject", ""),
            style=item.get("style", ""),
            photography=item.get("photography", ""),
            atmosphere=item.get("atmosphere", ""),
            background=item.get("background", ""),
            light=item.get("light", ""),
            negative=item.get("negative", ""),
            parameters=item.get("parameters", ""),
        )
        db.add(tpl)
        created += 1

    if created:
        db.commit()
        logger.info("seeded %d system template(s)", created)
    return created
