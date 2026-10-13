"""`config.ini` für macless-haystack lesen/schreiben (Apple-ID + Passwort).

Reine Datei-/Textlogik ohne FastAPI – host-testbar über
`tests/test_apple_config.py` (gleiche Idee wie `app/fusion.py`).

**Wichtig:** `configparser.ConfigParser` interpretiert `%` als Interpolation
(`%(name)s`). Der Verbraucher – macless-haystack, `endpoint/mh_config.py` – liest
die Datei mit der **Standard-Interpolation**. Ein Passwort mit `%` ließ daher
zuerst das Schreiben in der Bridge (HTTP 500) und danach auch das Lesen im Dienst
(„'%' must be followed by '%' or '('") abbrechen.

Deshalb wird `%` beim Schreiben als `%%` **maskiert**: so liest der Dienst den
Wert wörtlich, und `read_apple_id` (mit Interpolation) liefert ihn wieder korrekt
zurück.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path

SECTION = "Settings"


def _escape(value: str) -> str:
    """`%` maskieren, damit die Interpolation des Verbrauchers den Wert wörtlich liest."""
    return value.replace("%", "%%")


def read_apple_id(path: Path) -> str:
    """Apple-ID aus `config.ini` lesen (leerer String, wenn nichts hinterlegt).

    Erst wie der Verbraucher (mit Interpolation, löst `%%` auf); schlägt das fehl
    (z. B. handgeschriebene Datei mit rohem `%`), wird ohne Interpolation gelesen.
    """
    if not path.exists():
        return ""
    for parser in (configparser.ConfigParser(),
                   configparser.ConfigParser(interpolation=None)):
        try:
            parser.read(path, encoding="utf-8")
            if not parser.has_section(SECTION):
                return ""
            return parser.get(SECTION, "appleid", fallback="").strip()
        except (configparser.Error, OSError, UnicodeDecodeError):
            continue
    return ""


def write_apple_credentials(
    path: Path, appleid: str, password: str, anisette_url: str, port: int = 6176
) -> None:
    """Apple-Zugangsdaten schreiben; bestehende Einstellungen bleiben erhalten.

    Werte werden wörtlich gespeichert (`%` maskiert, siehe Modulkopf). Vorhandene
    Einstellungen (z. B. ein eigenes `anisette_url`) bleiben erhalten; Rechte 0600.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    parser = configparser.ConfigParser(interpolation=None)
    if path.exists():
        try:
            parser.read(path, encoding="utf-8")
        except (configparser.Error, OSError, UnicodeDecodeError):
            parser = configparser.ConfigParser(interpolation=None)
    if not parser.has_section(SECTION):
        parser.add_section(SECTION)
    parser.set(SECTION, "appleid", _escape(appleid))
    parser.set(SECTION, "appleid_pass", _escape(password))
    parser.set(SECTION, "anisette_url", _escape(anisette_url))
    parser.set(SECTION, "port", str(port))
    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
