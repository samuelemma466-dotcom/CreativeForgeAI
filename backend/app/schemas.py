from __future__ import annotations

import re
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")


def _new_id() -> str:
    return uuid4().hex


def _check_color(value: str) -> str:
    if not HEX_COLOR.match(value):
        raise ValueError("Color must be a hex value like #112233 or #112233AA")
    return value.upper()


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


# ---------------------------------------------------------------- brands
class BrandCreate(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=8000)
    industry: str = Field(default="", max_length=200)
    products: str = Field(default="", max_length=4000)
    audience: str = Field(default="", max_length=4000)
    voice: str = Field(default="", max_length=2000)
    colors: list[str] = Field(default_factory=list, max_length=8)
    logo_media_id: str | None = None
    contact: dict[str, str] = Field(default_factory=dict)
    website: str = Field(default="", max_length=500)
    socials: dict[str, str] = Field(default_factory=dict)
    platforms: list[str] = Field(default_factory=list, max_length=12)
    guidelines: str = Field(default="", max_length=8000)

    @field_validator("colors")
    @classmethod
    def validate_colors(cls, colors: list[str]) -> list[str]:
        return [_check_color(color) for color in colors]


class BrandUpdate(BrandCreate):
    pass


# ------------------------------------------------------------- campaigns
class CampaignCreate(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    brand_id: str | None = None
    product: str = Field(default="", max_length=2000)
    audience: str = Field(default="", max_length=2000)
    objective: str = Field(default="", max_length=2000)
    platform: str = Field(default="", max_length=500)
    duration: str = Field(default="", max_length=200)
    budget: str = Field(default="", max_length=200)
    offer: str = Field(default="", max_length=2000)
    problem: str = Field(default="", max_length=2000)
    cta: str = Field(default="", max_length=1000)
    instructions: str = Field(default="", max_length=4000)
    status: Literal["draft", "active", "archived"] = "draft"


class CampaignUpdate(CampaignCreate):
    pass


class StrategyAngle(ApiModel):
    title: str = ""
    description: str = ""
    hook: str = ""


class StrategyConcept(ApiModel):
    title: str = ""
    big_idea: str = ""
    execution: str = ""


class StrategyCalendarItem(ApiModel):
    day: str = ""
    platform: str = ""
    content: str = ""


class CampaignStrategy(ApiModel):
    summary: str = ""
    positioning: str = ""
    audience_insights: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    value_propositions: list[str] = Field(default_factory=list)
    usps: list[str] = Field(default_factory=list)
    angles: list[StrategyAngle] = Field(default_factory=list)
    concepts: list[StrategyConcept] = Field(default_factory=list)
    content_calendar: list[StrategyCalendarItem] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------ copy
COPY_KINDS = {
    "headline",
    "hooks",
    "short_script",
    "long_script",
    "product_description",
    "sales_copy",
    "social_caption",
    "cta",
    "landing_page",
    "promo_message",
    "email",
    "voiceover",
    "platform_variations",
}
COPY_TONES = {
    "professional",
    "luxury",
    "conversational",
    "emotional",
    "persuasive",
    "bold",
    "playful",
    "corporate",
}


class CopyGenerateRequest(ApiModel):
    kind: str = Field(default="headline", max_length=80)
    tone: str = Field(default="professional", max_length=80)
    campaign_id: str | None = None
    brand_id: str | None = None
    platform: str = Field(default="", max_length=200)
    length: str = Field(default="medium", max_length=80)
    instructions: str = Field(default="", max_length=3000)
    action: Literal["generate", "rewrite", "shorten", "expand", "change_tone"] = "generate"
    content: str | None = Field(default=None, max_length=20000)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        if value not in COPY_KINDS:
            raise ValueError(f"Unsupported copy kind. Choose one of: {', '.join(sorted(COPY_KINDS))}")
        return value

    @field_validator("tone")
    @classmethod
    def validate_tone(cls, value: str) -> str:
        if value not in COPY_TONES:
            raise ValueError(f"Unsupported tone. Choose one of: {', '.join(sorted(COPY_TONES))}")
        return value


class CopyItemCreate(ApiModel):
    campaign_id: str | None = None
    brand_id: str | None = None
    kind: str = Field(max_length=80)
    tone: str = Field(default="", max_length=80)
    title: str = Field(default="", max_length=300)
    content: str = Field(min_length=1, max_length=100000)


# -------------------------------------------------------------- design
LayerType = Literal["image", "text", "shape"]
ImageFilter = Literal["none", "grayscale", "sepia", "warm", "cool", "blur", "high_contrast"]
FontFamily = Literal["sans", "serif", "mono"]


class DesignLayer(ApiModel):
    id: str = Field(default_factory=_new_id, max_length=64)
    type: LayerType
    x: float = Field(default=0, ge=-10000, le=10000)
    y: float = Field(default=0, ge=-10000, le=10000)
    width: float = Field(default=400, gt=0, le=10000)
    height: float = Field(default=300, gt=0, le=10000)
    opacity: float = Field(default=1, ge=0, le=1)
    rotation: float = Field(default=0, ge=-180, le=180)

    # image
    media_id: str | None = None
    fit: Literal["cover", "contain"] = "cover"
    filter: ImageFilter = "none"

    # text
    text: str = Field(default="", max_length=3000)
    font: FontFamily = "sans"
    font_size: int = Field(default=64, ge=8, le=500)
    bold: bool = False
    color: str = "#F6F2E8"
    align: Literal["left", "center", "right"] = "left"
    line_height: float = Field(default=1.15, ge=0.8, le=2.5)
    shadow: bool = False
    stroke_color: str = "#000000"
    stroke_width: int = Field(default=0, ge=0, le=30)
    background_color: str = "#00000000"
    padding: int = Field(default=0, ge=0, le=200)

    # shape (stroke shared with image/text borders)
    shape: Literal["rect", "rounded_rect", "ellipse", "line"] = "rect"
    fill: str = "#D7FF4F"
    radius: float = Field(default=24, ge=0, le=500)
    border_color: str = Field(default="#00000000")
    border_width: int = Field(default=0, ge=0, le=50)

    @field_validator(
        "color",
        "stroke_color",
        "background_color",
        "fill",
        "border_color",
    )
    @classmethod
    def validate_layer_colors(cls, value: str) -> str:
        return _check_color(value)

    @model_validator(mode="after")
    def validate_type_fields(self) -> "DesignLayer":
        if self.type == "image" and not self.media_id:
            raise ValueError("Image layers require media_id")
        return self


class DesignData(ApiModel):
    width: int = Field(default=1080, ge=64, le=4096)
    height: int = Field(default=1080, ge=64, le=4096)
    background: str = "#111111"
    layers: list[DesignLayer] = Field(default_factory=list, max_length=80)

    @field_validator("background")
    @classmethod
    def validate_background(cls, value: str) -> str:
        return _check_color(value)


class DesignCreate(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    brand_id: str | None = None
    campaign_id: str | None = None
    template_id: str | None = None
    width: int | None = Field(default=None, ge=64, le=4096)
    height: int | None = Field(default=None, ge=64, le=4096)


class DesignExportRequest(ApiModel):
    format: Literal["png", "jpg"] = "png"
    scale: float = Field(default=1, ge=0.25, le=2)


# --------------------------------------------------------------- video
class ClipTextStyle(ApiModel):
    font_size: int = Field(default=64, ge=12, le=300)
    color: str = "#F6F2E8"
    background_color: str = "#000000"
    background_opacity: float = Field(default=0, ge=0, le=1)
    bold: bool = True
    shadow: bool = True
    position: Literal["top", "center", "bottom", "lower_third", "custom"] = "bottom"
    x_pct: float = Field(default=50, ge=0, le=100)
    y_pct: float = Field(default=82, ge=0, le=100)
    max_width_pct: float = Field(default=86, ge=10, le=100)
    align: Literal["left", "center", "right"] = "center"

    @field_validator("color", "background_color")
    @classmethod
    def validate_text_colors(cls, value: str) -> str:
        return _check_color(value)


class VideoClip(ApiModel):
    id: str = Field(default_factory=_new_id, max_length=64)
    kind: Literal["video", "image", "audio", "voice", "music", "text"]
    media_id: str | None = None
    label: str = Field(default="", max_length=200)
    start: float = Field(default=0, ge=0, le=86400)
    duration: float = Field(default=3, gt=0.05, le=3600)
    source_in: float = Field(default=0, ge=0, le=86400)
    volume: float = Field(default=1, ge=0, le=2)
    fade_in: float = Field(default=0, ge=0, le=30)
    fade_out: float = Field(default=0, ge=0, le=30)
    motion: Literal["none", "zoom_in", "zoom_out", "pan_left", "pan_right"] = "none"
    transition: Literal["cut", "fade"] = "cut"
    fit: Literal["cover", "contain"] = "cover"
    rotation: Literal[0, 90, 180, 270] = 0
    text: str = Field(default="", max_length=3000)
    style: ClipTextStyle = Field(default_factory=ClipTextStyle)
    muted: bool = False

    @model_validator(mode="after")
    def validate_clip(self) -> "VideoClip":
        if self.kind in {"video", "image", "audio", "voice", "music"} and not self.media_id:
            raise ValueError(f"{self.kind} clips require media_id")
        if self.kind == "text" and not self.text.strip():
            raise ValueError("Text clips require text")
        return self


class VideoTrack(ApiModel):
    id: str = Field(default_factory=_new_id, max_length=64)
    type: Literal["visual", "text", "audio"]
    name: str = Field(default="Track", max_length=120)
    clips: list[VideoClip] = Field(default_factory=list, max_length=300)


class SubtitleStyle(ApiModel):
    enabled: bool = False
    font_size: int = Field(default=44, ge=12, le=160)
    color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline: int = Field(default=2, ge=0, le=10)
    position: Literal["bottom", "center", "top"] = "bottom"
    margin_v: int = Field(default=70, ge=0, le=600)

    @field_validator("color", "outline_color")
    @classmethod
    def validate_subtitle_colors(cls, value: str) -> str:
        return _check_color(value)


class VideoData(ApiModel):
    width: int = Field(default=1080, ge=160, le=3840)
    height: int = Field(default=1920, ge=160, le=3840)
    fps: int = Field(default=30, ge=12, le=60)
    background: str = "#0B0B0C"
    tracks: list[VideoTrack] = Field(default_factory=list)
    subtitles: SubtitleStyle = Field(default_factory=SubtitleStyle)
    subtitle_id: str | None = None

    @field_validator("background")
    @classmethod
    def validate_video_background(cls, value: str) -> str:
        return _check_color(value)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "VideoData":
        clip_ids: set[str] = set()
        for track in self.tracks:
            for clip in track.clips:
                if clip.id in clip_ids:
                    raise ValueError(f"Duplicate clip id: {clip.id}")
                clip_ids.add(clip.id)
        return self

    def duration(self) -> float:
        ends = [clip.start + clip.duration for track in self.tracks for clip in track.clips]
        return round(max(ends, default=0), 3)


class VideoCreate(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    brand_id: str | None = None
    campaign_id: str | None = None
    aspect_ratio: Literal["9:16", "16:9", "1:1", "4:5"] = "9:16"
    width: int | None = Field(default=None, ge=160, le=3840)
    height: int | None = Field(default=None, ge=160, le=3840)
    fps: int = Field(default=30, ge=12, le=60)


class ProjectUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["draft", "active", "archived"] | None = None
    brand_id: str | None = None
    campaign_id: str | None = None
    data: dict[str, Any] | None = None


class VideoExportRequest(ApiModel):
    preset: str = Field(default="tiktok", max_length=80)
    format: Literal["mp4"] = "mp4"
    width: int | None = Field(default=None, ge=160, le=3840)
    height: int | None = Field(default=None, ge=160, le=3840)
    fps: int | None = Field(default=None, ge=12, le=60)
    crf: int = Field(default=23, ge=16, le=35)


class PreviewRequest(ApiModel):
    max_width: int = Field(default=640, ge=320, le=1280)


# ----------------------------------------------------------- subtitles
class SubtitleCreate(ApiModel):
    project_id: str | None = None
    title: str = Field(default="Untitled subtitles", max_length=200)
    srt: str = Field(default="", max_length=300000)
    style: dict[str, Any] = Field(default_factory=dict)


class SubtitleUpdate(SubtitleCreate):
    pass


# --------------------------------------------------------------- voice
class VoiceRequest(ApiModel):
    text: str = Field(min_length=1, max_length=6000)
    voice: str = Field(default="en", max_length=80)
    rate: int = Field(default=165, ge=80, le=450)
    pitch: int = Field(default=50, ge=0, le=99)
    title: str = Field(default="", max_length=200)

    @field_validator("voice")
    @classmethod
    def validate_voice(cls, value: str) -> str:
        if not re.match(r"^[A-Za-z0-9_+\-]+$", value):
            raise ValueError("Invalid voice identifier")
        return value


# ---------------------------------------------------------------- chat
ChatRole = Literal["user", "assistant"]
ChatMode = Literal["chat", "critique", "ideas", "rewrite"]


class ChatMessage(ApiModel):
    role: ChatRole
    content: str = Field(min_length=1, max_length=12000)

    @field_validator("content")
    @classmethod
    def require_non_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message content cannot be blank")
        return value


class ChatRequest(ApiModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=32)
    project_id: str | None = Field(default=None, max_length=64)
    brand_id: str | None = Field(default=None, max_length=64)
    selection: str | None = Field(default=None, max_length=6000)
    mode: ChatMode = "chat"

    @model_validator(mode="after")
    def validate_conversation(self) -> "ChatRequest":
        if self.messages[-1].role != "user":
            raise ValueError("The conversation must end with a user message")
        if sum(len(message.content) for message in self.messages) > 24000:
            raise ValueError("Conversation history is too large. Start a new chat or shorten earlier messages")
        if self.mode == "rewrite" and not (self.selection or "").strip():
            raise ValueError("Rewrite mode requires selected text")
        return self


# ------------------------------------------------------------ providers
class ProviderSettingsIn(ApiModel):
    ollama_base_url: str | None = Field(default=None, max_length=500)
    ollama_model: str | None = Field(default=None, max_length=200)
    openrouter_model: str | None = Field(default=None, max_length=300)
    openrouter_api_key: str | None = Field(default=None, max_length=500)


class AssistantPlanRequest(ApiModel):
    project_id: str
    instruction: str = Field(min_length=3, max_length=3000)
