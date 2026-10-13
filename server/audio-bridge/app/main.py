"""Audio-Bridge – Sprachnachrichten, Geräte-Registry, Find-My-Ingest und Sync.

Endpunkte und Datenmodell: docs/architecture.md (Abschnitt 3).
Konfiguration über Umgebungsvariablen (siehe server/.env.example).
"""

from __future__ import annotations

import asyncio
import configparser
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
import urllib.parse
import urllib.request
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

START_TIME = time.time()

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.auth import (  # noqa: E402
    hash_password,
    new_session_token,
    password_problem,
    session_expiry,
    verify_password,
)
from app.fusion import (  # noqa: E402
    SOURCE_TRUST,
    choose_best,
    movement_state,
    source_trust,
    source_valid_seconds,
)
from app.providers import get_provider

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
AUDIO_DIR = DATA_DIR / "audio"
FIRMWARE_DIR = DATA_DIR / "firmware"
DB_PATH = DATA_DIR / "bridge.sqlite3"
EVENTS_LOG = DATA_DIR / "events.jsonl"
STATIC_DIR = Path(__file__).parent / "static"


def env_int(name: str, default: int) -> int:
    """Zahlen-Env robust lesen: leer/unbrauchbar ⇒ Default (statt Crash)."""
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[config] {name}={raw!r} ungültig – nutze Default {default}", flush=True)
        return default


def env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"[config] {name}={raw!r} ungültig – nutze Default {default}", flush=True)
        return default


DEVICE_TOKEN = os.environ.get("DEVICE_TOKEN", "")
PARENT_TOKEN = os.environ.get("PARENT_TOKEN", "")
WEBHOOK_TOKEN = os.environ.get("TRACCAR_WEBHOOK_TOKEN", "")
FINDMY_TOKEN = os.environ.get("FINDMY_TOKEN", "")
TRACCAR_FORWARD_URL = os.environ.get("TRACCAR_FORWARD_URL", "")
# Kartenkacheln für die eingebaute Karte (Leaflet). Standard: OpenStreetMap –
# wer keine externen Aufrufe will, zeigt MAP_TILES auf einen eigenen Kachelserver.
MAP_TILES = os.environ.get("MAP_TILES", "https://tile.openstreetmap.org/{z}/{x}/{y}.png").strip()
MAP_ATTRIBUTION = os.environ.get("MAP_ATTRIBUTION", "© OpenStreetMap-Mitwirkende").strip()
# Automatische Traccar-Anmeldung (Single Sign-on): Zugangsdaten des Traccar-Kontos.
# Leer = kein Auto-Login (Traccar fragt dann selbst).
TRACCAR_SSO_EMAIL = os.environ.get("TRACCAR_SSO_EMAIL", "").strip()
TRACCAR_SSO_PASSWORD = os.environ.get("TRACCAR_SSO_PASSWORD", "").strip()
SEARCH_MODE_MINUTES = env_int("SEARCH_MODE_MINUTES", 30)
MAX_UPLOAD_MB = env_float("MAX_UPLOAD_MB", 2.0)
RETENTION_DAYS = env_int("RETENTION_DAYS", 30)
APPRISE_URLS = os.environ.get("APPRISE_URLS", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:admin@example.org")

# SIM-/SMS-Anbieter (anbieterneutral, docs/sim-providers.md):
#   SIM_PROVIDER        = nce | whereversim | generic | none
#   SIM_PROVIDER_CONFIG = Pfad zu einer JSON-Konfiguration für "generic"
#   SMS_SUBSCRIBE       = 1 → Echtzeit-SMS des Anbieters abonnieren (falls unterstützt)
SMS_SUBSCRIBE = os.environ.get("SMS_SUBSCRIBE", "").strip().lower() in ("1", "true", "yes", "on")
POLL_INTERVAL_S = env_int("POLL_INTERVAL_S", 900)
SEARCH_POLL_INTERVAL_S = env_int("SEARCH_POLL_INTERVAL_S", 60)

# Zielformate (siehe docs/decisions.md D-002: 8 kHz mono, IMA-ADPCM für den Tracker)
FMT_DEVICE = ["-c:a", "adpcm_ima_wav", "-ar", "8000", "-ac", "1"]
FMT_PARENT = ["-c:a", "libmp3lame", "-b:a", "48k", "-ar", "8000", "-ac", "1"]


# --- Datenbank --------------------------------------------------------------


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    FIRMWARE_DIR.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS messages (
                   id TEXT PRIMARY KEY,
                   direction TEXT NOT NULL CHECK (direction IN ('in', 'out')),
                   device_id TEXT NOT NULL,
                   created_at TEXT NOT NULL,
                   status TEXT NOT NULL DEFAULT 'new',
                   raw_file TEXT NOT NULL,
                   play_file TEXT NOT NULL,
                   duration_ms INTEGER,
                   note TEXT
               )"""
        )
        conn.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS devices (
                   id TEXT PRIMARY KEY,
                   name TEXT NOT NULL DEFAULT '',
                   imei TEXT NOT NULL DEFAULT '',
                   msisdn TEXT NOT NULL DEFAULT '',
                   notes TEXT NOT NULL DEFAULT '',
                   created_at TEXT NOT NULL
               )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS findmy_locations (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   provider TEXT NOT NULL,
                   beacon_id TEXT NOT NULL,
                   latitude REAL NOT NULL,
                   longitude REAL NOT NULL,
                   accuracy REAL,
                   reported_at TEXT,
                   received_at TEXT NOT NULL,
                   raw TEXT
               )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS positions (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   device_id TEXT NOT NULL,
                   latitude REAL NOT NULL,
                   longitude REAL NOT NULL,
                   accuracy REAL,
                   battery REAL,
                   source TEXT NOT NULL DEFAULT 'tracker',
                   reported_at TEXT,
                   received_at TEXT NOT NULL
               )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS firmware (
                   version TEXT PRIMARY KEY,
                   filename TEXT NOT NULL,
                   sha256 TEXT NOT NULL,
                   size INTEGER NOT NULL,
                   notes TEXT NOT NULL DEFAULT '',
                   uploaded_at TEXT NOT NULL
               )"""
        )


        conn.execute(
            """CREATE TABLE IF NOT EXISTS push_subscriptions (
                   endpoint TEXT PRIMARY KEY,
                   p256dh TEXT NOT NULL,
                   auth TEXT NOT NULL,
                   created_at TEXT NOT NULL
               )"""
        )
        # Migration: ICCID für die 1NCE-Zuordnung (SIM ↔ Gerät)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(devices)")}
        if "iccid" not in columns:
            conn.execute("ALTER TABLE devices ADD COLUMN iccid TEXT NOT NULL DEFAULT ''")
        # Per Echtzeit-Subscription empfangene SMS (docs/sim-providers.md)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS sim_sms (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   iccid TEXT NOT NULL DEFAULT '',
                   direction TEXT NOT NULL DEFAULT '',
                   originator TEXT NOT NULL DEFAULT '',
                   text TEXT NOT NULL DEFAULT '',
                   received_at TEXT NOT NULL
               )"""
        )
        # Benutzerkonten + Sitzungen (Login für die Eltern-UI)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   username TEXT UNIQUE NOT NULL,
                   password_hash TEXT NOT NULL,
                   role TEXT NOT NULL DEFAULT 'parent',
                   created_at TEXT NOT NULL
               )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                   token TEXT PRIMARY KEY,
                   user_id INTEGER NOT NULL,
                   created_at TEXT NOT NULL,
                   expires_at TEXT NOT NULL
               )"""
        )
        # Migrationen (idempotent): Spalten für neuere Installationen ergänzen
        message_columns = {row["name"] for row in conn.execute("PRAGMA table_info(messages)")}
        if "listened_at" not in message_columns:
            conn.execute("ALTER TABLE messages ADD COLUMN listened_at TEXT")
        # Zuordnung Find-My-Beacon → Kind (Sensor-Fusion, docs/fusion.md)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS beacons (
                   beacon_id TEXT PRIMARY KEY,
                   provider TEXT NOT NULL DEFAULT '',
                   device_id TEXT NOT NULL,
                   created_at TEXT NOT NULL
               )"""
        )


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def state_get(key: str) -> str | None:
    with db() as conn:
        row = conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def state_set(key: str, value: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO state(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def search_mode_active(device_id: str | None = None) -> bool:
    """Suchmodus – pro Gerät (mehrere Kinder!), mit Fallback auf den globalen Wert."""
    keys = [f"search_mode_until:{device_id}"] if device_id else []
    keys.append("search_mode_until")
    for key in keys:
        until = state_get(key)
        if until and float(until) > time.time():
            return True
    return False


def next_poll_seconds(battery: float | None = None, device_id: str | None = None) -> int:
    """Server-getriebenes Poll-Intervall (docs/optimizations.md A5/B4)."""
    if search_mode_active(device_id):
        return setting("search_poll_interval_s")
    if battery is not None and battery < setting("low_battery_percent"):
        return setting("poll_interval_s") * 2
    return setting("poll_interval_s")


def ensure_device(device_id: str) -> None:
    """Unbekannte Geräte automatisch anlegen (analog Traccar registerUnknown)."""
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO devices(id, name, created_at) VALUES(?, ?, ?)",
            (device_id, device_id, now_iso()),
        )


def validate_config() -> None:
    """Sanity-Check beim Start.

    Tokens müssen **nicht** mehr vorbereitet werden: fehlen sie (oder stehen
    noch Platzhalter in der .env), erzeugt die Bridge sie beim ersten Zugriff
    selbst und legt sie in der Datenbank ab – Erststart ohne Terminal.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DEVICE_TOKEN or DEVICE_TOKEN.startswith("change-me"):
        print("[setup] DEVICE_TOKEN fehlt – wird automatisch erzeugt", flush=True)
    if not PARENT_TOKEN or PARENT_TOKEN.startswith("change-me"):
        print("[setup] PARENT_TOKEN fehlt – wird automatisch erzeugt", flush=True)


# --- Auth -------------------------------------------------------------------


def token_ok(expected: str, provided: str | None) -> bool:
    return bool(expected) and provided is not None and secrets.compare_digest(expected, provided)


# --- Single Sign-on (Cookie für Caddy forward_auth) -------------------------

COOKIE_NAME = "ut_session"
# Optional: Cookie-Domain für SSO über Subdomains (z. B. ".example.org").
# Für *.localhost wird automatisch "localhost" gesetzt (deckt audio./traccar./…).
COOKIE_DOMAIN = os.environ.get("SESSION_COOKIE_DOMAIN", "").strip()


def request_is_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return proto.split(",")[0].strip() == "https"


def cookie_domain(request: Request) -> str | None:
    if COOKIE_DOMAIN:
        return COOKIE_DOMAIN
    host = (request.headers.get("host") or "").split(":")[0]
    if host == "localhost" or host.endswith(".localhost"):
        # Deckt localhost UND *.localhost ab – damit gilt die Anmeldung auch,
        # wenn die UI über den Direktport geöffnet wurde.
        return "localhost"
    return None  # Standard: Host-Cookie (reicht bei gleichem Host, anderem Port)


def session_token(request: Request, header_token: str | None = None) -> str:
    """Sitzungstoken aus Header (UI/API) oder Cookie (SSO)."""
    return (header_token or "").strip() or request.cookies.get(COOKIE_NAME, "")


def require_device(x_auth_token: str | None = Header(default=None)) -> None:
    if not token_ok(device_token(), x_auth_token):
        raise HTTPException(status_code=401, detail="Ungültiges Device-Token")


def users_count() -> int:
    with db() as conn:
        return int(conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])


