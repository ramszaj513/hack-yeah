from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from app.config import settings
from app.models.schemas import TranscriptSegment


class TranscriptUnavailable(Exception):
    """Raised when YouTube has no usable caption track."""


PREFERRED = ["en", "en-US", "en-GB"]


def fetch_english_transcript(video_id: str) -> list[TranscriptSegment]:
    """Fetch timed captions, preferring English but accepting any track.

    Uses the no-key youtube-transcript-api library, which reads public caption
    tracks. It does not transcribe audio.

    Note: YouTube blocks many datacenter IPs, so this server-side path is
    unreliable once deployed. The extension fetches captions in the viewer's
    own browser session and posts them with the request; this is the fallback
    for when it could not.
    """
    api = YouTubeTranscriptApi()

    try:
        fetched = api.fetch(video_id, languages=PREFERRED)
    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as exc:
        try:
            available = list(api.list(video_id))
        except Exception:
            raise TranscriptUnavailable(str(exc)) from exc

        if not available:
            raise TranscriptUnavailable("No caption track is available for this video.") from exc

        chosen = next((item for item in available if getattr(item, "language_code", "").startswith("en")), available[0])
        try:
            fetched = chosen.fetch()
        except Exception as inner:
            raise TranscriptUnavailable(str(inner)) from inner

    segments = [
        TranscriptSegment(text=snippet.text, start=snippet.start, duration=snippet.duration)
        for snippet in fetched
        if snippet.text and snippet.text.strip()
    ]
    if not segments:
        raise TranscriptUnavailable("The caption track was empty.")
    return segments[: settings().max_transcript_segments]
