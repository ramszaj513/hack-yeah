"""Peer-reviewed literature. All three APIs are free and need no key.

Europe PMC is the strongest for biomedical claims — the ones most worth getting
right — while OpenAlex gives broad cross-discipline coverage. Semantic Scholar
is excellent but rate-limits unauthenticated callers aggressively, so it is
treated as a bonus rather than something the pipeline leans on.
"""

from __future__ import annotations

import os

from app.config import settings
from app.pipeline.sources.base import ClaimContext, RetrievedDoc, http_client


SEMANTIC_SCHOLAR = "https://api.semanticscholar.org/graph/v1/paper/search"
EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
OPENALEX = "https://api.openalex.org/works"


class SemanticScholarSource:
    name = "semantic_scholar"

    async def fetch(self, context: ClaimContext) -> list[RetrievedDoc]:
        params = {
            "query": context.claim[:280],
            "limit": 4,
            "fields": "title,abstract,year,venue,url,citationCount,externalIds",
        }
        headers = {}
        key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
        if key:
            headers["x-api-key"] = key

        async with http_client() as client:
            response = await client.get(SEMANTIC_SCHOLAR, params=params, headers=headers)
            if response.status_code in (429, 403):
                # Unauthenticated quota is routinely exhausted; other academic
                # sources cover for it rather than failing the claim.
                return []
            response.raise_for_status()
            papers = response.json().get("data", []) or []

        docs: list[RetrievedDoc] = []
        for paper in papers:
            abstract = paper.get("abstract")
            url = paper.get("url")
            title = paper.get("title")
            if not (abstract and url and title):
                continue
            year = paper.get("year")
            venue = paper.get("venue") or "Semantic Scholar"
            citations = paper.get("citationCount")
            publisher = f"{venue}" + (f" ({year})" if year else "")
            if isinstance(citations, int):
                publisher += f" · {citations} citations"
            docs.append(
                RetrievedDoc(
                    title=title,
                    publisher=publisher,
                    url=url,
                    sourceType="academic",
                    snippet=abstract,
                ).truncated()
            )
        return docs


class EuropePmcSource:
    name = "europe_pmc"

    async def fetch(self, context: ClaimContext) -> list[RetrievedDoc]:
        params = {
            "query": context.claim[:280],
            "format": "json",
            "pageSize": 4,
            "resultType": "core",
        }
        async with http_client() as client:
            response = await client.get(EUROPE_PMC, params=params)
            response.raise_for_status()
            results = (response.json().get("resultList") or {}).get("result", []) or []

        docs: list[RetrievedDoc] = []
        for item in results:
            title = item.get("title")
            abstract = item.get("abstractText")
            if not (title and abstract):
                continue

            doi = item.get("doi")
            pmid = item.get("pmid")
            if doi:
                url = f"https://doi.org/{doi}"
            elif pmid:
                url = f"https://europepmc.org/article/MED/{pmid}"
            else:
                continue

            journal = item.get("journalTitle") or "Europe PMC"
            year = item.get("pubYear")
            docs.append(
                RetrievedDoc(
                    title=title,
                    publisher=f"{journal}" + (f" ({year})" if year else ""),
                    url=url,
                    sourceType="academic",
                    snippet=abstract,
                ).truncated()
            )
        return docs


def _reconstruct_abstract(inverted: dict[str, list[int]] | None) -> str:
    """OpenAlex stores abstracts as a word -> positions inverted index."""
    if not inverted:
        return ""
    positions: list[tuple[int, str]] = []
    for word, slots in inverted.items():
        for slot in slots:
            positions.append((slot, word))
    positions.sort()
    return " ".join(word for _, word in positions)


class OpenAlexSource:
    name = "openalex"

    async def fetch(self, context: ClaimContext) -> list[RetrievedDoc]:
        params = {"search": context.claim[:280], "per-page": 4}
        contact = settings().contact_email
        if contact:
            params["mailto"] = contact

        async with http_client() as client:
            response = await client.get(OPENALEX, params=params)
            response.raise_for_status()
            works = response.json().get("results", []) or []

        docs: list[RetrievedDoc] = []
        for work in works:
            title = work.get("display_name")
            abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
            doi = work.get("doi")
            url = doi or work.get("id")
            if not (title and abstract and url):
                continue

            location = work.get("primary_location") or {}
            venue = ((location.get("source") or {}).get("display_name")) or "OpenAlex"
            year = work.get("publication_year")
            citations = work.get("cited_by_count")

            publisher = venue + (f" ({year})" if year else "")
            if isinstance(citations, int):
                publisher += f" · {citations} citations"

            docs.append(
                RetrievedDoc(
                    title=title,
                    publisher=publisher,
                    url=url,
                    sourceType="academic",
                    snippet=abstract,
                ).truncated()
            )
        return docs
