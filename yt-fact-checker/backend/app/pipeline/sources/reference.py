"""Wikipedia lookup. Free, keyless, and strong on entities and definitions.

Full article text is fetched rather than the REST intro summary. An intro
defines the topic; the sentence bearing on a specific claim usually sits
further down, so summary-only retrieval reports "no evidence" for claims the
article plainly settles.
"""

from __future__ import annotations

import re

from app.pipeline.sources.base import ClaimContext, RetrievedDoc, http_client, select_passages


API = "https://en.wikipedia.org/w/api.php"
PAGE_URL = "https://en.wikipedia.org/wiki/"
MAX_ARTICLE_CHARS = 200_000

# Wikipedia's plaintext export renders every formula as a {\displaystyle ...}
# blob, which crowds out real prose and shows up inside quoted evidence.
_LATEX = re.compile(r"\{\\displaystyle[^{}]*(?:\{[^{}]*\}[^{}]*)*\}")


def _clean(text: str) -> str:
    return re.sub(r"[ \t]{2,}", " ", _LATEX.sub("", text))


class WikipediaSource:
    name = "wikipedia"

    async def fetch(self, context: ClaimContext) -> list[RetrievedDoc]:
        async with http_client() as client:
            search = await client.get(
                API,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": context.claim[:300],
                    "srlimit": 3,
                    "format": "json",
                },
            )
            search.raise_for_status()
            hits = search.json().get("query", {}).get("search", [])

            titles = [hit["title"] for hit in hits if hit.get("title")]
            if not titles:
                return []

            # One call for the plain-text body of every hit.
            extracts = await client.get(
                API,
                params={
                    "action": "query",
                    "prop": "extracts",
                    "explaintext": 1,
                    "titles": "|".join(titles),
                    "format": "json",
                    "redirects": 1,
                },
            )
            extracts.raise_for_status()
            pages = extracts.json().get("query", {}).get("pages", {})

        docs: list[RetrievedDoc] = []
        for page in pages.values():
            title = page.get("title")
            body = _clean((page.get("extract") or "")[:MAX_ARTICLE_CHARS])
            if not title or not body:
                continue

            docs.append(
                RetrievedDoc(
                    title=title,
                    publisher="Wikipedia",
                    url=PAGE_URL + title.replace(" ", "_"),
                    sourceType="reference",
                    snippet=select_passages(body, context.claim),
                )
            )
        return docs
