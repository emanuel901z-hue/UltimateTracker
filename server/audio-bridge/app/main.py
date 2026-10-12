"""Audio-Bridge – Sprachnachrichten, Geräte-Registry, Find-My-Ingest und Sync.

Endpunkte und Datenmodell: docs/architecture.md (Abschnitt 3).
Konfiguration über Umgebungsvariablen (siehe server/.env.example).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response

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
SEARCH_MODE_MINUTES = env_int("SEARCH_MODE_MINUTES", 30)
MAX_UPLOAD_MB = env_float("MAX_UPLOAD_MB", 2.0)
RETENTION_DAYS = env_int("RETENTION_DAYS", 30)
APPRISE_URLS = os.environ.get("APPRISE_URLS", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:admin@example.org")

# SIM-/SMS-Anbieter (anbieterneutral, docs/sim-providers.md):
#   SIM_PROVIDER        = nce | generic | none   (Default: nce, wenn Zugangsdaten da)
#   SIM_PROVIDER_CONFIG = Pfad zu einer JSON-Konfiguration für "generic"
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


def search_mode_active() -> bool:
    until = state_get("search_mode_until")
    return bool(until) and float(until) > time.time()


def next_poll_seconds(battery: float | None = None) -> int:
    """Server-getriebenes Poll-Intervall (docs/optimizations.md A5/B4)."""
    if search_mode_active():
        return SEARCH_POLL_INTERVAL_S
    if battery is not None and battery < 15:
        return POLL_INTERVAL_S * 2
    return POLL_INTERVAL_S


def ensure_device(device_id: str) -> None:
    """Unbekannte Geräte automatisch anlegen (analog Traccar registerUnknown)."""
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO devices(id, name, created_at) VALUES(?, ?, ?)",
            (device_id, device_id, now_iso()),
        )


def validate_config() -> None:
    """Fail-fast: klare Meldung statt stiller 401-Fehler (docs/optimizations.md A6)."""
    problems = []
    for name, value in (("DEVICE_TOKEN", DEVICE_TOKEN), ("PARENT_TOKEN", PARENT_TOKEN)):
        if not value or value.startswith("change-me"):
            problems.append(name)
    if problems:
        raise RuntimeError(
            "Konfiguration unvollständig: "
            + ", ".join(problems)
            + " sind leer oder noch Platzhalter – server/.env prüfen (Vorlage: .env.example)."
        )


# --- Auth -------------------------------------------------------------------


def token_ok(expected: str, provided: str | None) -> bool:
    return bool(expected) and provided is not None and secrets.compare_digest(expected, provided)


def require_device(x_auth_token: str | None = Header(default=None)) -> None:
    if not token_ok(DEVICE_TOKEN, x_auth_token):
        raise HTTPException(status_code=401, detail="Ungültiges Device-Token")


def require_parent(x_auth_token: str | None = Header(default=None)) -> None:
    if not token_ok(PARENT_TOKEN, x_auth_token):
        raise HTTPException(status_code=401, detail="Ungültiges Parent-Token")


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


# --- Retention --------------------------------------------------------------


def run_cleanup() -> dict:
    """Löscht Nachrichten/Audiodateien älter als RETENTION_DAYS (0 = aus)."""
    if RETENTION_DAYS <= 0:
        return {"removed": 0, "retention_days": 0, "disabled": True}
    cutoff = time.time() - RETENTION_DAYS * 86400
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
    return {"removed": removed, "retention_days": RETENTION_DAYS}


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
            return True
    except Exception as exc:  # Diagnose: Fehler nicht still verschlucken
        print(f"[forward] Traccar-Forward fehlgeschlagen ({type(exc).__name__}: {exc}) {url}", flush=True)
        return False


# --- App --------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_config()
    init_db()
    task = asyncio.create_task(retention_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="UltimateTracker Audio-Bridge", version="0.3.0", lifespan=lifespan)


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
    }


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
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
        forward_to_traccar(loc)
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
        "search_mode": search_mode_active(),
        "next_poll_s": next_poll_seconds(battery),
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
    return {
        "messages": [
            {
                "id": r["id"],
                "direction": r["direction"],
                "device_id": r["device_id"],
                "created_at": r["created_at"],
                "status": r["status"],
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
def set_search_mode(active: bool = Form(True), minutes: int | None = Form(None)) -> dict:
    """Suchmodus setzen/beenden (Tracker pollt dann häufiger und piept)."""
    duration = minutes if minutes else SEARCH_MODE_MINUTES
    until = time.time() + duration * 60 if active else 0
    state_set("search_mode_until", str(until))
    if active:
        notify_async("Suchmodus aktiv", f"Der Tracker piept jetzt {duration} Minuten lang.")
        push_async("Suchmodus aktiv", f"Der Tracker piept jetzt {duration} Minuten lang.")
    return {
        "search_mode": active,
        "until": until,
        "minutes": duration if active else 0,
        "next_poll_s": next_poll_seconds(),
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
        "search_mode": search_mode_active(),
        "next_poll_s": next_poll_seconds(battery),
        "last_beacon": dict(beacon) if beacon else None,
    }


@app.post("/api/v1/parent/maintenance/cleanup", dependencies=[Depends(require_parent)])
def maintenance_cleanup() -> dict:
    """Retention manuell auslösen (docs/optimizations.md A6)."""
    return run_cleanup()


# --- Geräte-Registry (Identitäten: IMEI ↔ MSISDN ↔ Name) --------------------


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
        if forward_to_traccar(loc):
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
