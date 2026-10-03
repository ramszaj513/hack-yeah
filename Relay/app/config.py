"""Configuration constants for the Relay app.

See ``docs/ARCHITECTURE.md`` (geometry and constants) and ``docs/PLAN.md`` section 3.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- Geometry / scale ------------------------------------------------------
R = 6371.0  # Earth radius in km
LAT0 = 52.2297  # map center (Warsaw)
LON0 = 21.0117  # map center (Warsaw)
SPEED_KMH = 50.0
SPEED_KM_PER_MIN = SPEED_KMH / 60.0  # 0.8333 km/min

# --- Categories ------------------------------------------------------------
# Internal category keys shared by crates and need-point requirements.
CATEGORIES: tuple[str, ...] = ("food", "water", "meds", "hygiene", "other")

# --- Solver modes ----------------------------------------------------------
FAIR_SHARE = "fair_share"
NEAREST_FIT = "nearest_fit"
MODES: tuple[str, ...] = (FAIR_SHARE, NEAREST_FIT)
DEFAULT_MODE = FAIR_SHARE

# --- Database --------------------------------------------------------------
_DEFAULT_DB = Path(__file__).resolve().parents[1] / "relay.db"
DB_PATH = os.environ.get("RELAY_DB_PATH", str(_DEFAULT_DB))

# Bump this when the seed scenario changes so existing databases get reseeded.
SEED_VERSION = "3"

# How long a suggested detour stays valid before it expires (seconds).
SUGGESTION_TTL_SECONDS = 90

# --- Solver behavior -------------------------------------------------------
# Small tolerance for floating-point errors in distance comparisons.
EPS = 1e-9
