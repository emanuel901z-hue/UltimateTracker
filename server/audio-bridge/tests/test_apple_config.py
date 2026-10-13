"""Unit-Tests der `config.ini`-Logik für macless-haystack (Apple-ID).

Regression: Ein Passwort mit `%` ließ das Speichern in der Bridge als HTTP 500
abstürzen – und danach auch das Lesen im Dienst (`configparser`-Interpolation).
Die Datei maskiert `%` deshalb als `%%`; der Verbraucher liest den Wert wörtlich.

Aufruf:  cd server/audio-bridge && python -m unittest discover -s tests -v
"""

import configparser
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

    def _as_consumer(self) -> configparser.ConfigParser:
        """So liest macless-haystack die Datei (Standard-Interpolation)."""
        parser = configparser.ConfigParser()
        parser.read(self.path, encoding="utf-8")
        return parser

    def test_read_missing_file(self) -> None:
        self.assertEqual(read_apple_id(self.path), "")

    def test_write_and_read_roundtrip(self) -> None:
        write_apple_credentials(self.path, "kind@example.com", "geheim-123", "http://anisette:6969")
        self.assertEqual(read_apple_id(self.path), "kind@example.com")
        self.assertEqual(self._as_consumer().get("Settings", "appleid"), "kind@example.com")
        self.assertEqual(self._as_consumer().get("Settings", "appleid_pass"), "geheim-123")

    def test_password_with_percent_is_readable_by_consumer(self) -> None:
        """'%' wird maskiert; der Verbraucher liest das Passwort wörtlich."""
        password = "KontrollSucht651%"
        write_apple_credentials(self.path, "kind@example.com", password, "http://anisette:6969")
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("KontrollSucht651%%", text)
        self.assertEqual(self._as_consumer().get("Settings", "appleid_pass"), password)
        self.assertEqual(read_apple_id(self.path), "kind@example.com")

    def test_read_handles_legacy_raw_percent(self) -> None:
        """Handgeschriebene Datei mit rohem '%' darf das Lesen nicht sprengen."""
        self.path.write_text(
            "[Settings]\nappleid = x@example.com\nappleid_pass = 50%Rabatt\n", encoding="utf-8"
        )
        self.assertEqual(read_apple_id(self.path), "x@example.com")

    def test_read_handles_raw_percent_in_appleid(self) -> None:
        self.path.write_text(
            "[Settings]\nappleid = a%b@example.com\n", encoding="utf-8"
        )
        self.assertEqual(read_apple_id(self.path), "a%b@example.com")

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
