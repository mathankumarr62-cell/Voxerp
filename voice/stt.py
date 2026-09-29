"""Speech-to-text boundary for browser/client integrations."""
from __future__ import annotations

import re


class SpeechToTextUnavailable(RuntimeError):
    """Raised when no STT provider is available; callers must offer text input."""


def transcribe_browser_result(transcript: object) -> str:
    """Validate a browser-provided transcript without treating it as trusted data."""
    if not isinstance(transcript, str) or not transcript.strip():
        raise SpeechToTextUnavailable("No speech transcript was provided")
    return normalize_course_codes(transcript.strip())


_DIGITS = dict(zip("zero one two three four five six seven eight nine".split(), "0123456789"))
_DIGIT_TOKEN = r"(?:[0-9]|" + "|".join(_DIGITS) + r")"
_COURSE_CODE = re.compile(
    r"\b([A-Za-z]{2,4}|[A-Za-z](?:\s+[A-Za-z]){1,3})\s*"
    r"(" + _DIGIT_TOKEN + r"(?:\s*" + _DIGIT_TOKEN + r"){3,5})(?![\w])",
    re.IGNORECASE,
)


def normalize_course_codes(text: str) -> str:
    """Join bounded letter prefixes and 4–6 spoken/digit code suffixes."""
    def replace(match):
        if re.fullmatch(r"[A-Za-z]{2,4}[0-9]{4,6}", match[0]):
            return match[0]
        prefix = re.sub(r"\s+", "", match[1]).upper()
        digits = re.findall(_DIGIT_TOKEN, match[2].lower())
        return prefix + "".join(_DIGITS.get(token, token) for token in digits)
    return _COURSE_CODE.sub(replace, text)
