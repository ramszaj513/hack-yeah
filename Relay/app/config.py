"""Stałe konfiguracyjne aplikacji Relay.

Zob. ``docs/ARCHITECTURE.md`` (geometria i stałe) oraz ``docs/PLAN.md`` sekcja 3.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- Geometria / skala -----------------------------------------------------
R = 6371.0  # promień Ziemi w km
LAT0 = 52.2297  # środek mapy (Warszawa)
LON0 = 21.0117  # środek mapy (Warszawa)
SPEED_KMH = 50.0
SPEED_KM_PER_MIN = SPEED_KMH / 60.0  # 0.8333 km/min

# --- Kategorie -------------------------------------------------------------
# Wewnętrzne klucze kategorii wspólne dla skrzynek i zapotrzebowania.
CATEGORIES: tuple[str, ...] = ("food", "water", "meds", "hygiene", "other")

# --- Tryby solvera ---------------------------------------------------------
FAIR_SHARE = "fair_share"
NEAREST_FIT = "nearest_fit"
MODES: tuple[str, ...] = (FAIR_SHARE, NEAREST_FIT)
DEFAULT_MODE = FAIR_SHARE

# --- Baza danych -----------------------------------------------------------
_DEFAULT_DB = Path(__file__).resolve().parents[1] / "relay.db"
DB_PATH = os.environ.get("RELAY_DB_PATH", str(_DEFAULT_DB))

# --- Zachowanie solvera ----------------------------------------------------
# Mała tolerancja na błędy zmiennoprzecinkowe przy porównaniach odległości.
EPS = 1e-9
