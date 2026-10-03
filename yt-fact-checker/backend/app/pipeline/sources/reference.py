"""Wikipedia lookup. Free, keyless, and strong on entities and definitions."""

from __future__ import annotations

from app.pipeline.sources.base import ClaimContext, RetrievedDoc, http_client


SEARCH = "https://en.wikipedia.org/w/api.php"
SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"


class WikipediaSource:
    name = "wikipedia"

    async def fetch(self, context: ClaimContext) -> list[RetrievedDoc]:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": context.claim[:300],
            "srlimit": 3,
            "format": "json",
        }
        async with http_client() as client:
            response = await client.get(SEARCH, params=params)
            response.raise_for_status()
            hits = response.json().get("query", {}).get("search", [])

            docs: list[RetrievedDoc] = []
            for hit in hits:
                title = hit.get("title")
                if not title:
                    continue
                try:
                    detail = await client.get(SUMMARY + title.replace(" ", "_"))
                    detail.raise_for_status()
                    payload = detail.json()
                except Exception:
                    continue

                url = (payload.get("content_urls", {}).get("desktop", {}) or {}).get("page")
                extract = payload.get("extract") or ""
                if not url or not extract:
                    continue
                docs.append(
                    RetrievedDoc(
                        title=title,
                        publisher="Wikipedia",
                        url=url,
                        sourceType="reference",
                        snippet=extract,
                    ).truncated()
                )
            return docs
