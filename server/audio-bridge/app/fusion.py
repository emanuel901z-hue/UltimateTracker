"""Sensor-Fusion: mehrere Positionsquellen → eine belastbare Position je Kind.

Reine Logik ohne Netzwerk/Datenbank, damit sie auf dem Host testbar ist
(`python -m unittest discover -s tests`). Die Bridge (main.py) liefert die
Kandidaten und nutzt das Ergebnis.

Prinzip: **auswählen statt mitteln.** GNSS (3–10 m) mit Crowd-Netz-Positionen
(~50–100 m) zu mitteln würde die gute Quelle verschlechtern. Deshalb:
Vertrauensstufe → Frische → Genauigkeit. Zusätzlich:

* **Gültigkeitsfenster** je Quelle (alte Messungen verfallen),
* **Sprungfilter** (unplausible Bewegung wird markiert, nicht verworfen),
* **Zustandserkennung** (steht / bewegt) aus der jüngsten Spur.

Details und Begründungen: docs/fusion.md
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

SOURCE_TRUST = {"tracker": 100, "apple": 60, "google": 60, "network": 30}
SOURCE_VALID_S = {"tracker": 1800, "apple": 5400, "google": 5400, "network": 900}
DEFAULT_TRUST = 20
DEFAULT_VALID_S = 900
EARTH_RADIUS_M = 6371000.0
MAX_SPEED_KMH = 120.0          # schneller bewegt sich ein Kind nicht
MOVING_THRESHOLD_M = 80.0      # ab dieser Distanz gilt die Spur als „bewegt"
MOVING_WINDOW_S = 3600         # betrachtetes Zeitfenster für die Zustandserkennung


def source_trust(provider: str) -> int:
    return SOURCE_TRUST.get((provider or "").lower(), DEFAULT_TRUST)


def source_valid_seconds(provider: str) -> int:
    return SOURCE_VALID_S.get((provider or "").lower(), DEFAULT_VALID_S)


def parse_epoch(value) -> float | None:
    """ISO-Zeitstempel oder Unix-Zeit → Sekunden (None bei Unlesbarem)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        cleaned = text.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).timestamp()
    except ValueError:
        return None


def distance_meters(first: tuple[float, float], second: tuple[float, float]) -> float:
    """Entfernung zweier Koordinaten (Haversine)."""
    lat1, lon1 = math.radians(first[0]), math.radians(first[1])
    lat2, lon2 = math.radians(second[0]), math.radians(second[1])
    delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
    inner = (math.sin(delta_lat / 2) ** 2
             + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(inner)))


def plausible_move(previous: dict | None, candidate: dict, max_speed_kmh: float = MAX_SPEED_KMH) -> bool:
    """Ist die Bewegung von `previous` zu `candidate` physikalisch plausibel?

    Unplausible Sprünge entstehen durch fehlerhafte Fixes (typisch bei GNSS im
    Funkloch) oder durch Zeitsprünge. Sie werden **markiert**, nicht verworfen –
    eine echte Positionsänderung darf nie verloren gehen.
    """
    if previous is None:
        return True
    first = (previous.get("latitude"), previous.get("longitude"))
    second = (candidate.get("latitude"), candidate.get("longitude"))
    if None in first or None in second:
        return True
    previous_epoch = parse_epoch(previous.get("received_at"))
    candidate_epoch = parse_epoch(candidate.get("received_at"))
    if previous_epoch is None or candidate_epoch is None:
        return True
    seconds = abs(candidate_epoch - previous_epoch)
    if seconds < 1:
        return True  # gleiche Messung/Zeitstempel
    allowed = max_speed_kmh / 3.6 * seconds
    return distance_meters(first, second) <= allowed


def movement_state(positions: list[dict], now: float | None = None) -> str:
    """'moving' | 'standing' | 'unknown' aus den jüngsten Positionen."""
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    recent = []
    for position in positions:
        epoch = parse_epoch(position.get("received_at"))
        if epoch is not None and 0 <= now - epoch <= MOVING_WINDOW_S:
            recent.append((epoch, position))
    if len(recent) < 2:
        return "unknown"
    recent.sort(key=lambda item: item[0])
    span = 0.0
    for (first_epoch, first), (second_epoch, second) in zip(recent, recent[1:]):
        if second_epoch - first_epoch > 0:
            span += distance_meters(
                (first.get("latitude"), first.get("longitude")),
                (second.get("latitude"), second.get("longitude")),
            )
    return "moving" if span >= MOVING_THRESHOLD_M else "standing"


def choose_best(candidates: list[dict], previous: dict | None = None,
                now: float | None = None) -> dict | None:
    """Beste verfügbare Position bestimmen.

    `candidates`: Liste mit source, latitude, longitude, accuracy?, received_at.
    `previous`: zuletzt übernommene Position (für den Sprungfilter).

    Rückgabe: gewählte Position + trust/age_s/valid/reason/stale/suspect und die
    Liste aller Quellen (zur Kontrolle in der UI).
    """
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    if not candidates:
        return None

    enriched = []
    for candidate in candidates:
        source = (candidate.get("source") or "").lower()
        epoch = parse_epoch(candidate.get("received_at"))
        age = None if epoch is None else max(0, int(now - epoch))
        valid = age is not None and age <= source_valid_seconds(source)
        enriched.append({
            **candidate,
            "source": source,
            "trust": source_trust(source),
            "age_s": age,
            "valid": valid,
            "suspect": not plausible_move(previous, candidate),
        })

    usable = [item for item in enriched if item["valid"]]
    if usable:
        # Unplausible Sprünge zuletzt, sonst: Vertrauen → Frische → Genauigkeit
        chosen = sorted(usable, key=lambda item: (
            item["suspect"],
            -item["trust"],
            item["age_s"] if item["age_s"] is not None else 10 ** 9,
            item["accuracy"] if item.get("accuracy") is not None else 10 ** 6,
        ))[0]
        chosen = {**chosen, "reason": "beste gültige Quelle", "stale": False}
    else:
        chosen = {**sorted(enriched, key=lambda item: item["trust"], reverse=True)[0],
                  "reason": "keine frische Quelle – letzter bekannter Stand", "stale": True}

    return {
        **chosen,
        "sources": [
            # .get(), damit Quellen ohne Genauigkeit/Angabe nicht zum Fehler führen
            {key: item.get(key) for key in ("source", "age_s", "accuracy", "valid", "trust", "suspect")}
            for item in sorted(enriched, key=lambda entry: -entry["trust"])
        ],
    }
