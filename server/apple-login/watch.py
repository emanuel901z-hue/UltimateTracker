#!/usr/bin/env python3
"""Helfer für die Apple-Anmeldung (2FA) – Teil des Compose-Profils `findmy`.

Das Image `macless-haystack` fragt den SMS-2FA-Code über `input()` ab; in einem
Container ohne Terminal endet das im `EOFError`. Dieser Helfer läuft dauerhaft,
führt die Anmeldung auf Anforderung aus und reicht den Code nach – so lässt sich
der Code aus der Eltern-UI eingeben (`docs/findmy.md`).

Steuerung ausschließlich über Dateien im geteilten Volume `macless-data`
(im Container `/app/endpoint/data`), damit die Bridge **keinen** Docker-Zugriff
braucht:

  apple-login/start      → Anmeldung starten (wird konsumiert)
  apple-login/code       → SMS-Code (wird konsumiert)
  apple-login/status     → JSON {"state": …} (schreibt der Helfer)
  apple-login/log        → Ausgabe der Anmeldung (schreibt der Helfer)
  apple-login/heartbeat  → Zeitstempel (schreibt der Helfer: „läuft er?")

Zustände: idle · starting · waiting · verifying · done · error
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

DIR = pathlib.Path(os.environ.get("APPLE_LOGIN_DIR", "/app/endpoint/data/apple-login"))
AUTH = pathlib.Path(os.environ.get("APPLE_AUTH_FILE", "/app/endpoint/data/auth.json"))
DEFAULT_CMD = (
    "python -u -c \"from endpoint.register.apple_cryptography import getAuth; "
    "getAuth(regenerate=True)\""
)
# Für Tests/andere Images überschreibbar (z. B. ein Skript, das einen Code abfragt).
CMD = os.environ.get("APPLE_LOGIN_CMD", "").strip() or DEFAULT_CMD
CWD = os.environ.get("APPLE_LOGIN_CWD", "/app")
POLL_S = float(os.environ.get("APPLE_LOGIN_POLL_S", "1"))


def write_status(state: str) -> None:
    tmp = DIR / "status.tmp"
    tmp.write_text(json.dumps({"state": state}), encoding="utf-8")
    tmp.replace(DIR / "status")


def log_tail(limit: int = 4000) -> str:
    try:
        return (DIR / "log").read_text(encoding="utf-8", errors="replace")[-limit:]
    except OSError:
        return ""


def run_login() -> None:
    """Anmeldung ausführen; den SMS-Code aus `code` nachliefern."""
    DIR.mkdir(parents=True, exist_ok=True)
    before = AUTH.stat().st_mtime if AUTH.exists() else 0.0
    # Nur das Protokoll zurücksetzen – einen bereits hinterlegten Code (die UI
    # darf ihn auch vor dem Prompt senden) NICHT verwerfen. Die Bridge räumt
    # beim Start ohnehin `code` weg.
    (DIR / "log").unlink(missing_ok=True)
    with (DIR / "log").open("w", encoding="utf-8") as log:
        write_status("starting")
        proc = subprocess.Popen(
            CMD, shell=True, cwd=CWD, stdin=subprocess.PIPE,
            stdout=log, stderr=subprocess.STDOUT,
        )
        prompted = False
        while proc.poll() is None:
            code_file = DIR / "code"
            if code_file.exists():
                code = code_file.read_text(encoding="utf-8").strip()
                code_file.unlink(missing_ok=True)
                if code:
                    try:
                        proc.stdin.write((code + "\n").encode())
                        proc.stdin.flush()
                        write_status("verifying")
                    except (BrokenPipeError, OSError):
                        pass
            elif not prompted and "2FA code" in log_tail():
                # Der Login hat gerade den Code angefordert (Apple hat die SMS
                # geschickt) – jetzt darf der Nutzer ihn eintragen.
                prompted = True
                write_status("waiting")
            time.sleep(POLL_S)
        try:
            proc.stdin.close()
        except OSError:
            pass
        proc.wait()
    after = AUTH.stat().st_mtime if AUTH.exists() else 0.0
    write_status("done" if after > before else "error")


def main() -> int:
    DIR.mkdir(parents=True, exist_ok=True)
    write_status("idle")
    print(f"[apple-login] bereit, warte auf {DIR}/start", flush=True)
    while True:
        (DIR / "heartbeat").write_text(str(time.time()), encoding="utf-8")
        if (DIR / "start").exists():
            (DIR / "start").unlink(missing_ok=True)
            print("[apple-login] Anmeldung startet", flush=True)
            try:
                run_login()
            except Exception as exc:  # den Helfer nie sterben lassen
                print(f"[apple-login] Fehler: {exc!r}", flush=True)
                write_status("error")
            print(f"[apple-login] Ende: {log_tail(200)!r}", flush=True)
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
