"""Opt-in result cache, for demos and for development.

Off by default. A live check should go and look at the world, and a cached
verdict is a frozen one — if it was wrong, it stays wrong until the entry
expires. That is the wrong trade for normal use.

It is the right trade in two places. On stage, a check that has been run once
replays in under a second and returns exactly what it returned in rehearsal,
instead of depending on a conference network and whatever the search index
feels like returning that minute. And while iterating on prompts, replaying the
evidence makes a change's effect visible instead of being buried under
retrieval noise.

Enable with CACHE_ENABLED=true. Warm it by running the check once.

Keys carry the model and a pipeline version, so changing a prompt or a model
invalidates what it would have affected rather than serving answers from the
old behaviour.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from app.config import settings


# Bump when a prompt, schema or routing rule changes in a way that should
# invalidate stored results.
PIPELINE_VERSION = "2026-10-04.1"

_lock = threading.Lock()
_connection: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        path = Path(settings().cache_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _connection = sqlite3.connect(path, check_same_thread=False)
        _connection.execute(
            "CREATE TABLE IF NOT EXISTS entries ("
            "  key TEXT PRIMARY KEY, value TEXT NOT NULL, stored_at REAL NOT NULL)"
        )
        _connection.commit()
    return _connection


def key_for(namespace: str, *parts: Any) -> str:
    payload = json.dumps(
        [namespace, PIPELINE_VERSION, *parts], sort_keys=True, ensure_ascii=False, default=str
    )
    return f"{namespace}:{hashlib.sha256(payload.encode()).hexdigest()[:32]}"


def get(key: str) -> Any | None:
    config = settings()
    if not config.cache_enabled:
        return None

    with _lock:
        row = _db().execute("SELECT value, stored_at FROM entries WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None

    value, stored_at = row
    if config.cache_ttl_seconds > 0 and time.time() - stored_at > config.cache_ttl_seconds:
        with _lock:
            _db().execute("DELETE FROM entries WHERE key = ?", (key,))
            _db().commit()
        return None

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def put(key: str, value: Any) -> None:
    if not settings().cache_enabled:
        return
    try:
        payload = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return

    with _lock:
        _db().execute(
            "INSERT INTO entries (key, value, stored_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, stored_at = excluded.stored_at",
            (key, payload, time.time()),
        )
        _db().commit()


def stats() -> dict[str, int]:
    if not settings().cache_enabled:
        return {"total": 0}
    with _lock:
        counts: dict[str, int] = {}
        total = 0
        for (key,) in _db().execute("SELECT key FROM entries"):
            total += 1
            namespace = key.split(":", 1)[0]
            counts[namespace] = counts.get(namespace, 0) + 1
    return {"total": total, **counts}


def clear() -> int:
    with _lock:
        removed = _db().execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        _db().execute("DELETE FROM entries")
        _db().commit()
    return removed
