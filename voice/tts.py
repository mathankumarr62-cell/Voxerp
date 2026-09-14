"""Text-to-speech boundary for browser/client integrations."""
from __future__ import annotations


class TextToSpeechUnavailable(RuntimeError):
    """Raised when a client does not support speech synthesis."""


def prepare_speech(text: object, *, max_length: int = 4_000) -> str:
    """Return safe response text for a client-side TTS engine."""
    if not isinstance(text, str) or not text.strip():
        raise TextToSpeechUnavailable("No response text is available for speech")
    return text.strip()[:max_length]
