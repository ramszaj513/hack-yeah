from dataclasses import dataclass, field
from functools import lru_cache
import os

from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    demo_mode: bool
    frontend_origins: list[str]

    openai_api_key: str
    openai_model: str
    openai_reasoning_model: str

    google_fact_check_api_key: str

    max_claims: int
    max_transcript_segments: int
    enable_web_search: bool
    enable_citation_verification: bool
    enable_refutation_pass: bool

    # Several open academic APIs ask for a contact address in the User-Agent
    # in exchange for higher, friendlier rate limits.
    contact_email: str

    evidence_per_claim: int = 9
    http_timeout_seconds: float = 20.0

    extra: dict[str, str] = field(default_factory=dict)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)


@lru_cache
def settings() -> Settings:
    origins = os.getenv("FRONTEND_ORIGINS", "*")
    return Settings(
        demo_mode=_flag("DEMO_MODE", "false"),
        frontend_origins=[origin.strip() for origin in origins.split(",") if origin.strip()],
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini").strip(),
        openai_reasoning_model=os.getenv("OPENAI_REASONING_MODEL", "gpt-5.4").strip(),
        google_fact_check_api_key=os.getenv("GOOGLE_FACT_CHECK_API_KEY", "").strip(),
        max_claims=_int("MAX_CLAIMS", 8),
        max_transcript_segments=_int("MAX_TRANSCRIPT_SEGMENTS", 2000),
        enable_web_search=_flag("ENABLE_WEB_SEARCH", "true"),
        enable_citation_verification=_flag("ENABLE_CITATION_VERIFICATION", "true"),
        enable_refutation_pass=_flag("ENABLE_REFUTATION_PASS", "true"),
        contact_email=os.getenv("CONTACT_EMAIL", "").strip(),
    )


def user_agent() -> str:
    contact = settings().contact_email
    suffix = f" ({contact})" if contact else ""
    return f"yt-fact-checker/0.2 (+https://github.com/ramszaj513/hack-yeah){suffix}"
