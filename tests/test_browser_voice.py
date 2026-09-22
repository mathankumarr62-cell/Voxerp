"""Run the actual dashboard JavaScript with controlled browser boundaries, offline."""
from pathlib import Path
import shutil
import subprocess
import unittest


class BrowserVoiceTests(unittest.TestCase):
    def test_dashboard_voice_lifecycle(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node.js is required for the browser voice regression tests.')
        result = subprocess.run(
            [node, '--test', str(Path(__file__).with_name('browser_voice.test.cjs'))],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
