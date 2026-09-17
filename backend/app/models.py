import datetime
import secrets

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .database import Base


def gen_relay_key() -> str:
    return "rk-" + secrets.token_hex(20)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)

    daily_quota = Column(Float, nullable=False)  # max $ spend / day, admin-editable
    cost_per_image = Column(Float, nullable=False)  # $ cost charged per generated image

    relay_key = Column(String(64), unique=True, index=True, default=gen_relay_key)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    templates = relationship("Template", back_populates="owner", cascade="all, delete-orphan")
    jobs = relationship("GenerationJob", back_populates="user", cascade="all, delete-orphan")


class Template(Base):
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # null = system template
    is_system = Column(Boolean, default=False, nullable=False)  # admin-created -> read-only to others

    name = Column(String(200), nullable=False)
    season = Column(String(50), index=True, default="")
    scene = Column(String(50), index=True, default="")  # 场景/细节
    product = Column(String(50), index=True, default="")
    region = Column(String(100), index=True, default="")  # 区域

    subject = Column(Text, default="")
    style = Column(Text, default="")
    photography = Column(Text, default="")
    atmosphere = Column(Text, default="")
    background = Column(Text, default="")
    light = Column(Text, default="")
    negative = Column(Text, default="")
    parameters = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="templates")

    def prompt_fields(self) -> dict:
        return {
            "subject": self.subject,
            "style": self.style,
            "photography": self.photography,
            "atmosphere": self.atmosphere,
            "background": self.background,
            "light": self.light,
            "negative": self.negative,
            "parameters": self.parameters,
        }


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    template_id = Column(Integer, ForeignKey("templates.id"), nullable=True)

    # Snapshot of the exact prompt used, so later edits to the template (or its
    # deletion) never change the historical record of what was generated.
    prompt_snapshot_json = Column(Text, default="{}")

    input_images_json = Column(Text, default="[]")   # list of relative paths under UPLOAD_DIR
    output_images_json = Column(Text, default="[]")  # list of relative paths under GENERATED_DIR

    image_count = Column(Integer, default=1)
    cost = Column(Float, default=0.0)
    status = Column(String(20), default="success")  # pending | success | failed
    error_message = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    expire_at = Column(DateTime, nullable=False, index=True)

    user = relationship("User", back_populates="jobs")


class GlobalConfig(Base):
    """Singleton row (id=1) holding admin-editable platform defaults."""

    __tablename__ = "global_config"

    id = Column(Integer, primary_key=True, default=1)
    default_cost_per_image = Column(Float, default=0.3)
    default_daily_quota = Column(Float, default=50.0)


class RelayUsageLog(Base):
    __tablename__ = "relay_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    model = Column(String(100))
    endpoint = Column(String(100))
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
