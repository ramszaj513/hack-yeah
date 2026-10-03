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


class UnverifiedReason(str, Enum):
    """Why a claim did not receive a definitive verdict.

    Collapsing every unresolved claim into a single `couldnt_verify` hides the
    difference between "nobody has published on this" and "our provider timed
    out", which are very different things for a viewer deciding how much weight
    to give the result.
    """

    NO_EVIDENCE_FOUND = "no_evidence_found"
    SOURCES_CONFLICT = "sources_conflict"
    EVIDENCE_NOT_SPECIFIC = "evidence_not_specific"
    CITATION_UNVERIFIABLE = "citation_unverifiable"
    PROVIDER_ERROR = "provider_error"
    CLAIM_AMBIGUOUS = "claim_ambiguous"


class Technique(str, Enum):
    """How a passage persuades. Names the method, never the position taken."""

    UNDISCLOSED_AD = "undisclosed_ad"
    EMOTIONAL_MANIPULATION = "emotional_manipulation"
    LOADED_LANGUAGE = "loaded_language"
    LOGICAL_FALLACY = "logical_fallacy"
    CHERRY_PICKING = "cherry_picking"
    CONSPIRACY_FRAMING = "conspiracy_framing"
    POLITICAL_FRAMING = "political_framing"
    UNFALSIFIABLE = "unfalsifiable"


class ClaimType(str, Enum):
    DEFINITIONAL = "definitional"
    STATISTICAL = "statistical"
    SCIENTIFIC = "scientific"
    HISTORICAL = "historical"
    POLITICAL = "political"
    GENERAL = "general"


SourceType = Literal["primary", "academic", "fact_checker", "journalism", "reference", "web"]

# Lower rank wins when evidence is sorted or when sources disagree.
SOURCE_TIER: dict[str, int] = {
    "primary": 0,
    "academic": 1,
    "fact_checker": 2,
    "reference": 3,
    "journalism": 4,
    "web": 5,
}


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
    url: str = Field(default="", max_length=500)
    transcript: list[TranscriptSegment] = Field(default_factory=list, max_length=2000)


class Context(BaseModel):
    country: str | None = None
    timeframe: str | None = None


class Evidence(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    title: str = Field(min_length=1, max_length=500)
    publisher: str = Field(min_length=1, max_length=250)
    url: HttpUrl
    sourceType: SourceType

    # The span the model says supports its reading of this source. When
    # citation verification runs, `quoteVerified` records whether that span was
    # actually found in the fetched page.
    snippet: str = Field(default="", max_length=600)
    quoteVerified: bool | None = None
    supports: Literal["supports", "contradicts", "context"] = "supports"

    @property
    def tier(self) -> int:
        return SOURCE_TIER.get(str(self.sourceType), 9)


class Claim(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))

    # `text` is the decontextualised, self-contained claim shown to the viewer.
    # `quote` is the verbatim transcript span it came from, which is what the
    # timestamp is derived from and what proves the claim was not invented.
    text: str = Field(min_length=1, max_length=2000)
    quote: str = Field(default="", max_length=2000)

    startSeconds: float = Field(ge=0)
    endSeconds: float = Field(ge=0)

    verdict: Verdict
    claimType: ClaimType = ClaimType.GENERAL
    unverifiedReason: UnverifiedReason | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    basis: str = Field(min_length=1, max_length=700)
    evidence: list[Evidence] = Field(default_factory=list, max_length=12)
    context: Context = Field(default_factory=Context)

    @field_validator("endSeconds")
    @classmethod
    def end_after_start(cls, value: float, info):
        start = info.data.get("startSeconds")
        if start is not None and value < start:
            raise ValueError("endSeconds must be greater than or equal to startSeconds")
        return value


class Signal(BaseModel):
    """A rhetorical observation, anchored to the transcript like a claim."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    quote: str = Field(min_length=1, max_length=2000)
    startSeconds: float = Field(ge=0)
    endSeconds: float = Field(ge=0)
    technique: Technique
    severity: Literal["low", "medium", "high"] = "low"
    note: str = Field(min_length=1, max_length=300)


class CheckResponse(BaseModel):
    analysisId: str
    status: Literal["complete", "no_transcript", "no_claims", "failed"]
    mode: Literal["demo", "live"] = "live"
    claims: list[Claim] = Field(default_factory=list)
    signals: list[Signal] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
