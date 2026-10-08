from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class PlanDetail(BaseModel):
    name: str
    price: int
    currency: str = "MMK"
    max_words: int
    weekly_generations: Optional[int]
    lifetime_generations: Optional[int] = None
    requires_login: bool


class VoiceQuotaOut(BaseModel):
    id: Optional[int] = None
    email: Optional[str] = None
    plan: str
    is_pro: bool = False
    subscription_active: bool = False
    used_generations: int
    weekly_generations: Optional[int]
    weekly_generations_used: int
    weekly_generations_limit: Optional[int]
    max_words: int
    words_limit: int
    credits: Optional[int] = None
    token_usage: int = 0
    generation_limit: Optional[int] = None
    generation_period: str = "weekly"  # "lifetime" (free) | "weekly" | "unlimited"
    free_generations_used: int = 0
    free_generations_limit: int = 1
    active_from: Optional[datetime] = None
    active_until: Optional[datetime] = None
    resets_at: Optional[datetime] = None


class StylePresetOut(BaseModel):
    id: str
    name: str
    myanmar_name: str
    category: str
    description: str
    icon: str
    default_intensity: float
    tags: list[str] = Field(default_factory=list)


class StyleCategoryOut(BaseModel):
    id: str
    name: str
    myanmar_name: str
    description: str
    icon: str


class StyleListResponse(BaseModel):
    categories: list[StyleCategoryOut]
    presets: list[StylePresetOut]


class StyleProcessRequest(BaseModel):
    generated_audio_id: Optional[str] = None
    audio_id: Optional[str] = None
    style: str
    intensity: float = Field(default=0.8, ge=0.0, le=100.0)


class StyleProcessResponse(BaseModel):
    audio_id: str
    preset_id: str
    preset_name: str
    category: str
    intensity: float
    intensity_percent: int
    duration_seconds: Optional[float] = None
    sample_rate: Optional[int] = None
    cached: bool
    processing_time_ms: float
    audio_url: str


class VoiceEffectRequest(BaseModel):
    audio_id: Optional[str] = None
    generated_audio_id: Optional[str] = None
    preset: str
    intensity: float = Field(default=80.0, ge=0.0, le=100.0)


class VoiceEffectResponse(BaseModel):
    audio_id: str
    preset: str
    preset_name: Optional[str] = None
    category: Optional[str] = None
    intensity: float
    intensity_percent: int
    duration_seconds: Optional[float] = None
    sample_rate: Optional[int] = None
    cached: bool = False
    processing_time_ms: float = 0.0
    url: str


