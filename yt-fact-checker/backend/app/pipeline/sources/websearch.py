"""Open-web retrieval through the OpenAI web_search tool.

This runs as its own call per claim. That scoping is deliberate: citations
harvested from a response covering several claims cannot be attributed to any
one of them, and attaching them to all of them invents evidence.
"""

from __future__ import annotations

from app.config import settings
from app.pipeline.llm import LLMUnavailable, structured_call
from app.pipeline.sources.base import ClaimContext, RetrievedDoc


SEARCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sources"],
    "properties": {
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "publisher", "url", "quote", "source_type"],
                "properties": {
                    "title": {"type": "string"},
                    "publisher": {"type": "string"},
                    "url": {"type": "string"},
                    "quote": {
                        "type": "string",
                        "description": "Sentence copied verbatim from the page that bears on the claim.",
                    },
                    "source_type": {
                        "type": "string",
                        "enum": ["primary", "academic", "fact_checker", "journalism", "reference", "web"],
                    },
                },
            },
        }
    },
}


PROMPT = """Search the web for evidence that bears on this claim. Gather sources; do not judge the claim yet.

Claim: {claim}
{context}

Requirements:
- Return up to 6 sources that directly address the claim.
- If the claim names a date or period, search for THAT date explicitly, and
  prefer reporting published on or after it. An institution's own standing
  pages often predate the event and will describe the situation before it —
  treating those as current is how a true report of a recent event gets called
  false. Search news for the event, not just the organisation's website.
- If the claim compares two things ("older than", "more than", "before"), search
  for EACH side separately and return sources for both. A source covering only
  one half leaves the comparison unanswerable.
- Prefer primary sources (official statistics, government and institutional
  publications, regulatory filings, court documents), then peer-reviewed
  research, then established fact-checkers and reputable news.
- Deliberately include sources that CONTRADICT the claim if they exist. A
  one-sided source list is a failure, not a success.
- `quote` must be copied verbatim from the page. Never paraphrase it.
- `url` must be the real page you read, not a search-results page.
"""


class WebSearchSource:
    name = "web_search"

    @property
    def available(self) -> bool:
        config = settings()
        return config.llm_enabled and config.enable_web_search

    async def fetch(self, context: ClaimContext) -> list[RetrievedDoc]:
        if not self.available:
            return []

        extras = []
        if context.country:
            extras.append(f"Country: {context.country}")
        if context.timeframe:
            extras.append(f"Timeframe: {context.timeframe}")

        prompt = PROMPT.format(claim=context.claim, context="\n".join(extras))

        try:
            payload, grounded = await structured_call(
                prompt=prompt,
                schema_name="evidence_search",
                schema=SEARCH_SCHEMA,
                web_search=True,
                max_output_tokens=2500,
                cache_key="ytfc-search",
            )
        except LLMUnavailable:
            return []

        allowed = set(grounded)
        docs: list[RetrievedDoc] = []
        for item in payload.get("sources", []) or []:
            url = (item.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            # When the tool reported citations, keep the model honest by
            # preferring URLs it actually visited.
            if allowed and url not in allowed:
                continue
            docs.append(
                RetrievedDoc(
                    title=(item.get("title") or url)[:300],
                    publisher=(item.get("publisher") or "Web")[:200],
                    url=url,
                    sourceType=item.get("source_type") or "web",
                    snippet=item.get("quote") or "",
                    modelReported=True,
                ).truncated()
            )
        return docs