# --- Automatische Ersteinrichtung (ohne Terminal) ---------------------------
# Ziel: „docker compose up -d" + Browser öffnen – fertig. Fehlen Tokens in der
# .env, erzeugt die Bridge sie selbst und legt sie in der Datenbank ab. Den
# Traccar-Administrator legt sie ebenfalls selbst an, solange Traccar noch
# keinen Benutzer hat (Traccar erlaubt die Registrierung genau dann).


def stored_secret(key: str, env_value: str) -> str:
    existing = state_get(f"secret:{key}")
    if existing:
        return existing
    value = (env_value or "").strip()
    if not value or value.startswith("change-me"):
        value = secrets.token_hex(24)
        print(f"[setup] {key}-Token automatisch erzeugt (keine Datei nötig)", flush=True)
    state_set(f"secret:{key}", value)
    return value


def device_token() -> str:
    return stored_secret("device", DEVICE_TOKEN)


def parent_token() -> str:
    return stored_secret("parent", PARENT_TOKEN)


_traccar_admin = {"checked_at": 0.0, "value": None}


def traccar_credentials() -> tuple[str, str]:
    """Zugangsdaten des Traccar-Kontos (aus der Einrichtung oder der .env)."""
    email = state_get("traccar:email") or TRACCAR_SSO_EMAIL
    password = state_get("traccar:password") or TRACCAR_SSO_PASSWORD
    return email, password


def ensure_traccar_admin(force: bool = False) -> dict:
    """Traccar-Administrator anlegen, wenn noch keiner existiert (max. 1×/Minute)."""
    email, password = traccar_credentials()
    if email and password:
        return {"email": email, "password": password, "created": False, "configured": True}
    now = time.time()
    if not force and _traccar_admin["value"] is not None and now - _traccar_admin["checked_at"] < 60:
        return _traccar_admin["value"]

    candidate_email = "admin@ultimatetracker.local"
    candidate_password = "UT-" + secrets.token_urlsafe(12)
    payload = json.dumps({
        "name": "Administrator", "email": candidate_email, "password": candidate_password,
    }).encode()
    request = urllib.request.Request(
        "http://traccar:8082/api/users", data=payload,
        headers={"Content-Type": "application/json"},
    )
    result = {"email": "", "password": "", "created": False, "configured": False}
    try:
        with urllib.request.urlopen(request, timeout=8):
            state_set("traccar:email", candidate_email)
            state_set("traccar:password", candidate_password)
            print(f"[setup] Traccar-Administrator angelegt: {candidate_email}", flush=True)
            result = {"email": candidate_email, "password": candidate_password,
                      "created": True, "configured": True}
    except urllib.error.HTTPError as exc:
        # 400 = "Registration disabled" → es gibt schon ein Konto (kein Fehler)
        print(f"[setup] Traccar-Registrierung nicht nötig/erlaubt (HTTP {exc.code})", flush=True)
    except Exception as exc:
        print(f"[setup] Traccar nicht erreichbar: {exc!r}", flush=True)
    _traccar_admin.update({"checked_at": now, "value": result})
    return result


def session_user(token: str | None) -> dict | None:
    """Angemeldeten Benutzer zu einem Sitzungstoken liefern (None = ungültig)."""
    if not token:
        return None
    with db() as conn:
        row = conn.execute(
            "SELECT s.expires_at, u.id, u.username, u.role FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE s.token = ?",
            (token,),
        ).fetchone()
    if row is None:
        return None
    if row["expires_at"] < now_iso():  # ISO-Strings sind vergleichbar (UTC)
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        return None
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


def require_parent(request: Request, x_auth_token: str | None = Header(default=None)) -> None:
    """Zugang für Eltern: Sitzungstoken (Header **oder** Cookie) oder API-Token."""
    token = session_token(request, x_auth_token)
    if token_ok(parent_token(), token) or session_user(token) is not None:
        return
    raise HTTPException(status_code=401, detail="Nicht angemeldet")


def require_admin(x_auth_token: str | None = Header(default=None)) -> dict:
    """Nur Administratoren (Benutzerverwaltung). Der API-Token gilt als Admin."""
    if token_ok(parent_token(), x_auth_token):
        return {"id": 0, "username": "token", "role": "admin"}
    user = session_user(x_auth_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Nicht angemeldet")
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Nur für Administratoren")
    return user


def ensure_admin_user() -> None:
    """Ersten Administrator aus PARENT_USER/PARENT_PASSWORD anlegen (falls leer)."""
    with db() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    if count > 0:
        return
    username = (os.environ.get("PARENT_USER") or "admin").strip() or "admin"
    password = (os.environ.get("PARENT_PASSWORD") or "").strip()
    if not password:
        print("[auth] Noch kein Benutzer und PARENT_PASSWORD nicht gesetzt – "
              "Anmeldung per API-Token möglich, Benutzer über die UI/API anlegen", flush=True)
        return
    problem = password_problem(password)
    if problem:
        print(f"[auth] PARENT_PASSWORD abgelehnt: {problem}", flush=True)
        return
    with db() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES(?, ?, 'admin', ?)",
            (username, hash_password(password), now_iso()),
        )
    print(f"[auth] Administrator '{username}' angelegt", flush=True)


# --- Audio-Hilfsfunktionen --------------------------------------------------


def convert(src: Path, dst: Path, fmt: list[str]) -> bool:
    """Konvertiert per ffmpeg; False, wenn ffmpeg fehlt oder scheitert."""
    if not shutil.which("ffmpeg"):
        return False
    try:
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), *fmt, str(dst)],
            check=True,
            timeout=120,
        )
        return True
    except (subprocess.SubprocessError, OSError):
        return False


async def store_upload(upload: UploadFile, msg_id: str) -> Path:
    """Speichert den Upload mit Größenlimit (docs/optimizations.md A6)."""
    limit = int(MAX_UPLOAD_MB * 1024 * 1024)
    path = AUDIO_DIR / f"{msg_id}-raw"
    size = 0
    with path.open("wb") as fh:
        while True:
            chunk = await upload.read(64 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                fh.close()
                path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413, detail=f"Upload zu groß (>{MAX_UPLOAD_MB} MB)"
                )
            fh.write(chunk)
    return path


def insert_message(
    msg_id: str, direction: str, device_id: str, raw: Path, play: Path, duration_ms: int | None
) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO messages(id, direction, device_id, created_at, raw_file, play_file, duration_ms) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (msg_id, direction, device_id, now_iso(), raw.name, play.name, duration_ms),
        )


# --- Benachrichtigungen (Apprise) -------------------------------------------


def notify(title: str, body: str) -> None:
    """Sendet eine Benachrichtigung über die konfigurierten APPRISE_URLS."""
    if not APPRISE_URLS:
        return
    try:
        import apprise  # lokal importiert, damit Apprise optional bleibt
    except ImportError:
        print("[notify] apprise nicht installiert – Benachrichtigung übersprungen", flush=True)
        return
    ap = apprise.Apprise()
    for url in APPRISE_URLS.split(","):
        url = url.strip()
        if url:
            ap.add(url)
    try:
        ok = ap.notify(title=title, body=body)
        print(f"[notify] {title}: {'ok' if ok else 'fehlgeschlagen'}", flush=True)
    except Exception as exc:  # Benachrichtigungsfehler dürfen nie den Request killen
        print(f"[notify] Fehler: {exc!r}", flush=True)


def notify_async(title: str, body: str) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    asyncio.create_task(asyncio.to_thread(notify, title, body))


# --- Web-Push (VAPID, PWA) --------------------------------------------------


def get_vapid_keys() -> tuple[str, str]:
    """VAPID-Schlüssel aus dem Zustandsspeicher; beim ersten Aufruf erzeugen."""
    private_pem = state_get("vapid_private_pem")
    public_b64 = state_get("vapid_public_b64")
    if private_pem and public_b64:
        return private_pem, public_b64
    try:
        import base64

        from cryptography.hazmat.primitives import serialization
        from py_vapid import Vapid01
    except ImportError as exc:
        raise RuntimeError("pywebpush/py_vapid nicht installiert") from exc

    vapid = Vapid01()
    vapid.generate_keys()
    private_pem = vapid.private_pem().decode()
    raw = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    public_b64 = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    state_set("vapid_private_pem", private_pem)
    state_set("vapid_public_b64", public_b64)
    return private_pem, public_b64


def push_subscription_count() -> int:
    with db() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM push_subscriptions").fetchone()
    return int(row["n"])


