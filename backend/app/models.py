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
    is_approved = Column(Boolean, default=False, nullable=False)  # registration needs admin approval

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
    remix_template_id = Column(Integer, ForeignKey("remix_templates.id"), nullable=True)  # 二创套图模板

    # All jobs created by one click of "生成套图" share the same batch_id --
    # even when that click fans out into several GenerationJob rows (one per
    # selected template). Used to group the download/history UI so a batch
    # downloads as one folder instead of one-folder-per-template. Always
    # populated (server assigns one if the client doesn't send it); legacy
    # rows from before this column existed are backfilled to their own
    # singleton batch (see migrate.py).
    batch_id = Column(String(64), index=True, nullable=True)

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

    # Deprecated as of the multi-provider RelayProvider table below -- kept
    # only so a one-time startup migration can carry an already-configured
    # single relay forward into a RelayProvider row. Don't read/write these
    # anywhere else.
    remote_relay_base_url = Column(String(300), default="")
    remote_relay_api_key = Column(String(200), default="")


class RelayProvider(Base):
    """One configured upstream (chat + image) relay. Multiple can be saved;
    exactly one is `is_active` at a time -- that's the one actually used for
    套图 generation and for this service's own /v1/* passthrough. Admin can
    add/edit/switch from the admin panel at any time, no redeploy needed."""

    __tablename__ = "relay_providers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    # "sync_edit"   -> OpenAI-style synchronous POST {base_url}/images/edits
    #                  (multipart image[] fields, immediate image bytes/url back).
    #                  This is what the user's own ai-relay project speaks.
    # "toapis_async" -> ToAPIs-style: upload ref images to {base_url}/uploads/images
    #                  first, POST {base_url}/images/generations (JSON,
    #                  reference_images as URLs) to get a task id, then poll
    #                  GET {base_url}/images/generations/{task_id} until
    #                  completed/failed.
    kind = Column(String(30), nullable=False, default="sync_edit")
    base_url = Column(String(300), nullable=False)
    api_key = Column(String(300), nullable=False)
    image_model = Column(String(100), nullable=False, default="gpt-image-2")  # e.g. gpt-image-2, gemini-3-pro-image
    is_active = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class RemixTemplate(Base):
    """二创套图模板: composite a batch of uploaded product photos (图2) into
    one preset background image (图1) that lives on the template itself, using
    a single plain-text prompt instead of the 8-field structured prompt that
    the regular Template uses. Naming convention (not enforced, just a UI
    hint): "产品-描述", e.g. "产品-低角度-白底"."""

    __tablename__ = "remix_templates"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # null = system template
    is_system = Column(Boolean, default=False, nullable=False)

    name = Column(String(200), nullable=False)
    product = Column(String(50), index=True, default="")  # also the permission-scoping dimension

    background_image_path = Column(String(500), nullable=False, default="")  # 图1, relative to REMIX_BG_DIR
    prompt = Column(Text, default="把上传的产品（图2）放到图1中")

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    owner = relationship("User")


class UserProductAccess(Base):
    """Grants a user permission to see/use templates (regular or 二创) for one
    `product`. A user with zero rows here is unrestricted (sees every
    product) -- this is an opt-in allowlist an admin applies per user, not a
    default lockout, so upgrading never silently hides existing templates
    from users who were already using them."""

    __tablename__ = "user_product_access"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    product = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class RelayUsageLog(Base):
    __tablename__ = "relay_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    model = Column(String(100))
    endpoint = Column(String(100))
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
