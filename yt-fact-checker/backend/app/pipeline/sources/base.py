from __future__ import annotations

from dataclasses import dataclass
import re
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

    # True when the excerpt is a quote the model says it read on the page,
    # rather than text handed to us by a structured API. Only these can be
    # invented, so only these are worth checking before we rely on them.
    modelReported: bool = False
    snippetVerified: bool | None = None

    def truncated(self, limit: int = 1200) -> "RetrievedDoc":
        return RetrievedDoc(
            title=self.title[:300],
            publisher=self.publisher[:200],
            url=self.url,
            sourceType=self.sourceType,
            snippet=" ".join(self.snippet.split())[:limit],
            modelReported=self.modelReported,
            snippetVerified=self.snippetVerified,
        )


@dataclass
class ClaimContext:
    claim: str
    country: str | None = None
    timeframe: str | None = None
    claimType: str | None = None


_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "the a an is are was were be been being of in on at to for with and or not "
    "that this these those it its as by from has have had can could would should "
    "which who whom what when where why how example simple set".split()
)


def select_passages(document: str, claim: str, *, limit: int = 2200, keep: int = 3) -> str:
    """Pick the parts of a long document that actually bear on the claim.

    Sending the first N characters of an article is close to useless: an
    encyclopedia entry opens with a definition, while the sentence that
    confirms or refutes a specific claim is usually further down. Truncating
    from the top starves the adjudicator of the one line it needed.
    """
    paragraphs = [part.strip() for part in re.split(r"\n{2,}|\n(?===)", document) if part.strip()]
    if not paragraphs:
        return " ".join(document.split())[:limit]

    terms = {word for word in _WORD.findall(claim.lower()) if word not in _STOPWORDS and len(word) > 2}
    if not terms:
        return " ".join(" ".join(paragraphs).split())[:limit]

    scored: list[tuple[float, int, str]] = []
    for index, paragraph in enumerate(paragraphs):
        words = _WORD.findall(paragraph.lower())
        if not words:
            continue
        hits = sum(1 for term in terms if term in words)
        if not hits:
            continue
        # Favour paragraphs dense in the claim's terms, not merely long ones.
        scored.append((hits / len(terms) + hits / (len(words) ** 0.5), index, paragraph))

    if not scored:
        return " ".join(" ".join(paragraphs[:2]).split())[:limit]

    scored.sort(key=lambda row: row[0], reverse=True)
    chosen = sorted(scored[:keep], key=lambda row: row[1])
    return " ".join(" … ".join(paragraph for _, _, paragraph in chosen).split())[:limit]


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