def send_push(title: str, body: str) -> dict:
    """Sendet eine Web-Push-Nachricht an alle registrierten Browser-Abos."""
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        print("[push] pywebpush nicht installiert – übersprungen", flush=True)
        return {"sent": 0, "removed": 0, "error": "pywebpush fehlt"}
    try:
        private_pem, _ = get_vapid_keys()
    except Exception as exc:
        print(f"[push] VAPID nicht verfügbar: {exc!r}", flush=True)
        return {"sent": 0, "removed": 0, "error": str(exc)}

    payload = json.dumps({"title": title, "body": body})
    with db() as conn:
        rows = conn.execute("SELECT endpoint, p256dh, auth FROM push_subscriptions").fetchall()

    sent = 0
    stale: list[str] = []
    for row in rows:
        info = {
            "endpoint": row["endpoint"],
            "keys": {"p256dh": row["p256dh"], "auth": row["auth"]},
        }
        try:
            webpush(
                subscription_info=info,
                data=payload,
                vapid_private_key=private_pem,
                vapid_claims={"sub": VAPID_SUBJECT},
                timeout=10,
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            print(f"[push] Fehler (HTTP {status}): {exc!r}", flush=True)
            if status in (404, 410):
                stale.append(row["endpoint"])  # Abo ist nicht mehr gültig
        except Exception as exc:
            print(f"[push] Fehler: {exc!r}", flush=True)

    if stale:
        with db() as conn:
            for endpoint in stale:
                conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
    return {"sent": sent, "removed": len(stale), "total": len(rows)}


def push_async(title: str, body: str) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    asyncio.create_task(asyncio.to_thread(send_push, title, body))


# --- Laufzeit-Einstellungen (Operationszentrale) -----------------------------
# Überschreiben die .env-Defaults zur Laufzeit (ohne Neustart). Gespeichert in
# der state-Tabelle, damit sie Backups/Umzüge überleben.

SETTING_DEFS = {
    "poll_interval_s": {"default": POLL_INTERVAL_S, "min": 60, "max": 86400, "label": "Poll-Intervall (Normalbetrieb), Sekunden"},
    "search_poll_interval_s": {"default": SEARCH_POLL_INTERVAL_S, "min": 15, "max": 600, "label": "Poll-Intervall im Suchmodus, Sekunden"},
    "search_mode_minutes": {"default": SEARCH_MODE_MINUTES, "min": 1, "max": 720, "label": "Standarddauer Suchmodus, Minuten"},
    "retention_days": {"default": RETENTION_DAYS, "min": 0, "max": 3650, "label": "Aufbewahrung Audionachrichten, Tage (0 = nie löschen)"},
    "low_battery_percent": {"default": 15, "min": 0, "max": 100, "label": "Akkuschwelle für längeres Poll-Intervall, Prozent"},
    "notify_new_message": {"default": 1, "min": 0, "max": 1, "label": "Bei neuer Nachricht benachrichtigen (1/0)"},
}

_settings_cache = {"value": None, "expires_at": 0.0}


def settings_all() -> dict:
    now = time.time()
    if _settings_cache["value"] is not None and _settings_cache["expires_at"] > now:
        return _settings_cache["value"]
    values = {}
    with db() as conn:
        rows = conn.execute("SELECT key, value FROM state WHERE key LIKE 'setting:%'").fetchall()
    stored = {row["key"][len("setting:"):]: row["value"] for row in rows}
    for name, spec in SETTING_DEFS.items():
        raw = stored.get(name)
        try:
            value = int(raw) if raw is not None else int(spec["default"])
        except (TypeError, ValueError):
            value = int(spec["default"])
        values[name] = max(spec["min"], min(spec["max"], value))
    _settings_cache["value"] = values
    _settings_cache["expires_at"] = now + 5
    return values


def setting(name: str) -> int:
    return settings_all().get(name, int(SETTING_DEFS[name]["default"]))


def settings_update(values: dict) -> dict:
    with db() as conn:
        for name, raw in values.items():
            spec = SETTING_DEFS.get(name)
            if spec is None:
                continue
            try:
                value = int(raw)
            except (TypeError, ValueError):
                continue
            value = max(spec["min"], min(spec["max"], value))
            conn.execute(
                "INSERT INTO state(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (f"setting:{name}", str(value)),
            )
    _settings_cache["value"] = None  # Cache verwerfen
    return settings_all()


# --- Dienste-Übersicht („eine App": Status + Links aller Dienste) -----------

# key, Anzeigename, Beschreibung, interner Host:Port, Port nach außen, SITE_*-Variable
SERVICE_DEFS = [
    ("bridge", "Eltern-UI/API", "Nachrichten, Status, Suchmodus, Geräte",
     "audio-bridge:8085", 8085, "SITE_AUDIO"),
    ("traccar", "Karte (Traccar)", "Positionen, Geofences, Verlauf",
     "traccar:8082", 8082, "SITE_TRACCAR"),
    ("google-findmy", "Google Find My", "Find-Hub-WebUI: Beacons, Scheduling",
     "google-findmy-webui:4321", 4321, "SITE_FINDMY"),
    ("apple-findmy", "Apple Find My", "macless-haystack: Beacons, Schlüssel",
     "macless-haystack:6176", 6176, "SITE_APPLE"),
    ("anisette", "Apple-Auth-Dienst", "Anisette (für die Apple-Bridge)",
     "anisette:6969", 6969, None),
    ("findmy-bridge", "Apple → Traccar", "automatische Beacon-Synchronisation",
     None, None, None),
]

_services_cache = {"value": None, "expires_at": 0.0}

# Dienste ohne veröffentlichten Port: nur intern erreichbar, kein Link in der UI
INTERNAL_SERVICES = {"anisette", "findmy-bridge"}
# Kurze Hinweise, was bei einem Dienst noch zu tun ist
SERVICE_HINTS = {
    "apple-findmy": "Apple-ID hinterlegen (docs/findmy.md)",
    "google-findmy": "Google-Anmeldung in der WebUI (einmalig)",
}


def probe_http(host: str, port: int, path: str = "/", timeout: float = 2.0) -> str:
    """Erreichbarkeit prüfen: 'up' (auch bei 401/404 – Hauptsache, es antwortet)."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=timeout) as response:
            return "up" if response.status < 500 else "error"
    except urllib.error.HTTPError as exc:
        return "up" if exc.code < 500 else "error"
    except Exception:
        return "down"


# --- SIM-Provider (anbieterneutral) -----------------------------------------

_sim_provider = None
_sim_provider_loaded = False


def load_provider_config() -> dict | None:
    """JSON-Konfiguration für den Generic-Provider (SIM_PROVIDER_CONFIG)."""
    path = os.environ.get("SIM_PROVIDER_CONFIG", "").strip()
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        print(f"[provider] Konfiguration nicht gefunden: {path}", flush=True)
    except json.JSONDecodeError as exc:
        print(f"[provider] Konfiguration ist kein gültiges JSON: {exc}", flush=True)
    return None


def sim_provider():
    """Provider-Singleton – hält z. B. den OAuth-Token im Cache."""
    global _sim_provider, _sim_provider_loaded
    if not _sim_provider_loaded:
        _sim_provider_loaded = True
        try:
            _sim_provider = get_provider(config=load_provider_config())
        except Exception as exc:
            print(f"[provider] {exc}", flush=True)
    return _sim_provider


async def watch_sim_messages() -> None:
    """Echtzeit-SMS des Anbieters abonnieren (falls unterstützt).

    Eingehende Nachrichten landen in der Tabelle `sim_sms`; Nachrichten **vom
    Gerät** (MO) lösen zusätzlich eine Eltern-Benachrichtigung aus – das ist der
    Pfad für „Tracker meldet sich per SMS", ohne auf das Polling zu warten.
    """
    provider = sim_provider()
    if provider is None or not provider.configured():
        print("[sms-watch] kein SIM-Provider konfiguriert", flush=True)
        return
    if not provider.supports_watch():
        print(f"[sms-watch] {provider.name} unterstützt keine Echtzeit-SMS", flush=True)
        return

    with db() as conn:
        rows = conn.execute("SELECT DISTINCT iccid FROM devices WHERE iccid != ''").fetchall()
    iccids = [str(row["iccid"]) for row in rows]
    if not iccids:
        print("[sms-watch] keine ICCID in der Geräte-Registry – Echtzeit-SMS inaktiv", flush=True)
        return

    async def handle(sms) -> None:
        iccid = str(sms.raw.get("iccid") or "")
        with db() as conn:
            conn.execute(
                "INSERT INTO sim_sms(iccid, direction, originator, text, received_at) "
                "VALUES(?, ?, ?, ?, ?)",
                (iccid, sms.direction, sms.source, sms.text, now_iso()),
            )
        label = "vom Tracker" if sms.direction == "MO" else "an den Tracker"
        print(f"[sms-watch] SMS {label}: {sms.text[:60]!r}", flush=True)
        if sms.direction == "MO":  # Gerät → Server: Eltern sofort informieren
            push_async("SMS vom Tracker", sms.text[:120] or "(leer)")
            notify_async("SMS vom Tracker", sms.text[:200] or "(leer)")

    print(f"[sms-watch] Echtzeit-SMS aktiv für {len(iccids)} SIM(s)", flush=True)
    tasks = [asyncio.create_task(provider.watch_sms(iccid, handle)) for iccid in iccids]
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        raise


# --- Retention --------------------------------------------------------------


def run_cleanup() -> dict:
    """Löscht Nachrichten/Audiodateien älter als die Aufbewahrungszeit (0 = aus)."""
    days = setting("retention_days")
    state_set("last_cleanup", now_iso())
    if days <= 0:
        return {"removed": 0, "retention_days": 0, "disabled": True}
    cutoff = time.time() - days * 86400
    removed = 0
    with db() as conn:
        rows = conn.execute("SELECT id, raw_file, play_file, created_at FROM messages").fetchall()
        for row in rows:
            epoch = _to_epoch(row["created_at"])
            if epoch is None or epoch >= cutoff:
                continue
            for name in (row["raw_file"], row["play_file"]):
                (AUDIO_DIR / name).unlink(missing_ok=True)
            conn.execute("DELETE FROM messages WHERE id = ?", (row["id"],))
            removed += 1
    # Alte Backup-Archive mit aufräumen (älter als 2 Tage)
    for archive in DATA_DIR.glob("backup-*.tar.gz"):
        if archive.stat().st_mtime < time.time() - 2 * 86400:
            archive.unlink(missing_ok=True)
    return {"removed": removed, "retention_days": days}


async def retention_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            result = await asyncio.to_thread(run_cleanup)
            if result.get("removed"):
                print(f"[retention] {result}", flush=True)
        except Exception as exc:
            print(f"[retention] Fehler: {exc!r}", flush=True)


# --- Firmware/OTA-Hilfsfunktionen (docs/optimizations.md B7) ---------------


def parse_version(text: str):
    """'1.2.3' → (1, 2, 3); None bei ungültigem Format."""
    parts = text.strip().split(".")
    if not 1 <= len(parts) <= 3:
        return None
    numbers = []
    for part in parts:
        if not part.isdigit() or len(part) > 4:
            return None
        numbers.append(int(part))
    while len(numbers) < 3:
        numbers.append(0)
    return tuple(numbers)


def version_is_newer(available: str, current: str) -> bool:
    a, c = parse_version(available), parse_version(current)
    if a is None or c is None:
        return False
    return a > c


def latest_firmware() -> dict | None:
    """Neueste Firmware nach Versionsvergleich (nicht nach Upload-Zeitpunkt)."""
    with db() as conn:
        rows = conn.execute("SELECT * FROM firmware").fetchall()
    best = None
    best_version = None
    for row in rows:
        version = parse_version(row["version"])
        if version is None:
            continue
        if best_version is None or version > best_version:
            best_version = version
            best = dict(row)
    return best


# --- Find-My- und Positions-Hilfsfunktionen ---------------------------------

LAT_KEYS = ("latitude", "lat", "latDeg", "lat_deg", "y")
LON_KEYS = ("longitude", "lon", "lng", "long", "lonDeg", "lon_deg", "x")
ID_KEYS = ("beacon_id", "beaconId", "device_id", "deviceId", "id", "identifier", "accessory_id", "name")
TIME_KEYS = ("reported_at", "reportedAt", "timestamp", "time", "date", "lastUpdate", "last_seen")
ACC_KEYS = ("accuracy", "acc", "horizontalAccuracy", "hdop")
PROVIDER_KEYS = ("provider", "source", "network")


def _pick(item: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return None


def _to_epoch(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    return None


def extract_location(item: dict) -> dict | None:
    """Tolerante Extraktion: das Payload-Format externer Find-My-Tools ist nicht dokumentiert."""
    lat = _pick(item, LAT_KEYS)
    lon = _pick(item, LON_KEYS)
    if lat is None or lon is None:
        return None
    try:
        latitude, longitude = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    accuracy = _pick(item, ACC_KEYS)
    try:
        accuracy = float(accuracy) if accuracy is not None else None
    except (TypeError, ValueError):
        accuracy = None
    beacon_id = _pick(item, ID_KEYS)
    reported = _pick(item, TIME_KEYS)
    return {
        "provider": str(_pick(item, PROVIDER_KEYS) or "unknown").lower(),
        "beacon_id": str(beacon_id) if beacon_id else "unknown",
        "latitude": latitude,
        "longitude": longitude,
        "accuracy": accuracy,
        "reported_at": str(reported) if reported is not None else None,
        "reported_epoch": _to_epoch(reported),
    }


def insert_findmy(loc: dict, raw: dict) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO findmy_locations(provider, beacon_id, latitude, longitude, accuracy, "
            "reported_at, received_at, raw) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (
                loc["provider"],
                loc["beacon_id"],
                loc["latitude"],
                loc["longitude"],
                loc["accuracy"],
                loc["reported_at"],
                now_iso(),
                json.dumps(raw, ensure_ascii=False),
            ),
        )


def insert_position(device_id: str, loc: dict, battery: float | None, source: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO positions(device_id, latitude, longitude, accuracy, battery, source, "
            "reported_at, received_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (
                device_id,
                loc["latitude"],
                loc["longitude"],
                loc.get("accuracy"),
                battery,
                source,
                loc.get("reported_at"),
                now_iso(),
            ),
        )


def sanitize_device_id(value: str) -> str:
    """Traccar akzeptiert in Geräte-IDs keine Bindestriche/Sonderzeichen.

    Für das Forwarding wird die ID auf ASCII-Buchstaben, Ziffern, '.' und '_'
    reduziert. Die Original-ID bleibt in der Bridge erhalten.
    """
    cleaned = "".join(ch for ch in value if ch.isascii() and (ch.isalnum() or ch in "._"))
    return cleaned or "unknown"


_assigned = {"at": 0.0}


def assign_devices_in_traccar() -> bool:
    """Ordnet alle Geräte dem Traccar-Konto zu (idempotent, höchstens alle 10 min).

    Traccar legt Geräte bei unbekannten Uploads an (database.registerUnknown),
    ordnet sie aber keinem Benutzer zu – die Oberfläche zeigt dann
    „Registriere dein erstes Gerät", obwohl die Geräte existieren. Über
    `?all=true` sieht der Administrator auch noch nicht zugeordnete Geräte.
    """
    if time.time() - _assigned["at"] < 600:
        return True
    session = traccar_session()
    if not session or not session[1]:
        return False
    jsession, user_id = session
    try:
        request = urllib.request.Request("http://traccar:8082/api/devices?all=true",
                                         headers={"Cookie": jsession})
        with urllib.request.urlopen(request, timeout=8) as response:
            devices = json.loads(response.read() or b"[]")
        assigned = 0
        for device in devices:
            payload = json.dumps({"userId": user_id, "deviceId": device["id"]}).encode()
            req = urllib.request.Request(
                "http://traccar:8082/api/permissions", data=payload,
                headers={"Cookie": jsession, "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=8):
                    assigned += 1
            except urllib.error.HTTPError as exc:
                if exc.code != 400:  # 400 = war schon zugeordnet
                    print(f"[traccar] Zuordnung Gerät {device['id']}: HTTP {exc.code}", flush=True)
        _assigned["at"] = time.time()
        if assigned:
            print(f"[traccar] {assigned} Gerät(e) dem Konto zugeordnet "
                  f"(von {len(devices)} bekannten)", flush=True)
        return True
    except Exception as exc:
        print(f"[traccar] Zuordnung fehlgeschlagen: {exc!r}", flush=True)
        return False


def traccar_session() -> tuple[str, int] | None:
    """Meldet sich bei Traccar an und liefert (Sitzungscookie, Benutzer-ID)."""
    email, password = traccar_credentials()
    if not (email and password):
        ensure_traccar_admin()
        email, password = traccar_credentials()
    if not (email and password):
        return None
    payload = urllib.parse.urlencode({"email": email, "password": password}).encode()
    request = urllib.request.Request(
        "http://traccar:8082/api/session", data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.headers.get("Set-Cookie", "")
            jsession = next((part.split(";")[0] for part in raw.split(",")
                             if "JSESSIONID=" in part), "")
            body = json.loads(response.read() or b"{}")
    except Exception as exc:
        print(f"[traccar] Anmeldung für Zuordnung fehlgeschlagen: {exc!r}", flush=True)
        return None
    return (jsession, int(body.get("id") or 0)) if jsession else None


# --- Sensor-Fusion: mehrere Quellen → eine Position je Kind -----------------
# Die Logik liegt in app/fusion.py (reine Funktionen, host-getestet). Hier nur
# die Datenbeschaffung aus der Bridge-Datenbank.

def beacon_assignments() -> dict[str, str]:
    """Beacon-ID (klein) → Geräte-ID des Kindes."""
    with db() as conn:
        rows = conn.execute("SELECT beacon_id, device_id FROM beacons").fetchall()
    return {row["beacon_id"].lower(): row["device_id"] for row in rows}


def candidate_positions(device_id: str, limit: int = 40) -> list[dict]:
    """Alle aktuellen Positionsquellen eines Kindes (Tracker + zugeordnete Beacons)."""
    assignments = beacon_assignments()
    beacons = [beacon for beacon, child in assignments.items() if child == device_id]
    candidates: list[dict] = []
    with db() as conn:
        row = conn.execute(
            "SELECT latitude, longitude, battery, received_at FROM positions "
            "WHERE device_id = ? ORDER BY id DESC LIMIT 1", (device_id,),
        ).fetchone()
        if row is not None:
            candidates.append({
                "source": "tracker", "latitude": row["latitude"], "longitude": row["longitude"],
                "accuracy": None, "battery": row["battery"], "received_at": row["received_at"],
            })
        if beacons:
            placeholders = ",".join("?" for _ in beacons)
            for beacon in conn.execute(
                f"SELECT provider, beacon_id, latitude, longitude, accuracy, received_at "
                f"FROM findmy_locations WHERE lower(beacon_id) IN ({placeholders}) "
                f"AND id IN (SELECT MAX(id) FROM findmy_locations "
                f"           GROUP BY provider, lower(beacon_id))",
                beacons,
            ).fetchall():
                candidates.append({
                    "source": (beacon["provider"] or "findmy").lower(),
                    "latitude": beacon["latitude"], "longitude": beacon["longitude"],
                    "accuracy": beacon["accuracy"], "battery": None,
                    "received_at": beacon["received_at"],
                })
    for candidate in candidates:
        candidate["trust"] = source_trust(candidate["source"])
        epoch = _to_epoch(candidate["received_at"]) or 0
        candidate["age_s"] = max(0, int(time.time() - epoch)) if epoch else None
        valid = source_valid_seconds(candidate["source"])
        candidate["valid"] = candidate["age_s"] is not None and candidate["age_s"] <= valid
    return candidates


def best_position(device_id: str) -> dict | None:
    """Beste verfügbare Position eines Kindes (Fusion, docs/fusion.md)."""
    candidates = candidate_positions(device_id)
    if not candidates:
        return None
    with db() as conn:
        previous_row = conn.execute(
            "SELECT latitude, longitude, received_at FROM positions "
            "WHERE device_id = ? ORDER BY id DESC LIMIT 1 OFFSET 1", (device_id,),
        ).fetchone()
        recent = conn.execute(
            "SELECT latitude, longitude, received_at FROM positions "
            "WHERE device_id = ? ORDER BY id DESC LIMIT 12", (device_id,),
        ).fetchall()
    chosen = choose_best(candidates, previous=dict(previous_row) if previous_row else None)
    if chosen is None:
        return None
    chosen["state"] = movement_state([dict(row) for row in recent])
    return chosen


def forward_fused_to_traccar(device_id: str) -> bool:
    """Sendet die fusionierte Position eines Kindes an Traccar (ein Gerät je Kind)."""
    best = best_position(device_id)
    if best is None:
        return False
    epoch = _to_epoch(best["received_at"]) or int(time.time())
    return forward_to_traccar({
        "beacon_id": device_id,
        "latitude": best["latitude"],
        "longitude": best["longitude"],
        "accuracy": best["accuracy"],
        "reported_epoch": epoch,
    })


def forward_to_traccar(loc: dict) -> bool:
    """Reicht Positionen als OsmAnd-Position an Traccar weiter."""
    if not TRACCAR_FORWARD_URL:
        return False
    params = {
        "id": sanitize_device_id(loc["beacon_id"]),
        "lat": loc["latitude"],
        "lon": loc["longitude"],
        "timestamp": loc.get("reported_epoch") or int(time.time()),
    }
    if loc.get("accuracy"):
        params["hdop"] = loc["accuracy"]
    url = TRACCAR_FORWARD_URL.rstrip("/") + "/?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            if not (200 <= response.status < 300):
                print(f"[forward] Traccar HTTP {response.status}: {url}", flush=True)
                return False
            # Gerät dem Konto zuordnen, sonst zeigt Traccar „Registriere dein erstes Gerät"
            assign_devices_in_traccar()
            return True
    except Exception as exc:  # Diagnose: Fehler nicht still verschlucken
        print(f"[forward] Traccar-Forward fehlgeschlagen ({type(exc).__name__}: {exc}) {url}", flush=True)
        return False


# --- App --------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_config()
    init_db()
    ensure_admin_user()
    retention = asyncio.create_task(retention_loop())
    watch = asyncio.create_task(watch_sim_messages()) if SMS_SUBSCRIBE else None
    try:
        yield
    finally:
        retention.cancel()
        if watch is not None:
            watch.cancel()


app = FastAPI(title="UltimateTracker Audio-Bridge", version="0.3.0", lifespan=lifespan)

# Statische Dateien (Icons für PWA/apple-touch-icon, Service Worker liegt am Root)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def caddy_available(timeout: float = 1.0) -> bool:
    """Ist der TLS-Frontdoor (Caddy) im Docker-Netz erreichbar?

    Dort lebt das Single Sign-on (forward_auth). Nur dann sind die
    SITE_*-Adressen sinnvoll verlinkbar.
    """
    import socket

    try:
        with socket.create_connection(("caddy", 443), timeout=timeout):
            return True
    except OSError:
        return False


@app.get("/api/v1/parent/services", dependencies=[Depends(require_parent)])
def services_overview() -> dict:
    """Status und Adressen aller Dienste – Grundlage für die Übersicht in der UI.

    Ergebnis wird 10 s gecacht, damit die Oberfläche die Dienste nicht hämmert.
    """
    now = time.time()
    if _services_cache["value"] is not None and _services_cache["expires_at"] > now:
        return _services_cache["value"]

    sso = caddy_available()
    result = []
    for key, name, description, target, port, site_env in SERVICE_DEFS:
        status = "n/a"
        if target:
            host, _, port_text = target.partition(":")
            internal_port = int(port_text)
            path = "/api/server" if key == "traccar" else "/"
            status = probe_http(host, internal_port, path)
        site_host = os.environ.get(site_env, "") if site_env else ""
        internal = key in INTERNAL_SERVICES
        result.append({
            "key": key,
            "name": name,
            "description": description,
            "status": status,
            "port": None if internal else port,
            "site_host": site_host,
            # Nur über Caddy greift das Single Sign-on (und TLS).
            "sso_available": bool(sso and site_host and port and not internal),
            # Interner Dienst: kein Link (nichts zu öffnen), nur Status.
            "internal": internal,
            # Traccar meldet sich über den Link automatisch an (Einmal-Ticket).
            "own_login": key in ("google-findmy", "apple-findmy"),
            "hint": SERVICE_HINTS.get(key, ""),
        })

    payload = {
        "services": result,
        "sso": {"available": sso, "entry": os.environ.get("SITE_AUDIO", "") or "audio.localhost"},
        "checked_at": now_iso(),
    }
    _services_cache["value"] = payload
    _services_cache["expires_at"] = now + 10
    return payload


@app.get("/api/v1/parent/settings", dependencies=[Depends(require_parent)])
def settings_get() -> dict:
    """Laufzeit-Einstellungen (überschreiben die .env-Defaults)."""
    return {
        "values": settings_all(),
        "definitions": {
            name: {"label": spec["label"], "min": spec["min"], "max": spec["max"]}
            for name, spec in SETTING_DEFS.items()
        },
    }


@app.put("/api/v1/parent/settings", dependencies=[Depends(require_parent)])
async def settings_put(request: Request) -> dict:
    """Einstellungen ändern – wirken sofort, ohne Neustart."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON erwartet")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON-Objekt erwartet")
    return {"values": settings_update(body)}


