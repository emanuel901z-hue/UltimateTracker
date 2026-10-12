#!/usr/bin/env python3
"""Erzeugt die PWA-/App-Icons als PNG (ohne externe Bibliotheken).

Warum: iOS verlangt für `apple-touch-icon` ein PNG (SVG wird ignoriert), und
Android/Chrome möchten 192/512 px. Das Motiv entspricht dem SVG-Icon im
Manifest (dunkle Fläche, hellblauer Kopf + Körper).

Aufruf:  python scripts/generate-icons.py
Ergebnis: server/audio-bridge/app/static/icon-{180,192,512}.png
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

BACKGROUND = (31, 41, 55)   # #1f2937
FOREGROUND = (99, 164, 241)  # #63a4f1
SIZES = (180, 192, 512)
OUT_DIR = Path(__file__).resolve().parent.parent / "server" / "audio-bridge" / "app" / "static"


def png_bytes(width: int, height: int, rows: list[bytes]) -> bytes:
    """Minimaler PNG-Encoder (8 Bit RGBA)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + row for row in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def inside_rounded(x: float, y: float, size: float, radius: float) -> bool:
    """Punkt innerhalb eines abgerundeten Quadrats?"""
    if radius <= x <= size - radius or radius <= y <= size - radius:
        return 0 <= x <= size and 0 <= y <= size
    corner_x = radius if x < radius else size - radius
    corner_y = radius if y < radius else size - radius
    return (x - corner_x) ** 2 + (y - corner_y) ** 2 <= radius ** 2


def render(size: int) -> bytes:
    radius = size * 0.17
    head = (size * 0.5, size * 0.375, size * 0.145)
    body = (size * 0.5, size * 0.95, size * 0.30)

    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            if not inside_rounded(px, py, size, radius):
                row += bytes((0, 0, 0, 0))
                continue
            color = BACKGROUND
            if (px - head[0]) ** 2 + (py - head[1]) ** 2 <= head[2] ** 2:
                color = FOREGROUND
            elif (px - body[0]) ** 2 + (py - body[1]) ** 2 <= body[2] ** 2 and py > size * 0.62:
                color = FOREGROUND
            row += bytes((*color, 255))
        rows.append(bytes(row))
    return png_bytes(size, size, rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        path = OUT_DIR / f"icon-{size}.png"
        path.write_bytes(render(size))
        print(f"{path} ({path.stat().st_size} Bytes)")


if __name__ == "__main__":
    main()
