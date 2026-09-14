from django.test import SimpleTestCase

from voice.stt import SpeechToTextUnavailable, transcribe_browser_result
from voice.tts import TextToSpeechUnavailable, prepare_speech


class VoiceFallbackTests(SimpleTestCase):
    def test_stt_requires_nonempty_browser_transcript(self):
        self.assertEqual(transcribe_browser_result("  my attendance  "), "my attendance")
        with self.assertRaises(SpeechToTextUnavailable):
            transcribe_browser_result("")

    def test_tts_has_safe_text_fallback(self):
        self.assertEqual(prepare_speech("Hello"), "Hello")
        with self.assertRaises(TextToSpeechUnavailable):
            prepare_speech(None)