@app.get("/api/v1/parent/map", dependencies=[Depends(require_parent)])
def parent_map() -> dict:
    """Kartendaten: letzte Position je Tracker, letzte Position je Find-My-Beacon,
    Kachel-URL und Attribution.

    Bewusst ohne Traccar: die Karte in der Eltern-UI braucht damit **keine**
    zweite Anmeldung (Traccar verlangt sein eigenes Konto, und im iframe hält
    die Sitzung wegen Third-Party-Cookie-Blockade oft nicht).
    """
    with db() as conn:
        trackers = []
        for device in conn.execute("SELECT id, name FROM devices ORDER BY created_at").fetchall():
            best = best_position(device["id"])
            if best is None:
                continue
            trackers.append({
                "device_id": device["id"],
                "name": device["name"] or device["id"],
                "latitude": best["latitude"],
                "longitude": best["longitude"],
                "battery": best.get("battery"),
                "received_at": best["received_at"],
                "source": best["source"],
                "accuracy": best["accuracy"],
                "age_s": best["age_s"],
                "stale": best["stale"],
                "reason": best["reason"],
                "state": best.get("state", "unknown"),
                "sources": best["sources"],
            })
        beacons = [
            dict(row) for row in conn.execute(
                "SELECT provider, beacon_id, latitude, longitude, received_at FROM findmy_locations "
                "WHERE id IN (SELECT MAX(id) FROM findmy_locations GROUP BY provider, beacon_id) "
                "ORDER BY received_at DESC LIMIT 50"
            ).fetchall()
        ]
    return {
        "tiles": MAP_TILES,
        "attribution": MAP_ATTRIBUTION,
        "trackers": trackers,
        "beacons": beacons,
        "checked_at": now_iso(),
    }


