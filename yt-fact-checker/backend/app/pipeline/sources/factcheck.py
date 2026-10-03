"""Google Fact Check Tools.

High precision when it hits, but it only covers claims a professional
fact-checker has already published a ClaimReview for — a small slice of what
gets said in an arbitrary video. It is one source among several, never the
whole pipeline.
"""

from __future__ import annotations

from app.config import settings
from app.pipeline.sources.base import ClaimContext, RetrievedDoc, http_client


ENDPOINT = "https://factchecktools.googleapis.com/v1alpha1/claims:search"


class GoogleFactCheckSource:
    name = "google_fact_check"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key if api_key is not None else settings().google_fact_check_api_key

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def fetch(self, context: ClaimContext) -> list[RetrievedDoc]:
        if not self.available:
            return []

        params = {
            "query": context.claim[:300],
            "languageCode": "en",
            "key": self.api_key,
            "pageSize": 5,
        }
        async with http_client() as client:
            response = await client.get(ENDPOINT, params=params)
            response.raise_for_status()
            payload = response.json()

        docs: list[RetrievedDoc] = []
        for item in payload.get("claims", []) or []:
            review = (item.get("claimReview") or [{}])[0]
            url = review.get("url")
            if not url:
                continue
            rating = review.get("textualRating") or ""
            reviewed = item.get("text") or ""
            docs.append(
                RetrievedDoc(
                    title=review.get("title") or reviewed or "Fact-check review",
                    publisher=(review.get("publisher") or {}).get("name", "Fact Check Tools"),
                    url=url,
                    sourceType="fact_checker",
                    snippet=f"Reviewed claim: {reviewed}. Rating by the publisher: {rating}.",
                ).truncated()
            )
        return docs
