"""Evidence retrieval: routing by claim type, then parallel fan-out."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app import cache
from app.config import settings
from app.models.schemas import SOURCE_TIER, ClaimType
from app.pipeline.sources.academic import EuropePmcSource, OpenAlexSource, SemanticScholarSource
from app.pipeline.sources.base import ClaimContext, RetrievedDoc, Source
from app.pipeline.sources.factcheck import GoogleFactCheckSource
from app.pipeline.sources.reference import WikipediaSource
from app.pipeline.sources.websearch import WebSearchSource


@dataclass
class Retrieval:
    docs: list[RetrievedDoc]
    attempted: list[str]
    failed: list[str]

    @property
    def all_failed(self) -> bool:
        return bool(self.attempted) and len(self.failed) == len(self.attempted)


# Routing is what separates this from a generic search wrapper: a health claim
# should reach the biomedical literature, not just whatever ranks well today.
ROUTES: dict[ClaimType, tuple[str, ...]] = {
    # Definitional and mathematical claims are settled by reference works.
    # Research abstracts assume these facts rather than stating them, so
    # routing them to the literature returns papers that never say the thing.
    ClaimType.DEFINITIONAL: ("wikipedia", "web_search", "openalex"),
    ClaimType.SCIENTIFIC: ("europe_pmc", "openalex", "semantic_scholar", "web_search", "wikipedia"),
    ClaimType.STATISTICAL: ("web_search", "wikipedia", "google_fact_check"),
    ClaimType.HISTORICAL: ("wikipedia", "web_search", "openalex"),
    ClaimType.POLITICAL: ("google_fact_check", "web_search", "wikipedia"),
    ClaimType.GENERAL: ("web_search", "wikipedia", "google_fact_check"),
}


def _registry() -> dict[str, Source]:
    return {
        "wikipedia": WikipediaSource(),
        "semantic_scholar": SemanticScholarSource(),
        "openalex": OpenAlexSource(),
        "europe_pmc": EuropePmcSource(),
        "google_fact_check": GoogleFactCheckSource(),
        "web_search": WebSearchSource(),
    }


def _is_available(source: Source) -> bool:
    available = getattr(source, "available", True)
    return bool(available)


async def gather_evidence(context: ClaimContext, claim_type: ClaimType) -> Retrieval:
    context.claimType = claim_type.value
    key = cache.key_for(
        "evidence", context.claim, context.country, context.timeframe,
        claim_type.value, settings().openai_model,
    )
    cached = cache.get(key)
    if cached is not None:
        return Retrieval(
            docs=[RetrievedDoc(**doc) for doc in cached["docs"]],
            attempted=cached["attempted"],
            failed=cached["failed"],
        )

    registry = _registry()
    names = ROUTES.get(claim_type, ROUTES[ClaimType.GENERAL])
    selected = [(name, registry[name]) for name in names if name in registry and _is_available(registry[name])]

    if not selected:
        return Retrieval(docs=[], attempted=[], failed=[])

    results = await asyncio.gather(
        *(source.fetch(context) for _, source in selected),
        return_exceptions=True,
    )

    docs: list[RetrievedDoc] = []
    failed: list[str] = []
    seen: set[str] = set()

    for (name, _), result in zip(selected, results):
        if isinstance(result, BaseException):
            failed.append(name)
            continue
        for doc in result:
            # Not `key`: that name holds the cache key, and shadowing it here
            # once stored every entry under a URL instead.
            url = doc.url.rstrip("/")
            if url in seen:
                continue
            seen.add(url)
            docs.append(doc)

    docs.sort(key=lambda doc: SOURCE_TIER.get(str(doc.sourceType), 9))
    retrieval = Retrieval(
        docs=docs[: settings().evidence_per_claim],
        attempted=[name for name, _ in selected],
        failed=failed,
    )
    # Caching a total provider failure would pin an outage in place.
    if retrieval.docs:
        cache.put(key, {
            "docs": [vars(doc) for doc in retrieval.docs],
            "attempted": retrieval.attempted,
            "failed": retrieval.failed,
        })
    return retrieval