@app.get("/api/v1/parent/system", dependencies=[Depends(require_parent)])
def system_status() -> dict:
    """Betriebswerte für das Monitoring: Last, Speicher, Platte, Datenbestand."""
    try:
        load = os.getloadavg()[0]
    except (AttributeError, OSError):
        load = 0.0

    memory = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                key, _, value = line.partition(":")
                if key in ("MemTotal", "MemAvailable"):
                    memory[key] = int(value.split()[0]) // 1024  # MB
    except OSError:
        pass

    usage = shutil.disk_usage(DATA_DIR if DATA_DIR.exists() else Path("."))
    audio_files = [item for item in AUDIO_DIR.glob("*") if item.is_file()] if AUDIO_DIR.exists() else []
    audio_bytes = sum(item.stat().st_size for item in audio_files)

    with db() as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            for table in ("messages", "positions", "devices", "findmy_locations")
        }
        oldest = conn.execute("SELECT MIN(created_at) AS t FROM messages").fetchone()["t"]

    backups = sorted(DATA_DIR.glob("backup-*.tar.gz")) if DATA_DIR.exists() else []
    return {
        "uptime_s": int(time.time() - START_TIME),
        "load_1m": round(load, 2),
        "memory_mb": memory,
        "disk_mb": {
            "total": usage.total // 1048576,
            "free": usage.free // 1048576,
            "used_percent": round(100 * (usage.total - usage.free) / max(usage.total, 1), 1),
        },
        "data": {
            **counts,
            "audio_files": len(audio_files),
            "audio_mb": round(audio_bytes / 1048576, 2),
            "oldest_message": oldest,
            "last_cleanup": state_get("last_cleanup"),
            "last_backup": backups[-1].name if backups else None,
        },
        "versions": {"bridge": app.version, "python": sys.version.split()[0]},
        "checked_at": now_iso(),
    }


@app.get("/api/v1/parent/maintenance/backup", dependencies=[Depends(require_parent)])
def maintenance_backup() -> FileResponse:
    """Datenverzeichnis (Audio, Datenbank, Ereignislog) als tar.gz herunterladen."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = DATA_DIR / f"backup-{stamp}.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        if AUDIO_DIR.exists():
            archive.add(AUDIO_DIR, arcname="audio")
        if DB_PATH.exists():
            archive.add(DB_PATH, arcname="bridge.sqlite3")
        if EVENTS_LOG.exists():
            archive.add(EVENTS_LOG, arcname="events.jsonl")
    return FileResponse(path, media_type="application/gzip", filename=path.name)


# --- Anmeldung (Eltern-UI) --------------------------------------------------


@app.get("/api/v1/auth/state")
def auth_state() -> dict:
    """Öffentlich: existiert schon ein Konto? (Steuert die Erstanmeldung in der UI)."""
    count = users_count()
    return {"users": count, "registration_open": count == 0}


@app.post("/api/v1/auth/register")
async def auth_register(request: Request) -> dict:
    """Erstanmeldung ohne Terminal: legt den ersten Administrator an.

    Nur solange noch kein Benutzer existiert – danach ausschließlich über die
    Benutzerverwaltung (Admin) oder den Setup-Assistenten.
    """
    if users_count() > 0:
        raise HTTPException(status_code=409, detail="Es existiert schon ein Konto – bitte anmelden")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON erwartet")
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Benutzername braucht mindestens 3 Zeichen")
    problem = password_problem(password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    with db() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES(?, ?, 'admin', ?)",
            (username, hash_password(password), now_iso()),
        )
    print(f"[setup] Erstes Konto angelegt: {username} (Administrator)", flush=True)
    return {"created": username, "role": "admin"}


@app.post("/api/v1/auth/login")
async def auth_login(request: Request, response: Response) -> dict:
    """Anmeldung mit Benutzername und Passwort → Sitzungstoken + Cookie (SSO)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON erwartet")
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        await asyncio.sleep(0.5)  # bremst Durchprobieren
        raise HTTPException(status_code=401, detail="Benutzername oder Passwort falsch")
    token = new_session_token()
    expires = session_expiry()
    with db() as conn:
        conn.execute(
            "INSERT INTO sessions(token, user_id, created_at, expires_at) VALUES(?, ?, ?, ?)",
            (token, row["id"], now_iso(), expires),
        )
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now_iso(),))
    # Cookie für Single Sign-on über Caddy (forward_auth) – der Header-Weg bleibt.
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=24 * 30 * 3600,
        httponly=True,
        samesite="lax",
        secure=request_is_https(request),
        domain=cookie_domain(request),
        path="/",
    )
    return {
        "token": token,
        "expires_at": expires,
        "user": {"username": row["username"], "role": row["role"]},
    }


@app.get("/api/v1/auth/verify")
def auth_verify(request: Request, x_auth_token: str | None = Header(default=None)) -> Response:
    """Für Caddy `forward_auth`: 200 = angemeldet, 401 = nicht (kein Body, schnell)."""
    token = session_token(request, x_auth_token)
    if token_ok(parent_token(), token) or session_user(token) is not None:
        return Response(status_code=200)
    return Response(status_code=401)


@app.post("/api/v1/auth/logout")
async def auth_logout(request: Request, response: Response) -> dict:
    """Sitzung beenden (Token und Cookie werden ungültig)."""
    token = session_token(request, request.headers.get("x-auth-token"))
    with db() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    response.delete_cookie(COOKIE_NAME, domain=cookie_domain(request), path="/")
    return {"logged_out": True}


@app.get("/api/v1/auth/me")
def auth_me(x_auth_token: str | None = Header(default=None)) -> dict:
    """Aktuell angemeldeter Zugang (Sitzung oder API-Token)."""
    if token_ok(parent_token(), x_auth_token):
        return {"username": "token", "role": "admin", "kind": "token"}
    user = session_user(x_auth_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Nicht angemeldet")
    return {**user, "kind": "session"}


@app.post("/api/v1/auth/password")
async def auth_password(request: Request, x_auth_token: str | None = Header(default=None)) -> dict:
    """Eigenes Passwort ändern (nur mit Anmeldung – nicht mit dem API-Token)."""
    user = session_user(x_auth_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Nur mit Anmeldung möglich (kein API-Token)")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON erwartet")
    current = str(body.get("current") or "")
    new = str(body.get("new") or "")

    with db() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
    if row is None or not verify_password(current, row["password_hash"]):
        await asyncio.sleep(0.5)  # bremst Durchprobieren
        raise HTTPException(status_code=401, detail="Aktuelles Passwort ist falsch")
    problem = password_problem(new)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    if verify_password(new, row["password_hash"]):
        raise HTTPException(status_code=400, detail="Das neue Passwort ist identisch mit dem alten")

    with db() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new), user["id"]))
        # Alle anderen Sitzungen beenden – die aktuelle bleibt gültig.
        conn.execute(
            "DELETE FROM sessions WHERE user_id = ? AND token != ?",
            (user["id"], x_auth_token or ""),
        )
    return {"changed": True, "other_sessions_ended": True}


