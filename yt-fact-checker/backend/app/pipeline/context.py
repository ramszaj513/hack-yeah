import re

from app.models.schemas import Context, VideoMetadata


KNOWN_COUNTRIES = {
    "united states": "United States",
    "u.s.": "United States",
    "america": "United States",
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom",
    "britain": "United Kingdom",
    "canada": "Canada",
    "australia": "Australia",
    "india": "India",
}


def resolve_context(claim: str, video: VideoMetadata) -> tuple[Context, bool]:
    text = f"{video.title} {video.description} {claim}".lower()
    country = next((label for token, label in KNOWN_COUNTRIES.items() if token in text), None)
    year = re.search(r"\b(?:18|19|20)\d{2}\b", text)
    timeframe = year.group(0) if year else None

    ambiguous_reference = re.search(r"\b(the government|the law|the economy|this country|they)\b", claim.lower())
    needs_context = bool(ambiguous_reference and not country)
    return Context(country=country, timeframe=timeframe), needs_context
