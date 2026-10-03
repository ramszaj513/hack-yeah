from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import settings, user_agent
from app.models.schemas import SourceType


@dataclass
class RetrievedDoc:
    title: str
    publisher: str
    url: str
    sourceType: SourceType
    snippet: str = ""

    def truncated(self, limit: int = 1200) -> "RetrievedDoc":
        return RetrievedDoc(
            title=self.title[:300],
            publisher=self.publisher[:200],
            url=self.url,
            sourceType=self.sourceType,
            snippet=" ".join(self.snippet.split())[:limit],
        )


@dataclass
class ClaimContext:
    claim: str
    country: str | None = None
    timeframe: str | None = None


class Source(Protocol):
    name: str

    async def fetch(self, context: ClaimContext) -> list[RetrievedDoc]:
        ...


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=settings().http_timeout_seconds,
        headers={"User-Agent": user_agent(), "Accept": "application/json"},
        follow_redirects=True,
    )