@app.post("/api/v1/auth/users/{user_id}/password", dependencies=[Depends(require_admin)])
async def users_reset_password(user_id: int, request: Request) -> dict:
    """Passwort eines Benutzers zurücksetzen (Administrator, ohne altes Passwort)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON erwartet")
    new = str(body.get("new") or "")
    problem = password_problem(new)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    with db() as conn:
        row = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Unbekannter Benutzer")
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new), user_id))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return {"reset": row["username"], "sessions_ended": True}


@app.get("/api/v1/auth/users", dependencies=[Depends(require_admin)])
def users_list() -> dict:
    with db() as conn:
        rows = conn.execute("SELECT id, username, role, created_at FROM users ORDER BY id").fetchall()
    return {"users": [dict(row) for row in rows]}


@app.post("/api/v1/auth/users", dependencies=[Depends(require_admin)])
async def users_create(request: Request) -> dict:
    """Weiteren Zugang anlegen (z. B. zweiter Elternteil)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON erwartet")
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    role = "admin" if str(body.get("role") or "parent") == "admin" else "parent"
    if not username or not password:
        raise HTTPException(status_code=400, detail="username und password erforderlich")
    problem = password_problem(password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO users(username, password_hash, role, created_at) VALUES(?, ?, ?, ?)",
                (username, hash_password(password), role, now_iso()),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Benutzername ist schon vergeben")
    return {"created": username, "role": role}


@app.delete("/api/v1/auth/users/{user_id}", dependencies=[Depends(require_admin)])
def users_delete(user_id: int) -> dict:
    with db() as conn:
        row = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Unbekannter Benutzer")
        count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if count <= 1:
            raise HTTPException(status_code=400, detail="Der letzte Benutzer kann nicht gelöscht werden")
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return {"deleted": row["username"]}


@app.get("/api/v1/parent/overview", dependencies=[Depends(require_parent)])
def parent_overview() -> dict:
    """Alle Kinder auf einen Blick – für Familien mit mehreren Trackern."""
    with db() as conn:
        devices = conn.execute("SELECT * FROM devices ORDER BY created_at").fetchall()
        children = []
        for device in devices:
            position = conn.execute(
                "SELECT latitude, longitude, battery, received_at FROM positions "
                "WHERE device_id = ? ORDER BY id DESC LIMIT 1",
                (device["id"],),
            ).fetchone()
            message = conn.execute(
                "SELECT created_at, direction FROM messages WHERE device_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (device["id"],),
            ).fetchone()
            pending = conn.execute(
                "SELECT COUNT(*) AS n FROM messages WHERE device_id = ? AND direction = 'out' "
                "AND status = 'new'",
                (device["id"],),
            ).fetchone()["n"]
            children.append({
                "device_id": device["id"],
                "name": device["name"] or device["id"],
                "imei": device["imei"] or device["id"],
                "msisdn": device["msisdn"] or "",
                "battery": position["battery"] if position else None,
                "last_position_at": position["received_at"] if position else None,
                "last_message_at": message["created_at"] if message else None,
                "pending_messages": pending,
                "search_mode": search_mode_active(device["id"]),
            })
    return {"children": children, "count": len(children)}


@app.post("/api/v1/parent/sso/ticket", dependencies=[Depends(require_parent)])
def sso_ticket() -> dict:
    """Einmal-Ticket für den Dienst-Auto-Login.

    Warum nicht einfach das Sitzungscookie? Browser verwerfen `Domain=localhost`
    (die Domain braucht laut RFC einen Punkt), deshalb kommt das Cookie von
    `audio.localhost` nie bei `traccar.localhost` an. Das Ticket umgeht das:
    kurz gültig, einmalig, nur mit gültiger Anmeldung erhältlich.
    """
    now = time.time()
    with db() as conn:
        conn.execute("DELETE FROM state WHERE key LIKE 'sso_ticket:%' AND CAST(value AS REAL) < ?",
                     (now,))
    ticket = secrets.token_urlsafe(24)
    state_set(f"sso_ticket:{ticket}", str(now + 120))
    return {"ticket": ticket, "expires_in": 120}


def sso_login_response(request: Request, ticket: str) -> Response:
    """Meldet sich serverseitig in Traccar an und gibt das Sitzungscookie weiter.

    Wird von `/_sso/traccar` und von `/?sso=…` genutzt (der Wurzel-Pfad ist die
    echte SPA-Route – damit kann der Browser keine alte Seite für einen
    unbekannten Pfad aus dem Cache zeigen).
    """
    entry = os.environ.get("SITE_AUDIO", "") or "audio.localhost"
    host = request.headers.get("host") or entry
    authorized = False
    if ticket:
        stored = state_get(f"sso_ticket:{ticket}")
        if stored and float(stored) > time.time():
            authorized = True
        with db() as conn:
            conn.execute("DELETE FROM state WHERE key = ?", (f"sso_ticket:{ticket}",))
    if not authorized:
        token = session_token(request)
        authorized = token_ok(parent_token(), token) or session_user(token) is not None

    if not authorized:
        if request.cookies.get(COOKIE_NAME):
            # Cookie vorhanden, aber für diesen Host nicht gültig (Direktzugang)
            return RedirectResponse(f"https://{entry}/?sso=failed", status_code=302)
        back = urllib.parse.quote(f"https://{host}/_sso/traccar", safe="")
        return RedirectResponse(f"https://{entry}/?next={back}", status_code=302)

    email, password = TRACCAR_SSO_EMAIL, TRACCAR_SSO_PASSWORD
    if not (email and password):
        email, password = traccar_credentials()
        if not (email and password):
            ensure_traccar_admin()
            email, password = traccar_credentials()
    if not (email and password):
        return RedirectResponse("/", status_code=302)

    payload = urllib.parse.urlencode({"email": email, "password": password}).encode()
    request_login = urllib.request.Request(
        "http://traccar:8082/api/session", data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    cookie = ""
    try:
        with urllib.request.urlopen(request_login, timeout=8) as response:
            raw = response.headers.get("Set-Cookie", "")
            cookie = next((part.split(";")[0] for part in raw.split(",")
                           if "JSESSIONID=" in part), "")
    except Exception as exc:
        print(f"[sso] Traccar-Anmeldung fehlgeschlagen: {exc!r}", flush=True)

    redirect = RedirectResponse("/", status_code=302)
    if cookie:
        suffix = "; Path=/; HttpOnly; SameSite=Lax"
        if request_is_https(request):
            suffix += "; Secure"
        redirect.headers["Set-Cookie"] = cookie + suffix
    return redirect


@app.get("/_sso/traccar")
def sso_traccar(request: Request) -> Response:
    """Auto-Login über den klassischen Pfad (Rückwärtskompatibilität)."""
    return sso_login_response(request, (request.query_params.get("ticket") or "").strip())


CA_FILE = Path(os.environ.get("CADDY_CA_FILE", "/caddy-data/caddy/pki/authorities/local/root.crt"))
# Verzeichnis der macless-haystack-Daten (Volume) – dort liegt config.ini
APPLE_CONFIG_DIR = Path(os.environ.get("APPLE_CONFIG_DIR", "/macless-data"))


def apple_config_status() -> dict:
    """Ist für macless-haystack eine Apple-ID hinterlegt?"""
    path = APPLE_CONFIG_DIR / "config.ini"
    if not path.exists():
        return {"configured": False, "path": str(path), "appleid": ""}
    parser = configparser.ConfigParser()
    try:
        parser.read(path)
        appleid = parser.get("Settings", "appleid", fallback="") if parser.has_section("Settings") else ""
    except Exception:
        appleid = ""
    return {"configured": bool(appleid), "path": str(path), "appleid": appleid}


@app.get("/api/v1/parent/apple", dependencies=[Depends(require_parent)])
def apple_status() -> dict:
    """Apple-Find-My-Einrichtung: Zugangsdaten hinterlegt, Dienst erreichbar?"""
    status = apple_config_status()
    status["service"] = probe_http("macless-haystack", 6176, "/") if status["configured"] else "down"
    return status


@app.put("/api/v1/parent/apple", dependencies=[Depends(require_parent)])
async def apple_configure(request: Request) -> dict:
    """Apple-ID für macless-haystack hinterlegen.

    Das Image fragt die Zugangsdaten beim ersten Start **interaktiv** ab – in
    einem Container ohne Terminal endet das im EOFError. Der Assistent schreibt
    sie stattdessen in `data/config.ini`; der Dienst startet danach von selbst
    (restart: on-failure).
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON erwartet")
    appleid = str(body.get("appleid") or "").strip()
    password = str(body.get("password") or "")
    if not appleid or "@" not in appleid:
        raise HTTPException(status_code=400, detail="Bitte die Apple-ID (E-Mail) angeben")
    if not password:
        raise HTTPException(status_code=400, detail="Bitte das Apple-Passwort angeben")

    APPLE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = APPLE_CONFIG_DIR / "config.ini"
    parser = configparser.ConfigParser()
    if path.exists():
        try:
            parser.read(path)
        except Exception:
            parser = configparser.ConfigParser()
    if not parser.has_section("Settings"):
        parser.add_section("Settings")
    parser.set("Settings", "appleid", appleid)
    parser.set("Settings", "appleid_pass", password)
    parser.set("Settings", "anisette_url", os.environ.get("ANISETTE_URL", "http://anisette:6969"))
    parser.set("Settings", "port", "6176")
    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    print(f"[apple] Zugangsdaten hinterlegt für {appleid}", flush=True)
    return {
        "configured": True,
        "path": str(path),
        "hint": "Der Dienst startet automatisch neu – das kann bis zu einer Minute dauern.",
    }


@app.get("/ca.crt", response_class=FileResponse)
def ca_certificate() -> Response:
    """Root-Zertifikat der Caddy-CA zum Installieren auf den Geräten.

    Bewusst ohne Anmeldung und über HTTP erreichbar: Solange das Zertifikat
    nicht installiert ist, zeigt der Browser für HTTPS eine Warnung – der
    Download muss also ohne vertrauenswürdiges TLS funktionieren. Das Zertifikat
    selbst ist öffentlich (der private Schlüssel bleibt in Caddy).
    """
    if not CA_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="Kein CA-Zertifikat gefunden – läuft Caddy? (docker compose --profile tls up -d)",
        )
    return FileResponse(CA_FILE, media_type="application/x-x509-ca-cert",
                        filename="ultimatetracker-ca.crt")


@app.get("/healthz")
def healthz() -> dict:
    return {
        "status": "ok",
        "search_mode": search_mode_active(),
        "findmy_forward": bool(TRACCAR_FORWARD_URL),
        "retention_days": RETENTION_DAYS,
        "notifications": bool(APPRISE_URLS),
        "push_subscriptions": push_subscription_count(),
        "sim_provider": sim_provider().name if sim_provider() else None,
        "sms_api": bool(sim_provider() and sim_provider().configured()),
        "sms_subscribe": SMS_SUBSCRIBE,
        "users": users_count(),
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Response:
    """Eltern-UI – oder Auto-Login, wenn `?sso=<ticket>` mitkommt.

    Der SSO-Einstieg läuft bewusst über die Wurzel-URL: Das ist die echte
    SPA-Route von Traccar, damit kann der Browser keine alte Seite für einen
    unbekannten Pfad aus dem Cache zeigen (genau das führte zu schwarzen Seiten).
    """
    ticket = (request.query_params.get("sso") or "").strip()
    if ticket:
        return sso_login_response(request, ticket)
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/sw.js")
def service_worker() -> Response:
    """Service Worker für PWA + Web-Push (muss vom Root ausgeliefert werden)."""
    return Response(
        (STATIC_DIR / "sw.js").read_text(encoding="utf-8"),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@app.get("/manifest.webmanifest")
def manifest() -> Response:
    return Response(
        (STATIC_DIR / "manifest.webmanifest").read_text(encoding="utf-8"),
        media_type="application/manifest+json",
    )


# --- Push-Verwaltung (Eltern) -----------------------------------------------


@app.get("/api/v1/parent/push/key", dependencies=[Depends(require_parent)])
def push_key() -> dict:
    try:
        _, public_b64 = get_vapid_keys()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Push nicht verfügbar: {exc}")
    return {"key": public_b64, "subscriptions": push_subscription_count()}


@app.post("/api/v1/parent/push/subscribe", dependencies=[Depends(require_parent)])
async def push_subscribe(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON erwartet")
    endpoint = str(body.get("endpoint") or "")
    keys = body.get("keys") or {}
    p256dh = str(keys.get("p256dh") or "")
    auth = str(keys.get("auth") or "")
    if not endpoint or not p256dh or not auth:
        raise HTTPException(status_code=400, detail="endpoint/keys fehlen")
    with db() as conn:
        conn.execute(
            "INSERT INTO push_subscriptions(endpoint, p256dh, auth, created_at) VALUES(?, ?, ?, ?) "
            "ON CONFLICT(endpoint) DO UPDATE SET p256dh = excluded.p256dh, auth = excluded.auth",
            (endpoint, p256dh, auth, now_iso()),
        )
    return {"subscribed": True, "subscriptions": push_subscription_count()}


@app.delete("/api/v1/parent/push/subscribe", dependencies=[Depends(require_parent)])
async def push_unsubscribe(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON erwartet")
    endpoint = str(body.get("endpoint") or "")
    if not endpoint:
        raise HTTPException(status_code=400, detail="endpoint fehlt")
    with db() as conn:
        conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
    return {"removed": endpoint, "subscriptions": push_subscription_count()}


@app.post("/api/v1/parent/push/test", dependencies=[Depends(require_parent)])
def push_test() -> dict:
    return send_push("UltimateTracker", "Testbenachrichtigung – Push funktioniert.")


# --- Tracker (Device) -------------------------------------------------------


@app.post("/api/v1/device/sync", dependencies=[Depends(require_device)])
async def device_sync(request: Request) -> dict:
    """Kombinierter Sync (docs/optimizations.md A5): Position rein, alles andere raus.

    Body: {device_id, battery?, wake_reason?, fw?, position?{lat,lon,hdop,ts}}
    Antwort: {server_time, search_mode, next_poll_s, message?, config, min_fw}
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON erwartet")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON-Objekt erwartet")
    device_id = str(body.get("device_id") or "").strip()
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id fehlt")
    ensure_device(device_id)

    battery = body.get("battery")
    try:
        battery = float(battery) if battery is not None else None
    except (TypeError, ValueError):
        battery = None

    position = body.get("position")
    if isinstance(position, dict):
        loc = {
            "provider": "tracker",
            "beacon_id": device_id,
            "latitude": None,
            "longitude": None,
            "accuracy": position.get("hdop"),
            "reported_at": position.get("ts"),
            "reported_epoch": _to_epoch(position.get("ts")),
        }
        try:
            loc["latitude"] = float(position.get("lat"))
            loc["longitude"] = float(position.get("lon"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="position.lat/position.lon ungültig")
        insert_position(device_id, loc, battery, source="tracker")
        # Fusionierte Position weitergeben: Traccar bekommt je Kind genau eine
        # Position (die beste Quelle), nicht jede Quelle als eigenes Gerät.
        forward_fused_to_traccar(device_id)
        if battery is not None and battery < 15:
            notify_async(
                "Tracker-Akku niedrig",
                f"Gerät {device_id}: nur noch {battery:.0f} % Akku.",
            )

    with db() as conn:
        row = conn.execute(
            "SELECT id, play_file, duration_ms FROM messages "
            "WHERE direction = 'out' AND device_id = ? AND status = 'new' "
            "ORDER BY created_at LIMIT 1",
            (device_id,),
        ).fetchone()
    message = None
    if row is not None:
        path = AUDIO_DIR / row["play_file"]
        message = {
            "id": row["id"],
            "url": f"/api/v1/device/messages/{row['id']}/audio",
            "format": (path.suffix.lstrip(".") or "bin"),
            "size": path.stat().st_size if path.exists() else None,
            "duration_ms": row["duration_ms"],
        }

    fw_version = str(body.get("fw") or "")
    latest = latest_firmware()
    offer = None
    if latest is not None and fw_version and version_is_newer(latest["version"], fw_version):
        offer = {
            "version": latest["version"],
            "url": f"/api/v1/device/firmware/{latest['version']}/download",
            "sha256": latest["sha256"],
            "size": latest["size"],
        }

    return {
        "server_time": now_iso(),
        "search_mode": search_mode_active(device_id),
        "next_poll_s": next_poll_seconds(battery, device_id),
        "message": message,
        "ota": offer,
        "config": {"audio_volume": None},
        "min_fw": None,
    }


@app.post("/api/v1/device/messages", dependencies=[Depends(require_device)])
async def device_upload(
    device_id: str = Form(...),
    duration_ms: int | None = Form(None),
    audio: UploadFile = File(...),
) -> dict:
    """Audio-Uplink des Trackers (IMA-ADPCM-WAV) → für Eltern nach MP3 konvertiert."""
    msg_id = uuid.uuid4().hex[:12]
    raw = await store_upload(audio, msg_id)
    play = AUDIO_DIR / f"{msg_id}.mp3"
    ok = convert(raw, play, FMT_PARENT)
    insert_message(msg_id, "in", device_id, raw, play if ok else raw, duration_ms)
    ensure_device(device_id)
    if setting("notify_new_message"):
        notify_async("Neue Sprachnachricht", f"Gerät {device_id} hat eine Nachricht gesendet.")
        push_async("Neue Sprachnachricht", "Der Tracker hat eine Nachricht gesendet.")
    return {"id": msg_id, "converted": ok}


@app.get("/api/v1/device/pending", dependencies=[Depends(require_device)])
def device_pending(device_id: str) -> dict:
    """Kompatibilitäts-Endpunkt (ältere Firmware); /sync ist der neue Weg."""
    ensure_device(device_id)
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM messages WHERE direction = 'out' AND device_id = ? AND status = 'new' "
            "ORDER BY created_at LIMIT 1",
            (device_id,),
        ).fetchone()
    return {
        "message_id": row["id"] if row else None,
        "download_url": f"/api/v1/device/messages/{row['id']}/audio" if row else None,
        "search_mode": search_mode_active(),
        "next_poll_s": next_poll_seconds(),
    }


@app.get("/api/v1/device/messages/{message_id}/audio", dependencies=[Depends(require_device)])
def device_download(message_id: str) -> FileResponse:
    """Downlink-Datei für den Tracker; markiert die Nachricht als zugestellt."""
    with db() as conn:
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Unbekannte Nachricht")
        conn.execute("UPDATE messages SET status = 'delivered' WHERE id = ?", (message_id,))
    path = AUDIO_DIR / row["play_file"]
    if not path.exists():
        raise HTTPException(status_code=410, detail="Datei fehlt")
    media = "audio/wav" if path.suffix == ".wav" else "application/octet-stream"
    return FileResponse(path, media_type=media, filename=path.name)


# --- Eltern (Parent) --------------------------------------------------------


@app.post("/api/v1/parent/messages", dependencies=[Depends(require_parent)])
async def parent_upload(device_id: str = Form(...), audio: UploadFile = File(...)) -> dict:
    """Sprachnachricht der Eltern (Browser: Opus/WebM) → IMA-ADPCM-WAV für den Tracker."""
    msg_id = uuid.uuid4().hex[:12]
    raw = await store_upload(audio, msg_id)
    play = AUDIO_DIR / f"{msg_id}.wav"
    ok = convert(raw, play, FMT_DEVICE)
    insert_message(msg_id, "out", device_id, raw, play if ok else raw, None)
    ensure_device(device_id)
    return {"id": msg_id, "converted": ok}


@app.post("/api/v1/parent/messages/listened", dependencies=[Depends(require_parent)])
def messages_all_listened() -> dict:
    """Alle eingegangenen Nachrichten als gehört markieren (Chat-Status)."""
    with db() as conn:
        cursor = conn.execute(
            "UPDATE messages SET listened_at = ?, status = 'heard' "
            "WHERE direction = 'in' AND listened_at IS NULL",
            (now_iso(),),
        )
        marked = cursor.rowcount
    return {"marked": marked}


@app.post("/api/v1/parent/messages/{message_id}/listened", dependencies=[Depends(require_parent)])
def message_listened(message_id: str) -> dict:
    """Eine Nachricht als gehört markieren."""
    stamp = now_iso()
    with db() as conn:
        row = conn.execute("SELECT id FROM messages WHERE id = ?", (message_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Unbekannte Nachricht")
        conn.execute(
            "UPDATE messages SET listened_at = ?, status = 'heard' WHERE id = ?",
            (stamp, message_id),
        )
    return {"id": message_id, "listened_at": stamp, "status": "heard"}


@app.get("/api/v1/parent/messages", dependencies=[Depends(require_parent)])
def parent_list(device_id: str | None = None, limit: int = 50) -> dict:
    sql = "SELECT * FROM messages"
    args: list = []
    if device_id:
        sql += " WHERE device_id = ?"
        args.append(device_id)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(max(1, min(limit, 200)))
    with db() as conn:
        rows = conn.execute(sql, args).fetchall()
        unheard = conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE direction = 'in' AND listened_at IS NULL "
            + ("AND device_id = ?" if device_id else ""),
            ([device_id] if device_id else []),
        ).fetchone()["n"]
    return {
        "unheard": unheard,
        "messages": [
            {
                "id": r["id"],
                "direction": r["direction"],
                "device_id": r["device_id"],
                "created_at": r["created_at"],
                "status": r["status"],
                "listened_at": r["listened_at"] if "listened_at" in r.keys() else None,
                "duration_ms": r["duration_ms"],
                "audio_url": f"/api/v1/parent/messages/{r['id']}/audio",
            }
            for r in rows
        ]
    }


@app.get("/api/v1/parent/messages/{message_id}/audio", dependencies=[Depends(require_parent)])
def parent_audio(message_id: str) -> FileResponse:
    with db() as conn:
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Unbekannte Nachricht")
        if row["direction"] == "in" and row["status"] == "new":
            conn.execute("UPDATE messages SET status = 'read' WHERE id = ?", (message_id,))
    path = AUDIO_DIR / row["play_file"]
    if not path.exists():
        raise HTTPException(status_code=410, detail="Datei fehlt")
    media = "audio/mpeg" if path.suffix == ".mp3" else "application/octet-stream"
    return FileResponse(path, media_type=media, filename=path.name)


@app.post("/api/v1/parent/search-mode", dependencies=[Depends(require_parent)])
def set_search_mode(active: bool = Form(True), minutes: int | None = Form(None),
                    device_id: str | None = Form(None)) -> dict:
    """Suchmodus setzen/beenden – pro Kind (device_id), sonst global."""
    duration = minutes if minutes else setting("search_mode_minutes")
    until = time.time() + duration * 60 if active else 0
    key = f"search_mode_until:{device_id}" if device_id else "search_mode_until"
    state_set(key, str(until))
    if active:
        suffix = f" (Gerät {device_id})" if device_id else ""
        notify_async("Suchmodus aktiv", f"Der Tracker piept jetzt {duration} Minuten lang.{suffix}")
        push_async("Suchmodus aktiv", f"Der Tracker piept jetzt {duration} Minuten lang.{suffix}")
    return {
        "search_mode": active,
        "until": until,
        "minutes": duration if active else 0,
        "device_id": device_id,
        "next_poll_s": next_poll_seconds(None, device_id),
    }


@app.get("/api/v1/parent/status", dependencies=[Depends(require_parent)])
def parent_status(device_id: str) -> dict:
    """Komprimierte Statusansicht für die Eltern-UI (docs/optimizations.md A9)."""
    with db() as conn:
        device = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        position = conn.execute(
            "SELECT * FROM positions WHERE device_id = ? ORDER BY id DESC LIMIT 1", (device_id,)
        ).fetchone()
        message = conn.execute(
            "SELECT id, direction, created_at, status FROM messages WHERE device_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (device_id,),
        ).fetchone()
        pending = conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE device_id = ? AND direction = 'out' "
            "AND status = 'new'",
            (device_id,),
        ).fetchone()["n"]
        beacon = conn.execute(
            "SELECT provider, beacon_id, latitude, longitude, received_at FROM findmy_locations "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    battery = position["battery"] if position else None
    return {
        "device": dict(device) if device else None,
        "last_position": dict(position) if position else None,
        "last_message": dict(message) if message else None,
        "pending_messages": pending,
        "search_mode": search_mode_active(device_id),
        "next_poll_s": next_poll_seconds(battery, device_id),
        "last_beacon": dict(beacon) if beacon else None,
    }


@app.post("/api/v1/parent/maintenance/cleanup", dependencies=[Depends(require_parent)])
def maintenance_cleanup() -> dict:
    """Retention manuell auslösen (docs/optimizations.md A6)."""
    return run_cleanup()


# --- Geräte-Registry (Identitäten: IMEI ↔ MSISDN ↔ Name) --------------------


@app.get("/api/v1/parent/setup", dependencies=[Depends(require_parent)])
def setup_status() -> dict:
    """Was fehlt noch, bis der Tracker läuft? Grundlage für den Setup-Assistenten.

    Jeder Schritt ist einzeln prüfbar, damit die UI „Weiter" erst freigeben kann,
    wenn der Schritt wirklich erledigt ist (DAU-sicher).
    """
    with db() as conn:
        devices = [dict(row) for row in conn.execute(
            "SELECT * FROM devices ORDER BY created_at").fetchall()]
        positions = conn.execute("SELECT COUNT(*) AS n FROM positions").fetchone()["n"]
        messages = conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"]
        findmy = conn.execute("SELECT COUNT(*) AS n FROM findmy_locations").fetchone()["n"]
        last_position = conn.execute(
            "SELECT device_id, received_at FROM positions ORDER BY id DESC LIMIT 1").fetchone()

    return {
        "steps": {
            "willkommen": True,
            "geraet": bool(devices),
            "sim": any(device.get("iccid") for device in devices),
            "traccar": probe_http("traccar", 8082, "/api/server") == "up",
            "benachrichtigungen": push_subscription_count() > 0,
            # Zertifikat: nur relevant, wenn Caddy läuft (dann gibt es /ca.crt)
            "zertifikat": caddy_available() and CA_FILE.exists(),
            # Apple Find My: Zugangsdaten für macless-haystack hinterlegt?
            "apple": apple_config_status()["configured"],
            "funktionstest": bool(positions or messages or findmy),
        },
        "device": devices[0] if devices else None,
        "device_count": len(devices),
        "counts": {"positions": positions, "messages": messages, "findmy": findmy},
        "last_position": dict(last_position) if last_position else None,
        "sso": {"available": caddy_available(),
                "entry": os.environ.get("SITE_AUDIO", "") or "audio.localhost"},
        # Erststart ohne Terminal: Tokens und Traccar-Zugang zeigt der Assistent an
        "tokens": {"device": device_token(), "parent": parent_token()},
        "traccar": ensure_traccar_admin(),
        "done": bool(devices) and bool(positions or messages),
        "checked_at": now_iso(),
    }


@app.get("/api/v1/parent/beacons", dependencies=[Depends(require_parent)])
def beacons_list() -> dict:
    """Bekannte Find-My-Beacons mit Zuordnung zum Kind (Sensor-Fusion)."""
    assignments = beacon_assignments()
    with db() as conn:
        rows = conn.execute(
            "SELECT provider, beacon_id, MAX(received_at) AS seen, COUNT(*) AS n "
            "FROM findmy_locations GROUP BY provider, lower(beacon_id) ORDER BY beacon_id"
        ).fetchall()
        devices = conn.execute("SELECT id, name FROM devices ORDER BY created_at").fetchall()
    return {
        "beacons": [
            {
                "provider": row["provider"],
                "beacon_id": row["beacon_id"],
                "last_seen": row["seen"],
                "positions": row["n"],
                "device_id": assignments.get((row["beacon_id"] or "").lower(), ""),
            }
            for row in rows
        ],
        "devices": [dict(row) for row in devices],
        "trust": SOURCE_TRUST,
    }


@app.put("/api/v1/parent/beacons/{beacon_id}", dependencies=[Depends(require_parent)])
async def beacon_assign(beacon_id: str, request: Request) -> dict:
    """Beacon einem Kind zuordnen (device_id leer = Zuordnung aufheben).

    Erst durch die Zuordnung fließen die Find-My-Positionen in die fusionierte
    Position des Kindes – und Traccar bekommt weiterhin nur **ein** Gerät je Kind.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON erwartet")
    device_id = str(body.get("device_id") or "").strip()
    provider = str(body.get("provider") or "").strip()
    with db() as conn:
        conn.execute("DELETE FROM beacons WHERE lower(beacon_id) = lower(?)", (beacon_id,))
        if device_id:
            conn.execute(
                "INSERT INTO beacons(beacon_id, provider, device_id, created_at) VALUES(?, ?, ?, ?)",
                (beacon_id, provider, device_id, now_iso()),
            )
    return {"beacon_id": beacon_id, "device_id": device_id}


@app.get("/api/v1/parent/fused", dependencies=[Depends(require_parent)])
def parent_fused(device_id: str) -> dict:
    """Fusionierte Position eines Kindes samt Quellen (Sensor-Fusion)."""
    best = best_position(device_id)
    if best is None:
        raise HTTPException(status_code=404, detail="Keine Position für dieses Gerät")
    return best


@app.get("/api/v1/parent/devices", dependencies=[Depends(require_parent)])
def devices_list() -> dict:
    with db() as conn:
        rows = conn.execute("SELECT * FROM devices ORDER BY created_at").fetchall()
    return {"devices": [dict(r) for r in rows]}


@app.put("/api/v1/parent/devices/{device_id}", dependencies=[Depends(require_parent)])
async def device_upsert(device_id: str, request: Request) -> dict:
    """Gerät anlegen/aktualisieren. Body: {"name": "...", "imei": "...", "msisdn": "...", "notes": "..."}"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON erwartet")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON-Objekt erwartet")
    fields = {key: str(body.get(key, "") or "") for key in ("name", "imei", "msisdn", "iccid", "notes")}
    with db() as conn:
        conn.execute(
            "INSERT INTO devices(id, name, imei, msisdn, iccid, notes, created_at) VALUES(?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name = excluded.name, imei = excluded.imei, "
            "msisdn = excluded.msisdn, iccid = excluded.iccid, notes = excluded.notes",
            (device_id, fields["name"] or device_id, fields["imei"], fields["msisdn"],
             fields["iccid"], fields["notes"], now_iso()),
        )
    return {"id": device_id, **fields}


@app.delete("/api/v1/parent/devices/{device_id}", dependencies=[Depends(require_parent)])
def device_delete(device_id: str) -> dict:
    with db() as conn:
        conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    return {"deleted": device_id}


@app.get("/api/v1/parent/sim/messages", dependencies=[Depends(require_parent)])
def sim_messages(limit: int = 50) -> dict:
    """Per Echtzeit-Subscription empfangene SMS (Gerät → Server / Server → Gerät)."""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM sim_sms ORDER BY id DESC LIMIT ?", (max(1, min(limit, 200)),)
        ).fetchall()
    return {"count": len(rows), "messages": [dict(row) for row in rows]}


