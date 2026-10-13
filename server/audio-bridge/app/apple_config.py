"""`config.ini` für macless-haystack lesen/schreiben (Apple-ID + Passwort).

Reine Datei-/Textlogik ohne FastAPI – host-testbar über
`tests/test_apple_config.py` (gleiche Idee wie `app/fusion.py`).

**Wichtig:** `configparser.ConfigParser` interpretiert `%` als Interpolation
(`%(name)s`). Ein Passwort mit `%` ließ das Schreiben bisher mit
„invalid interpolation syntax" abstürzen (HTTP 500). Deshalb hier überall
`interpolation=None` – die Werte werden wörtlich übernommen.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path

SECTION = "Settings"


def _parser() -> configparser.ConfigParser:
    return configparser.ConfigParser(interpolation=None)


def read_apple_id(path: Path) -> str:
    """Apple-ID aus `config.ini` lesen (leerer String, wenn nichts hinterlegt)."""
    if not path.exists():
        return ""
    parser = _parser()
    try:
        parser.read(path, encoding="utf-8")
        if not parser.has_section(SECTION):
            return ""
        return parser.get(SECTION, "appleid", fallback="").strip()
    except (configparser.Error, OSError, UnicodeDecodeError):
        return ""


def write_apple_credentials(
    path: Path, appleid: str, password: str, anisette_url: str, port: int = 6176
) -> None:
    """Apple-Zugangsdaten schreiben; bestehende Einstellungen bleiben erhalten.

    Vorhandene Werte (z. B. ein bereits gesetztes `anisette_url`) werden
    beibehalten, nur die hier gesetzten Schlüssel ändern sich. Rechte 0600.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    parser = _parser()
    if path.exists():
        try:
            parser.read(path, encoding="utf-8")
        except (configparser.Error, OSError, UnicodeDecodeError):
            parser = _parser()
    if not parser.has_section(SECTION):
        parser.add_section(SECTION)
    parser.set(SECTION, "appleid", appleid)
    parser.set(SECTION, "appleid_pass", password)
    parser.set(SECTION, "anisette_url", anisette_url)
    parser.set(SECTION, "port", str(port))
    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
