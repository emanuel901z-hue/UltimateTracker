"""Benutzerkonten und Sitzungen – nur Standardbibliothek, damit host-testbar.

Format der Passwort-Hashes: ``pbkdf2_sha256$<salt-hex>$<digest-hex>``
(PBKDF2-HMAC-SHA256, 120 000 Runden). Sitzungen sind zufällige Tokens mit
Ablaufdatum; sie liegen in der Bridge-Datenbank.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

PBKDF2_ROUNDS = 120_000
SESSION_HOURS = 24 * 30  # 30 Tage – Eltern sollen sich nicht ständig neu anmelden

WEAK_PASSWORDS = ("passwort", "password", "1234567890", "ultimatetracker")


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt_hex, digest_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ROUNDS
        )
    except (ValueError, AttributeError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_expiry(hours: int = SESSION_HOURS) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(timespec="seconds")


def password_problem(password: str) -> str | None:
    """Mindestanforderungen prüfen; ``None`` bedeutet in Ordnung."""
    if len(password) < 10:
        return "Passwort muss mindestens 10 Zeichen haben"
    if password.lower() in WEAK_PASSWORDS:
        return "Passwort ist zu einfach"
    return None
