"""Audio-Bridge – Sprachnachrichten zwischen Tracker und Eltern-Web-UI.

Endpunkte und Datenmodell: docs/architecture.md (Abschnitt 3).
Konfiguration über Umgebungsvariablen (siehe server/.env.example).
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
AUDIO_DIR = DATA_DIR / "audio"
DB_PATH = DATA_DIR / "bridge.sqlite3"
EVENTS_LOG = DATA_DIR / "events.jsonl"
STATIC_DIR = Path(__file__).parent / "static"

DEVICE_TOKEN = os.environ.get("DEVICE_TOKEN", "")
PARENT_TOKEN = os.environ.get("PARENT_TOKEN", "")
WEBHOOK_TOKEN = os.environ.get("TRACCAR_WEBHOOK_TOKEN", "")
SEARCH_MODE_MINUTES = int(os.environ.get("SEARCH_MODE_MINUTES", "30"))

# Zielformate (siehe docs/decisions.md D-002: 8 kHz mono, IMA-ADPCM für den Tracker)
FMT_DEVICE = ["-c:a", "adpcm_ima_wav", "-ar", "8000", "-ac", "1"]
FMT_PARENT = ["-c:a", "libmp3lame", "-b:a", "48k", "-ar", "8000", "-ac", "1"]


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    with db() as conn:
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


def token_ok(expected: str, provided: str | None) -> bool:
    return bool(expected) and provided is not None and secrets.compare_digest(expected, provided)


def require_device(x_auth_token: str | None = Header(default=None)) -> None:
    if not token_ok(DEVICE_TOKEN, x_auth_token):
        raise HTTPException(status_code=401, detail="Ungültiges Device-Token")


def require_parent(x_auth_token: str | None = Header(default=None)) -> None:
    if not token_ok(PARENT_TOKEN, x_auth_token):
        raise HTTPException(status_code=401, detail="Ungültiges Parent-Token")


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


def store_upload(upload: UploadFile, msg_id: str) -> Path:
    path = AUDIO_DIR / f"{msg_id}-raw"
    with path.open("wb") as fh:
        shutil.copyfileobj(upload.file, fh)
    return path


def insert_message(
    msg_id: str, direction: str, device_id: str, raw: Path, play: Path, duration_ms: int | None
) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO messages(id, direction, device_id, created_at, raw_file, play_file, duration_ms) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (
                msg_id,
                direction,
                device_id,
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                raw.name,
                play.name,
                duration_ms,
            ),
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="UltimateTracker Audio-Bridge", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "search_mode": search_mode_active()}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


# --- Tracker (Device) -------------------------------------------------------


@app.post("/api/v1/device/messages", dependencies=[Depends(require_device)])
async def device_upload(
    device_id: str = Form(...),
    duration_ms: int | None = Form(None),
    audio: UploadFile = File(...),
) -> dict:
    """Audio-Uplink des Trackers (IMA-ADPCM-WAV) → für Eltern nach MP3 konvertiert."""
    msg_id = uuid.uuid4().hex[:12]
    raw = store_upload(audio, msg_id)
    play = AUDIO_DIR / f"{msg_id}.mp3"
    ok = convert(raw, play, FMT_PARENT)
    insert_message(msg_id, "in", device_id, raw, play if ok else raw, duration_ms)
    return {"id": msg_id, "converted": ok}


@app.get("/api/v1/device/pending", dependencies=[Depends(require_device)])
def device_pending(device_id: str) -> dict:
    """Nächste Nachricht + Suchmodus-Status für den Tracker-Poll."""
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
    raw = store_upload(audio, msg_id)
    play = AUDIO_DIR / f"{msg_id}.wav"
    ok = convert(raw, play, FMT_DEVICE)
    insert_message(msg_id, "out", device_id, raw, play if ok else raw, None)
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
    return {"search_mode": active, "until": until, "minutes": duration if active else 0}


# --- Traccar-Webhook --------------------------------------------------------


@app.post("/api/v1/traccar/events")
def traccar_events(payload: dict, x_auth_token: str | None = Header(default=None)) -> dict:
    """Empfänger für Traccar `event.forward` (Geofence/Alarm/Status)."""
    if WEBHOOK_TOKEN and not token_ok(WEBHOOK_TOKEN, x_auth_token):
        raise HTTPException(status_code=401, detail="Ungültiges Webhook-Token")
    entry = {"received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "payload": payload}
    with EVENTS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"ok": True}
