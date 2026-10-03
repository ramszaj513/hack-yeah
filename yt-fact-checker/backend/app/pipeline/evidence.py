import os
from typing import Any

import httpx

from app.models.schemas import Evidence


class EvidenceProvider:
    async def search(self, claim: str, context: dict[str, str | None]) -> list[Evidence]:
        raise NotImplementedError


class GoogleFactCheckProvider(EvidenceProvider):
    """Optional adapter for Google's public Fact Check Tools API."""

    endpoint = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, claim: str, context: dict[str, str | None]) -> list[Evidence]:
        params = {"query": claim, "languageCode": "en", "key": self.api_key, "pageSize": 5}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(self.endpoint, params=params)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()

        evidence: list[Evidence] = []
        for item in payload.get("claims", []):
            review = (item.get("claimReview") or [{}])[0]
            url = review.get("url")
            title = review.get("title") or item.get("text") or "Fact-check review"
            publisher = (review.get("publisher") or {}).get("name", "Fact Check Tools")
            if not url:
                continue
            evidence.append(
                Evidence(
                    title=title,
                    publisher=publisher,
                    url=url,
                    sourceType="fact_checker",
                )
            )
        return evidence


def configured_provider() -> EvidenceProvider | None:
    key = os.getenv("GOOGLE_FACT_CHECK_API_KEY", "")
    return GoogleFactCheckProvider(key) if key else None