# --- 1NCE-SMS (serververmittelt, docs/sms.md) -------------------------------


@app.get("/api/v1/parent/sms/status", dependencies=[Depends(require_parent)])
def sms_status() -> dict:
    """SIMs des Kontos inkl. SMS-Kontingent (anbieterneutral)."""
    provider = sim_provider()
    if provider is None or not provider.configured():
        return {
            "configured": False,
            "provider": provider.name if provider else None,
            "hint": "SIM_PROVIDER und Zugangsdaten in server/.env setzen (docs/sim-providers.md)",
        }
    try:
        sims = provider.list_sims()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SIM-Provider nicht erreichbar: {exc}")
    return {
        "configured": True,
        "provider": provider.name,
        "count": len(sims),
        "sims": [sim.as_dict() for sim in sims[:10]],
    }


@app.post("/api/v1/parent/sms", dependencies=[Depends(require_parent)])
async def sms_send(request: Request) -> dict:
    """MT-SMS an den Tracker senden (serververmittelt). Body: {"iccid": "…", "text": "…"}"""
    provider = sim_provider()
    if provider is None or not provider.configured():
        raise HTTPException(status_code=503, detail="Kein SIM-Provider konfiguriert")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON erwartet")
    iccid = str(body.get("iccid") or "").strip()
    text = str(body.get("text") or "").strip()
    if not iccid or not text:
        raise HTTPException(status_code=400, detail="iccid und text erforderlich")
    if len(text) > 160:
        raise HTTPException(status_code=400, detail="maximal 160 Zeichen (kein Multipart-Versand)")
    try:
        result = provider.send_sms(iccid, text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SMS-Versand fehlgeschlagen: {exc}")
    return {
        "sent": True,
        "iccid": iccid,
        "provider": provider.name,
        "id": result.get("id"),
        "hint": "Zustellung beim nächsten Netz-Attach",
    }


@app.get("/api/v1/parent/sms", dependencies=[Depends(require_parent)])
def sms_list(iccid: str, limit: int = 20) -> dict:
    """MT-/MO-SMS einer SIM (Plattform → Gerät bzw. Gerät → Plattform)."""
    provider = sim_provider()
    if provider is None or not provider.configured():
        raise HTTPException(status_code=503, detail="Kein SIM-Provider konfiguriert")
    try:
        messages = provider.list_sms(iccid, limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SMS-Abfrage fehlgeschlagen: {exc}")
    return {
        "iccid": iccid,
        "provider": provider.name,
        "total": len(messages),
        "messages": [message.as_dict() for message in messages],
    }


# --- Find My (Apple / Google) ----------------------------------------------


@app.post("/api/v1/findmy/locations")
async def findmy_ingest(request: Request, x_auth_token: str | None = Header(default=None)) -> dict:
    """Ingest für Find-My-Positionen (Apple/Google-Gegenstücke).

    Tolerantes Schema: akzeptiert Einzelobjekt oder Liste; erkennt gängige
    Feldnamen (lat/latitude, lon/lng/longitude, id/beacon_id/device_id, ...).
    Optionaler Token: FINDMY_TOKEN (leer = offen; Endpunkt dann nur intern erreichbar halten).
    """
    if FINDMY_TOKEN and not token_ok(FINDMY_TOKEN, x_auth_token):
        raise HTTPException(status_code=401, detail="Ungültiges Find-My-Token")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON erwartet")
    items = payload if isinstance(payload, list) else [payload]
    stored = 0
    forwarded = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        loc = extract_location(item)
        if loc is None:
            continue
        insert_findmy(loc, item)
        stored += 1
        # Nur zugeordnete Beacons fließen in die fusionierte Position des Kindes.
        # Nicht zugeordnete Beacons erscheinen nur in der Bridge (Karte/UI), damit
        # Traccar nicht mit Fremdgeräten zugestellt wird.
        child = beacon_assignments().get((loc.get("beacon_id") or "").lower())
        if child and forward_fused_to_traccar(child):
            forwarded += 1
    return {"stored": stored, "forwarded": forwarded}


@app.get("/api/v1/parent/findmy/locations", dependencies=[Depends(require_parent)])
def findmy_list(provider: str | None = None, beacon_id: str | None = None, limit: int = 20) -> dict:
    sql = "SELECT provider, beacon_id, latitude, longitude, accuracy, reported_at, received_at FROM findmy_locations"
    where: list[str] = []
    args: list = []
    if provider:
        where.append("provider = ?")
        args.append(provider)
    if beacon_id:
        where.append("beacon_id = ?")
        args.append(beacon_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(max(1, min(limit, 200)))
    with db() as conn:
        rows = conn.execute(sql, args).fetchall()
    return {"locations": [dict(r) for r in rows]}


# --- Firmware (OTA, docs/optimizations.md B7) -------------------------------


@app.post("/api/v1/parent/firmware", dependencies=[Depends(require_parent)])
async def firmware_upload(
    version: str = Form(...),
    notes: str = Form(""),
    firmware: UploadFile = File(...),
) -> dict:
    """Firmware-Binary hochladen (Eltern-Token). Version im Format 1.2.3."""
    if parse_version(version) is None:
        raise HTTPException(status_code=400, detail="Version muss wie 1.2.3 aussehen")
    data = await firmware.read()
    if not data:
        raise HTTPException(status_code=400, detail="Leere Datei")
    limit = int(MAX_UPLOAD_MB * 1024 * 1024 * 4)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"Firmware zu groß (>{limit} Bytes)")
    digest = hashlib.sha256(data).hexdigest()
    path = FIRMWARE_DIR / f"{version}.bin"
    path.write_bytes(data)
    with db() as conn:
        conn.execute(
            "INSERT INTO firmware(version, filename, sha256, size, notes, uploaded_at) "
            "VALUES(?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(version) DO UPDATE SET filename = excluded.filename, "
            "sha256 = excluded.sha256, size = excluded.size, notes = excluded.notes, "
            "uploaded_at = excluded.uploaded_at",
            (version, path.name, digest, len(data), notes, now_iso()),
        )
    return {"version": version, "sha256": digest, "size": len(data)}


@app.get("/api/v1/parent/firmware", dependencies=[Depends(require_parent)])
def firmware_list() -> dict:
    with db() as conn:
        rows = conn.execute(
            "SELECT version, sha256, size, notes, uploaded_at FROM firmware ORDER BY uploaded_at DESC"
        ).fetchall()
    return {"firmware": [dict(r) for r in rows]}


@app.delete("/api/v1/parent/firmware/{version}", dependencies=[Depends(require_parent)])
def firmware_delete(version: str) -> dict:
    with db() as conn:
        row = conn.execute("SELECT filename FROM firmware WHERE version = ?", (version,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Unbekannte Version")
        conn.execute("DELETE FROM firmware WHERE version = ?", (version,))
    (FIRMWARE_DIR / row["filename"]).unlink(missing_ok=True)
    return {"deleted": version}


@app.get("/api/v1/device/firmware/latest", dependencies=[Depends(require_device)])
def firmware_latest(fw: str = "") -> dict:
    """OTA-Angebot für den Tracker (update=false, wenn nichts Neueres vorliegt)."""
    latest = latest_firmware()
    if latest is None or not version_is_newer(latest["version"], fw):
        return {"update": False}
    return {
        "update": True,
        "version": latest["version"],
        "url": f"/api/v1/device/firmware/{latest['version']}/download",
        "sha256": latest["sha256"],
        "size": latest["size"],
    }


@app.get("/api/v1/device/firmware/{version}/download", dependencies=[Depends(require_device)])
def firmware_download(version: str) -> FileResponse:
    with db() as conn:
        row = conn.execute("SELECT * FROM firmware WHERE version = ?", (version,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Unbekannte Version")
    path = FIRMWARE_DIR / row["filename"]
    if not path.exists():
        raise HTTPException(status_code=410, detail="Datei fehlt")
    return FileResponse(path, media_type="application/octet-stream", filename=path.name)


# --- Traccar-Webhook --------------------------------------------------------


@app.post("/api/v1/traccar/events")
def traccar_events(payload: dict, x_auth_token: str | None = Header(default=None)) -> dict:
    """Empfänger für Traccar `event.forward` (Geofence/Alarm/Status)."""
    if WEBHOOK_TOKEN and not token_ok(WEBHOOK_TOKEN, x_auth_token):
        raise HTTPException(status_code=401, detail="Ungültiges Webhook-Token")
    entry = {"received_at": now_iso(), "payload": payload}
    with EVENTS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"ok": True}
