from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class Verdict(str, Enum):
    FALSE = "false"
    POTENTIALLY_FALSE = "potentially_false"
    MISLEADING = "misleading"
    SUPPORTED = "supported"
    CONTEXT_NEEDED = "context_needed"
    COULDNT_VERIFY = "couldnt_verify"


class TranscriptSegment(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    start: float = Field(ge=0)
    duration: float = Field(default=0, ge=0)

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Transcript text cannot be blank")
        return value.strip()


class VideoMetadata(BaseModel):
    id: str = Field(min_length=6, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=10000)
    language: str = Field(default="en", min_length=2, max_length=12)


class CheckRequest(BaseModel):
    video: VideoMetadata
    transcript: list[TranscriptSegment] = Field(max_length=2000)


class Context(BaseModel):
    country: str | None = None
    timeframe: str | None = None


class Evidence(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    title: str = Field(min_length=1, max_length=500)
    publisher: str = Field(min_length=1, max_length=250)
    url: HttpUrl
    sourceType: Literal["primary", "fact_checker", "journalism", "reference"]


class Claim(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    text: str = Field(min_length=1, max_length=2000)
    startSeconds: float = Field(ge=0)
    endSeconds: float = Field(ge=0)
    verdict: Verdict
    basis: str = Field(min_length=1, max_length=3000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=10)
    context: Context = Field(default_factory=Context)

    @field_validator("endSeconds")
    @classmethod
    def end_after_start(cls, value: float, info):
        start = info.data.get("startSeconds")
        if start is not None and value < start:
            raise ValueError("endSeconds must be greater than or equal to startSeconds")
        return value


class CheckResponse(BaseModel):
    analysisId: str
    status: Literal["complete", "no_transcript", "no_claims", "failed"]
    mode: Literal["demo", "live"] = "live"
    claims: list[Claim] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
