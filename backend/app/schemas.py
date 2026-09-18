import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------- Auth ----------

class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterOut(BaseModel):
    status: str  # "active" | "pending"
    message: str
    access_token: Optional[str] = None
    token_type: str = "bearer"


class MeOut(BaseModel):
    id: int
    username: str
    is_admin: bool
    daily_quota: float
    cost_per_image: float
    used_today: float
    relay_key: str

    class Config:
        from_attributes = True


# ---------- Templates ----------

class TemplateFields(BaseModel):
    subject: str = ""
    style: str = ""
    photography: str = ""
    atmosphere: str = ""
    background: str = ""
    light: str = ""
    negative: str = ""
    parameters: str = ""


class TemplateCreateIn(TemplateFields):
    name: str
    season: str = ""
    scene: str = ""
    product: str = ""
    region: str = ""


class TemplateUpdateIn(BaseModel):
    name: Optional[str] = None
    season: Optional[str] = None
    scene: Optional[str] = None
    product: Optional[str] = None
    region: Optional[str] = None
    subject: Optional[str] = None
    style: Optional[str] = None
    photography: Optional[str] = None
    atmosphere: Optional[str] = None
    background: Optional[str] = None
    light: Optional[str] = None
    negative: Optional[str] = None
    parameters: Optional[str] = None


class TemplateOut(TemplateFields):
    id: int
    owner_id: Optional[int]
    is_system: bool
    editable: bool  # computed relative to the requesting user
    name: str
    season: str
    scene: str
    product: str
    region: str
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


class TemplateFilterOptions(BaseModel):
    seasons: List[str]
    scenes: List[str]
    products: List[str]
    regions: List[str]


# ---------- Generation ----------

class GenerationOut(BaseModel):
    id: int
    template_id: Optional[int]
    prompt_snapshot: dict
    input_images: List[str]
    output_images: List[str]
    image_count: int
    cost: float
    status: str
    error_message: str
    created_at: datetime.datetime
    expire_at: datetime.datetime

    class Config:
        from_attributes = True


class BatchDownloadIn(BaseModel):
    ids: List[int]


# ---------- Admin ----------

class AdminUserOut(BaseModel):
    id: int
    username: str
    is_admin: bool
    is_approved: bool
    daily_quota: float
    cost_per_image: float
    used_today: float
    total_generated: int
    total_cost: float
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class AdminUserUpdateIn(BaseModel):
    daily_quota: Optional[float] = None
    cost_per_image: Optional[float] = None
    is_admin: Optional[bool] = None
    is_approved: Optional[bool] = None


class AdminConfigOut(BaseModel):
    default_cost_per_image: float
    default_daily_quota: float
    remote_relay_base_url: str
    remote_relay_api_key: str


class AdminConfigUpdateIn(BaseModel):
    default_cost_per_image: Optional[float] = None
    default_daily_quota: Optional[float] = None
    remote_relay_base_url: Optional[str] = None
    remote_relay_api_key: Optional[str] = None


class AdminStatsOut(BaseModel):
    total_users: int
    total_generations: int
    total_cost: float
    today_generations: int
    today_cost: float
    per_user: List[AdminUserOut]
