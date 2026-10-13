"""Unit-Tests der Sensor-Fusion (ohne Netzwerk, docs/fusion.md).

Aufruf:  cd server/audio-bridge && python -m unittest discover -s tests -v
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.fusion import (  # noqa: E402
    choose_best,
    distance_meters,
    movement_state,
    parse_epoch,
    plausible_move,
    source_trust,
    source_valid_seconds,
)

NOW = 1_800_000_000.0


def iso(seconds_ago: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(NOW - seconds_ago, tz=timezone.utc).isoformat()


def candidate(source: str, seconds_ago: float, latitude: float = 48.1372,
              longitude: float = 11.5756, accuracy: float | None = None) -> dict:
    return {
        "source": source,
        "latitude": latitude,
        "longitude": longitude,
        "accuracy": accuracy,
        "received_at": iso(seconds_ago),
    }


class TestSourceProperties(unittest.TestCase):
    def test_trust_order(self):
        self.assertGreater(source_trust("tracker"), source_trust("apple"))
        self.assertGreater(source_trust("apple"), source_trust("network"))
        self.assertGreater(source_trust("network"), source_trust("unbekannt"))

    def test_validity_windows(self):
        self.assertEqual(source_valid_seconds("tracker"), 1800)
        self.assertEqual(source_valid_seconds("google"), 5400)
        self.assertEqual(source_valid_seconds("network"), 900)
        self.assertEqual(source_valid_seconds("unbekannt"), 900)

    def test_parse_epoch(self):
        self.assertIsNone(parse_epoch(None))
        self.assertIsNone(parse_epoch(""))
        self.assertIsNone(parse_epoch("keine zeit"))
        self.assertEqual(parse_epoch(1234), 1234.0)
        self.assertEqual(parse_epoch("1234"), 1234.0)
        self.assertAlmostEqual(parse_epoch("2026-10-13T09:00:00Z"), 1791882000.0, places=0)


class TestDistanceAndPlausibility(unittest.TestCase):
    def test_distance_known_value(self):
        # 0.01 Grad Breite entspricht rund 1113 m
        meters = distance_meters((48.0, 11.0), (48.01, 11.0))
        self.assertAlmostEqual(meters, 1113, delta=15)

    def test_small_move_is_plausible(self):
        previous = {"latitude": 48.1372, "longitude": 11.5756, "received_at": iso(600)}
        moved = candidate("tracker", 0, latitude=48.1375, longitude=11.5760)
        self.assertTrue(plausible_move(previous, moved))

    def test_impossible_jump_is_not_plausible(self):
        previous = {"latitude": 48.1372, "longitude": 11.5756, "received_at": iso(60)}
        jumped = candidate("tracker", 0, latitude=52.5200, longitude=13.4050)  # Berlin
        self.assertFalse(plausible_move(previous, jumped))

    def test_without_previous_always_plausible(self):
        self.assertTrue(plausible_move(None, candidate("tracker", 0)))


class TestMovementState(unittest.TestCase):
    def test_unknown_with_single_point(self):
        self.assertEqual(movement_state([candidate("tracker", 0)]), "unknown")

    def test_standing(self):
        positions = [candidate("tracker", 1800), candidate("tracker", 900), candidate("tracker", 0)]
        self.assertEqual(movement_state(positions, now=NOW), "standing")

    def test_moving(self):
        positions = [
            candidate("tracker", 1800, latitude=48.1372),
            candidate("tracker", 900, latitude=48.1400),
            candidate("tracker", 0, latitude=48.1430),
        ]
        self.assertEqual(movement_state(positions, now=NOW), "moving")


class TestChooseBest(unittest.TestCase):
    def test_fresh_tracker_beats_findmy(self):
        chosen = choose_best([candidate("tracker", 60), candidate("apple", 30)], now=NOW)
        self.assertEqual(chosen["source"], "tracker")
        self.assertFalse(chosen["stale"])
        self.assertEqual(chosen["reason"], "beste gültige Quelle")

    def test_stale_tracker_loses_to_fresh_findmy(self):
        # GNSS älter als 30 Minuten → nicht mehr gültig, Apple (90 min) gewinnt
        chosen = choose_best([candidate("tracker", 2000), candidate("apple", 120)], now=NOW)
        self.assertEqual(chosen["source"], "apple")
        self.assertFalse(chosen["stale"])

    def test_no_fresh_source_falls_back_to_last_known(self):
        chosen = choose_best([candidate("tracker", 7200), candidate("network", 3000)], now=NOW)
        self.assertTrue(chosen["stale"])
        self.assertEqual(chosen["source"], "tracker")  # höchste Vertrauensstufe
        self.assertIn("letzter bekannter Stand", chosen["reason"])

    def test_accuracy_breaks_tie_within_same_trust(self):
        chosen = choose_best([candidate("apple", 60, accuracy=90),
                              candidate("google", 60, accuracy=40)], now=NOW)
        self.assertEqual(chosen["source"], "google")

    def test_freshness_breaks_tie(self):
        chosen = choose_best([candidate("apple", 300), candidate("google", 60)], now=NOW)
        self.assertEqual(chosen["source"], "google")

    def test_suspect_jump_is_deprioritised(self):
        previous = {"latitude": 48.1372, "longitude": 11.5756, "received_at": iso(60)}
        jumped = candidate("tracker", 0, latitude=52.5200, longitude=13.4050)   # unplausibel
        plausible = candidate("apple", 60, latitude=48.1373, longitude=11.5757, accuracy=60)
        chosen = choose_best([jumped, plausible], previous=previous, now=NOW)
        self.assertEqual(chosen["source"], "apple")

    def test_suspect_is_marked_not_dropped(self):
        previous = {"latitude": 48.1372, "longitude": 11.5756, "received_at": iso(60)}
        jumped = candidate("tracker", 0, latitude=52.5200, longitude=13.4050)
        chosen = choose_best([jumped], previous=previous, now=NOW)
        self.assertTrue(chosen["suspect"])          # übernommen, aber markiert
        self.assertEqual(chosen["source"], "tracker")

    def test_empty_candidates(self):
        self.assertIsNone(choose_best([], now=NOW))

    def test_sources_list_is_included(self):
        chosen = choose_best([candidate("tracker", 60), candidate("apple", 30),
                              candidate("network", 5000)], now=NOW)
        sources = {item["source"]: item for item in chosen["sources"]}
        self.assertEqual(set(sources), {"tracker", "apple", "network"})
        self.assertFalse(sources["network"]["valid"])   # 5000 s > 900 s
        self.assertTrue(sources["tracker"]["valid"])

    def test_real_time_default(self):
        # ohne now-Parameter wird die echte Zeit genutzt
        chosen = choose_best([candidate("tracker", 10, received_at=None) if False else {
            "source": "tracker", "latitude": 48.1, "longitude": 11.5,
            "received_at": time.time(),
        }])
        self.assertEqual(chosen["source"], "tracker")
        self.assertTrue(chosen["valid"])


if __name__ == "__main__":
    unittest.main()
