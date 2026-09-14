"""Optional voice interfaces.

Browser speech APIs are used by the web UI; these small abstractions make the
availability/fallback contract explicit without making voice a server runtime
dependency.
"""

from .stt import SpeechToTextUnavailable, transcribe_browser_result
from .tts import TextToSpeechUnavailable, prepare_speech

__all__ = ["SpeechToTextUnavailable", "TextToSpeechUnavailable", "transcribe_browser_result", "prepare_speech"]
