"""Speech-to-text boundary for browser/client integrations."""
from __future__ import annotations


class SpeechToTextUnavailable(RuntimeError):
    """Raised when no STT provider is available; callers must offer text input."""


def transcribe_browser_result(transcript: object) -> str:
    """Validate a browser-provided transcript without treating it as trusted data."""
    if not isinstance(transcript, str) or not transcript.strip():
        raise SpeechToTextUnavailable("No speech transcript was provided")
    return transcript.strip()
