#!/usr/bin/env python3
"""Tracker-Simulator – spielt den ESP32-Tracker gegen den echten Server-Stack.

Testet ohne Hardware: Sync (Position + Konfiguration), Audio-Uplink, Downlink-Poll.
Siehe docs/simulation.md.

Aufruf (in der WSL, Stack läuft):
    python3 scripts/simulate-tracker.py --device TEST123 --cycles 3
    python3 scripts/simulate-tracker.py --device TEST123 --send-audio
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import random
import struct
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path


def read_env(path: Path) -> dict:
    data: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                data[key.strip()] = value.strip()
    return data


def http(url: str, method: str = "GET", token: str | None = None,
         data: bytes | None = None, content_type: str | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(url, method=method, data=data)
    if token:
        request.add_header("X-Auth-Token", token)
    if content_type:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = "----UltimateTracker" + os.urandom(8).hex()
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    for name, (filename, content, ctype) in files.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
            f'filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
            + content
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def make_wav(seconds: float = 2.0, rate: int = 8000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / rate)))
            for i in range(int(rate * seconds))
        )
        wav.writeframes(frames)
    return buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description="Tracker-Simulator für den UltimateTracker-Stack")
    parser.add_argument("--base", default="http://localhost:8085", help="Bridge-Basis-URL")
    parser.add_argument("--device", default="TEST123", help="Geräte-ID (IMEI)")
    parser.add_argument("--cycles", type=int, default=3, help="Anzahl Sync-Zyklen")
    parser.add_argument("--interval", type=float, default=2.0, help="Sekunden zwischen Zyklen")
    parser.add_argument("--send-audio", action="store_true", help="Audio-Uplink simulieren")
    parser.add_argument("--env", default=str(Path.home() / "UltimateTracker/server/.env"),
                        help="Pfad zur server/.env (für DEVICE_TOKEN)")
    parser.add_argument("--token", default=None, help="Device-Token (sonst aus .env)")
    args = parser.parse_args()

    token = args.token or read_env(Path(args.env)).get("DEVICE_TOKEN")
    if not token:
        print(f"Kein Device-Token gefunden ({args.env}) – --token verwenden.", file=sys.stderr)
        return 2

    base = args.base.rstrip("/")
    lat, lon = 48.1372, 11.5756
    battery = 92.0
    failures = 0

    print(f"[sim] Gerät {args.device} gegen {base} – {args.cycles} Zyklen")
    for cycle in range(1, args.cycles + 1):
        lat += random.uniform(-0.0008, 0.0008)
        lon += random.uniform(-0.0008, 0.0008)
        battery = max(5.0, battery - random.uniform(0.3, 1.2))
        body = json.dumps({
            "device_id": args.device,
            "battery": round(battery, 1),
            "wake_reason": random.choice(["motion", "timer", "ptt"]),
            "fw": "sim-0.1",
            "position": {"lat": round(lat, 6), "lon": round(lon, 6), "hdop": 1.4,
                         "ts": int(time.time())},
        }).encode()

        status, raw = http(f"{base}/api/v1/device/sync", "POST", token, body, "application/json")
        if status != 200:
            print(f"[sim] Zyklus {cycle}: Sync fehlgeschlagen (HTTP {status}) {raw[:200]!r}")
            failures += 1
        else:
            data = json.loads(raw)
            print(f"[sim] Zyklus {cycle}: pos={lat:.5f},{lon:.5f} batt={battery:.1f}% "
                  f"next_poll={data['next_poll_s']}s search={data['search_mode']} "
                  f"message={'ja' if data.get('message') else 'nein'}")
            message = data.get("message")
            if message:
                code, blob = http(f"{base}{message['url']}", "GET", token)
                print(f"[sim]   Downlink geladen: HTTP {code}, {len(blob)} Bytes "
                      f"(Format {message['format']})")

        if args.send_audio and cycle == 1:
            audio = make_wav(2.0)
            payload, ctype = multipart({"device_id": args.device, "duration_ms": "2000"},
                                       {"audio": ("message.wav", audio, "audio/wav")})
            status, raw = http(f"{base}/api/v1/device/messages", "POST", token, payload, ctype)
            print(f"[sim] Audio-Uplink: HTTP {status} {raw[:120]!r}")
            if status != 200:
                failures += 1

        if cycle < args.cycles:
            time.sleep(args.interval)

    print(f"[sim] Fertig. Fehler: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
