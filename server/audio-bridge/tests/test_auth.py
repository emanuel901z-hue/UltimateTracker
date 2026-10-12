"""Unit-Tests für Benutzerkonten/Sitzungen (ohne Netzwerk).

Aufruf:  cd server/audio-bridge && python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.auth import (  # noqa: E402
    hash_password,
    new_session_token,
    password_problem,
    session_expiry,
    verify_password,
)


class TestPasswordHashing(unittest.TestCase):
    def test_roundtrip(self):
        stored = hash_password("ein-langes-passwort")
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password("ein-langes-passwort", stored))
        self.assertFalse(verify_password("falsch", stored))

    def test_salt_is_random(self):
        first = hash_password("gleiches-passwort")
        second = hash_password("gleiches-passwort")
        self.assertNotEqual(first, second)  # unterschiedliche Salts
        self.assertTrue(verify_password("gleiches-passwort", first))
        self.assertTrue(verify_password("gleiches-passwort", second))

    def test_rejects_broken_stored_values(self):
        for broken in ("", "kaputt", "pbkdf2_sha256$xyz$abc", "md5$aa$bb", None):
            self.assertFalse(verify_password("egal", broken))

    def test_known_vector_with_fixed_salt(self):
        # Reproduzierbar mit festem Salt (prüft das Format, nicht die Sicherheit)
        stored = hash_password("test-passwort-123", salt=bytes.fromhex("00112233445566778899aabbccddeeff"))
        self.assertEqual(stored, hash_password("test-passwort-123", salt=bytes.fromhex("00112233445566778899aabbccddeeff")))
        self.assertTrue(verify_password("test-passwort-123", stored))


class TestSessions(unittest.TestCase):
    def test_tokens_are_unique_and_long(self):
        tokens = {new_session_token() for _ in range(50)}
        self.assertEqual(len(tokens), 50)
        self.assertGreater(len(next(iter(tokens))), 30)

    def test_expiry_is_in_the_future_and_comparable(self):
        expiry = session_expiry()
        now = session_expiry(hours=0)
        self.assertGreater(expiry, now)  # ISO-Strings sind lexikografisch vergleichbar


class TestPasswordPolicy(unittest.TestCase):
    def test_accepts_reasonable_passwords(self):
        self.assertIsNone(password_problem("UltimateTracker-2026"))

    def test_rejects_short_or_weak(self):
        self.assertIsNotNone(password_problem("kurz"))
        self.assertIsNotNone(password_problem("passwort"))
        self.assertIsNotNone(password_problem("UltimateTracker"))  # in der Sperrliste


if __name__ == "__main__":
    unittest.main()
