"""Unit-Tests der `config.ini`-Logik für macless-haystack (Apple-ID).

Regression: Ein Passwort mit `%` ließ das Speichern mit
„invalid interpolation syntax" als HTTP 500 abstürzen.

Aufruf:  cd server/audio-bridge && python -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.apple_config import read_apple_id, write_apple_credentials  # noqa: E402


class AppleConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "config.ini"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_read_missing_file(self) -> None:
        self.assertEqual(read_apple_id(self.path), "")

    def test_write_and_read_roundtrip(self) -> None:
        write_apple_credentials(self.path, "kind@example.com", "geheim-123", "http://anisette:6969")
        self.assertEqual(read_apple_id(self.path), "kind@example.com")
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("[Settings]", text)
        self.assertIn("geheim-123", text)

    def test_password_with_percent(self) -> None:
        """'%' im Passwort darf nicht als Interpolation gedeutet werden."""
        password = "KontrollSucht651%"
        write_apple_credentials(self.path, "kind@example.com", password, "http://anisette:6969")
        self.assertEqual(read_apple_id(self.path), "kind@example.com")
        self.assertIn(password, self.path.read_text(encoding="utf-8"))

    def test_read_handles_percent_password(self) -> None:
        """Auch das Lesen darf an einem vorhandenen '%' nicht scheitern."""
        self.path.write_text(
            "[Settings]\nappleid = x@example.com\nappleid_pass = 50%Rabatt\n", encoding="utf-8"
        )
        self.assertEqual(read_apple_id(self.path), "x@example.com")

    def test_keeps_existing_settings(self) -> None:
        self.path.write_text(
            "[Settings]\nappleid = alt@example.com\nappleid_pass = alt\n"
            "anisette_url = http://eigen:1234\nextra = bleibt\n",
            encoding="utf-8",
        )
        write_apple_credentials(self.path, "neu@example.com", "neu", "http://anisette:6969")
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("extra = bleibt", text)
        self.assertIn("neu@example.com", text)
        self.assertEqual(read_apple_id(self.path), "neu@example.com")

    def test_rejects_garbage_file(self) -> None:
        self.path.write_text("kein ini\n", encoding="utf-8")
        self.assertEqual(read_apple_id(self.path), "")

    def test_creates_missing_directory(self) -> None:
        nested = Path(self._tmp.name) / "tief" / "drin" / "config.ini"
        write_apple_credentials(nested, "a@example.com", "p", "http://anisette:6969")
        self.assertEqual(read_apple_id(nested), "a@example.com")


if __name__ == "__main__":
    unittest.main()
