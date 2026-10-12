#!/usr/bin/env python3
"""Rendert die Eltern-UI in headless Chrome und prüft sie wirklich.

Aufruf:
    python scripts/ui-check.py [--base http://localhost:8085] [--out ui-shots]
                               [--chrome /pfad/zu/chrome]

Was passiert:
  * Anmeldung über die API (Passwort aus server/.env oder UT_PARENT_PASSWORD)
  * Screenshots aller Tabs in Desktop- (1280×900) und Mobil-Ansicht (390×844)
  * Auswertung des Accessibility-Baums im *gerenderten* Zustand:
    - kein Eingabefeld ohne zugänglichen Namen (harter Fehler)
    - Zählung von Tabs/Panels/Buttons/Statusregionen zur Kontrolle
  * Exit-Code 0 = bestanden (für die CI geeignet)

Warum zusätzlich zu scripts/check-ui-a11y.py? Der statische Check liest den
Quelltext, dieser prüft das Ergebnis nach HTML-Parsing, CSS und JavaScript –
also das, was Nutzer tatsächlich sehen und bedienen.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

try:
    import websockets
except ImportError:
    print("Bitte zuerst installieren:  pip install websockets")
    sys.exit(2)

TABS = ("einrichtung", "uebersicht", "karte", "nachricht", "geraete", "betrieb", "konto")
VIEWPORTS = {"desktop": (1280, 900, 1.0), "mobile": (390, 844, 2.0)}
CHROME_CANDIDATES = (
    os.environ.get("CHROME", ""),
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/opt/google/chrome/chrome",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


def find_chrome(explicit: str | None) -> str:
    for candidate in (explicit, *CHROME_CANDIDATES):
        if not candidate:
            continue
        if Path(candidate).exists():
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    raise SystemExit("Chrome nicht gefunden – mit --chrome /pfad/zu/chrome angeben.")


def parent_password() -> str:
    password = os.environ.get("UT_PARENT_PASSWORD", "").strip()
    if password:
        return password
    env_file = Path("server/.env")
    if env_file.exists():
        match = re.search(r"^PARENT_PASSWORD=(.+)$", env_file.read_text(encoding="utf-8"), re.M)
        if match and match.group(1).strip():
            return match.group(1).strip()
    raise SystemExit("Kein Eltern-Passwort: server/.env (PARENT_PASSWORD) oder UT_PARENT_PASSWORD setzen.")


def login(base: str, username: str, password: str) -> str:
    request = urllib.request.Request(
        f"{base}/api/v1/auth/login",
        data=json.dumps({"username": username, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)["token"]


class CDP:
    def __init__(self, socket) -> None:
        self.socket = socket
        self.counter = 0

    async def send(self, method: str, **params):
        self.counter += 1
        await self.socket.send(json.dumps({"id": self.counter, "method": method, "params": params}))
        while True:
            message = json.loads(await self.socket.recv())
            if message.get("id") == self.counter:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})

    async def evaluate(self, expression: str):
        result = await self.send("Runtime.evaluate", expression=expression, returnByValue=True,
                                 awaitPromise=True)
        return result.get("result", {}).get("value")


async def run(chrome: str, base: str, out: Path, username: str) -> int:
    token = login(base, username, parent_password())
    out.mkdir(parents=True, exist_ok=True)
    port = 9333
    process = subprocess.Popen([
        chrome, "--headless=new", f"--remote-debugging-port={port}", "--remote-allow-origins=*",
        "--no-first-run", "--no-default-browser-check", "--disable-gpu", "--hide-scrollbars",
        f"--user-data-dir={out / 'profile'}", "--window-size=1280,900", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        targets = None
        for _ in range(60):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1))
                break
            except Exception:
                time.sleep(0.5)
        if not targets:
            print("Chrome antwortet nicht auf dem Debug-Port")
            return 1
        page = next(target for target in targets if target["type"] == "page")

        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=60_000_000) as socket:
            cdp = CDP(socket)
            await cdp.send("Page.enable")
            await cdp.send("Runtime.enable")
            await cdp.send("Accessibility.enable")

            await cdp.send("Page.navigate", url=base)
            await asyncio.sleep(2.0)
            shot = await cdp.send("Page.captureScreenshot", format="png", captureBeyondViewport=True)
            (out / "00-login.png").write_bytes(base64.b64decode(shot["data"]))

            await cdp.evaluate(f"localStorage.setItem('ut_token', {json.dumps(token)})")
            await cdp.send("Page.navigate", url=base)
            await asyncio.sleep(3.0)
            if not await cdp.evaluate("document.getElementById('app') && !document.getElementById('app').hidden"):
                print("Anmeldung im Browser fehlgeschlagen")
                return 1

            for viewport, (width, height, scale) in VIEWPORTS.items():
                await cdp.send("Emulation.setDeviceMetricsOverride", width=width, height=height,
                               deviceScaleFactor=scale, mobile=width < 600)
                for tab in TABS:
                    await cdp.evaluate(f"document.getElementById('tab-{tab}').click()")
                    if tab == "karte":
                        # Karte erst auf Klick laden (Leaflet wird lazy geholt)
                        await cdp.evaluate("document.getElementById('map-load').click()")
                        await asyncio.sleep(3.5)
                    await asyncio.sleep(0.9)
                    shot = await cdp.send("Page.captureScreenshot", format="png", captureBeyondViewport=True)
                    (out / f"{viewport}-{tab}.png").write_bytes(base64.b64decode(shot["data"]))
                    print(f"  {viewport:7} {tab:10} -> {viewport}-{tab}.png")

            tree = await cdp.send("Accessibility.getFullAXTree")
            nodes = tree.get("nodes", [])
            roles: dict[str, int] = {}
            unnamed: list[str] = []
            for node in nodes:
                role = (node.get("role") or {}).get("value", "")
                roles[role] = roles.get(role, 0) + 1
                if role in {"textbox", "combobox", "checkbox", "spinbutton"}:
                    if not (node.get("name") or {}).get("value", "").strip():
                        unnamed.append(str(node.get("nodeId")))

        print(f"\nAccessibility-Baum: {len(nodes)} Knoten")
        for role in ("tablist", "tab", "tabpanel", "button", "textbox", "combobox", "heading", "status"):
            if roles.get(role):
                print(f"  {role}: {roles[role]}")
        if unnamed:
            print(f"\nFEHLER: {len(unnamed)} Eingabefeld(er) ohne zugänglichen Namen")
            return 1
        if roles.get("tab", 0) < len(TABS) or roles.get("tablist", 0) != 1:
            print("\nFEHLER: Tab-Muster im gerenderten Baum unvollständig")
            return 1
        print("\nAlle Prüfungen bestanden (Screenshots in " + str(out) + ")")
        return 0
    finally:
        process.terminate()


def main() -> int:
    parser = argparse.ArgumentParser(description="Eltern-UI in headless Chrome prüfen")
    parser.add_argument("--base", default="http://localhost:8085")
    parser.add_argument("--out", default="ui-shots")
    parser.add_argument("--chrome")
    parser.add_argument("--user", default=os.environ.get("UT_PARENT_USER", "admin"))
    args = parser.parse_args()
    return asyncio.run(run(find_chrome(args.chrome), args.base.rstrip("/"), Path(args.out), args.user))


if __name__ == "__main__":
    sys.exit(main())
