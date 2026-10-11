#!/usr/bin/env python3
"""Kleiner Echo-Server für Tests: loggt jede Anfrage (Methode, Pfad, Header, Body)
und antwortet mit 200 {"ok":true}.

Nützlich für: Apprise-Benachrichtigungen, Traccar-Webhooks, generische HTTP-Ziele.
Siehe docs/simulation.md.

Aufruf:  python3 scripts/dev-echo-server.py [port]
Als Container im Stack-Netz:
    docker run -d --rm --name ut-echo --network ultimatetracker_utnet \
      -v "$PWD/scripts:/s:ro" -w /s python:3.12-slim python dev-echo-server.py 9999
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        print(f"[echo] {self.command} {self.path}", flush=True)
        for key, value in self.headers.items():
            print(f"[echo]   {key}: {value}", flush=True)
        if body:
            print(f"[echo]   body: {body[:500]!r}", flush=True)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    do_GET = do_POST = do_PUT = do_DELETE = _handle

    def log_message(self, *args) -> None:  # Standard-Logging unterdrücken
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9999
    print(f"[echo] hört auf 0.0.0.0:{port}", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
