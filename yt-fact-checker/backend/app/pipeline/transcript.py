from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from app.models.schemas import TranscriptSegment


class TranscriptUnavailable(Exception):
    """Raised when YouTube has no usable English caption track."""


def fetch_english_transcript(video_id: str) -> list[TranscriptSegment]:
    """Fetch timed English captions, including auto-generated tracks.

    Uses the no-key youtube-transcript-api library, which reads public YouTube
    caption tracks. It does not transcribe audio.
    """
    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(video_id, languages=["en", "en-US", "en-GB"])
    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as exc:
        raise TranscriptUnavailable(str(exc)) from exc

    segments = [
        TranscriptSegment(text=snippet.text, start=snippet.start, duration=snippet.duration)
        for snippet in fetched
        if snippet.text and snippet.text.strip()
    ]
    if not segments:
        raise TranscriptUnavailable("English caption track was empty.")
    return segments[:2000]
