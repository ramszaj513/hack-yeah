from functools import lru_cache
import os

from dotenv import load_dotenv

load_dotenv()


@lru_cache
def settings() -> dict[str, object]:
    origins = os.getenv("FRONTEND_ORIGINS", "*")
    return {
        "demo_mode": os.getenv("DEMO_MODE", "true").lower() in {"1", "true", "yes"},
        "google_fact_check_api_key": os.getenv("GOOGLE_FACT_CHECK_API_KEY", ""),
        "frontend_origins": [origin.strip() for origin in origins.split(",") if origin.strip()],
    }
