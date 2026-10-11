# Find My (Apple & Google) – optionale Ortung über Fremdnetze

Ziel: Ein BLE-Beacon (Tracker-Mod, zusätzlicher ESP32 oder separater Chip) wird
von fremden Smartphones empfangen; die Standorte kommen über Apples bzw. Googles
Netz zurück. Dieses Dokument beschreibt die **Gegenstücke im Docker-Stack**, die
Initialisierung (Keys/Geräteregistrierung) und die Auswertung – plus die Grenzen.

> **Status: EXPERIMENTELL.** Beide Wege nutzen reverse-engineerte Protokolle ohne
> offizielle Unterstützung. Apple filtert seit 2025 geklonte AirTag-Advertisements
> (OpenHaystack-Issue #273); der Google-Weg ist eine Community-Reimplementierung.
> Beides kann jederzeit brechen.

## 1. Voraussetzungen & Grenzen

| Punkt | Apple (Find My) | Google (Find Hub) |
|---|---|---|
| Offiziell für DIY? | nein (OpenHaystack) | nein (Community-Tools) |
| Konto nötig | Apple-ID mit 2FA (**nur SMS-2FA**) | Google-Konto + Chrome (Desktop) |
| Docker-Gegenstück | `anisette` + `macless-haystack` | `google-findmy` (Microservice) |
| Erst-Setup | interaktiv (Apple-ID-Login im Container) | interaktiv (Chrome-Login auf Desktop) |
| Zuverlässigkeit | wackelig (Apple-Filter) | experimentell |
| Abdeckung | sehr hoch (iPhone-Dichte) | hoch (Android-Dichte) |

**Strombedarf:** Ein Beacon muss dauerhaft senden. Der ESP32-S3 kann im Deep Sleep
**nicht** advertisen → entweder Wake-Zyklen (1–3 mA Durchschnitt) oder ein
separater Always-on-Chip (z. B. ST17H66, µA-Bereich). Siehe `docs/decisions.md` D-009.

## 2. Apple: macless-haystack + Anisette

```bash
cd server
docker compose --profile findmy up -d anisette macless-haystack
```

Erst-Registrierung (einmalig, interaktiv):

```bash
docker compose stop macless-haystack
docker compose run --rm macless-haystack   # fragt Apple-ID, Passwort, SMS-2FA
# Erfolg: "serving at port 6176 over HTTP"
docker compose up -d macless-haystack
```

Hinweise aus dem Projekt-FAQ: neue Apple-IDs brauchen ggf. Zahlungsmethode/Daten
(„account score“); zu viele Geräte im Account stören den Login; `auth.json` liegt
im Volume `macless-data` und kann gesichert/ausgetauscht werden.

Keys + Firmware:

1. `generate_keys.py` aus den macless-haystack-Releases laden.
2. Keypair erzeugen → liefert `*_devices.json` (fürs Frontend) und die
   Base64-Advertising-Keys für die Firmware.
3. ESP32-Firmware aus dem Repo mit dem Key flashen (oder OpenHaystack-kompatible
   Firmware, z. B. für ST17H66-Clones).

Auswertung: Web-Frontend <https://dchristl.github.io/macless-haystack/>
(Endpunkt `http://<host>:6176` eintragen, `*_devices.json` importieren).
Den Endpunkt vor dem Exponieren per `config.ini` (`endpoint_user`/`endpoint_pass`)
absichern.

## 3. Google: google-findmy-Microservice

```bash
cd server
docker compose --profile findmy up -d google-findmy
```

Erst-Setup auf dem Desktop mit Chrome (einmalig):

1. `git clone https://github.com/rolsch/google-find-hub-sync` (oder ZIP).
2. `pip install -r requirements.txt`, dann `python main.py` → Chrome-Login;
   Ergebnis: `Auth/secrets.json`.
3. Datei ins Volume kopieren:
   `docker cp Auth/secrets.json ut-google-findmy:/app/Auth/secrets.json`
4. Optional im Tool: eigenen ESP32-Tracker registrieren (`r` drücken) und die
   Firmware aus `ESP32Firmware/` flashen.
5. Google-Anforderung: Auf einem Android-Gerät „Find My Device“ aktivieren
   („Mit Netzwerk in allen Bereichen“), sonst fehlen die E2EE-Daten.

Der Microservice läuft auf Port 5500 (Bearer-Token = `GOOGLE_FINDMY_TOKEN`) und
pusht Standorte an `PUSH_URL` → `http://audio-bridge:8085/api/v1/findmy/locations`.

## 4. Ingest & Auswertung in der Bridge

- `POST /api/v1/findmy/locations` – **toleranter** Ingest (Einzelobjekt oder Liste).
  Erkannt werden u. a. `lat/latitude`, `lon/lng/longitude`, `accuracy/acc`,
  `timestamp/time/reported_at`, `id/beacon_id/device_id`, `provider/source`.
  Unbekannte Formate werden inkl. Roh-JSON gespeichert (nichts geht verloren).
- Optional Token: `FINDMY_TOKEN` als Header `X-Auth-Token` (leer = offen; dann
  den Port nicht nach außen exponieren).
- Mit gesetztem `TRACCAR_FORWARD_URL` geht jede Position zusätzlich als
  OsmAnd-Position an Traccar → Beacon erscheint als **eigenes Gerät** auf der Karte.
  **ID-Bereinigung:** Traccar akzeptiert in Geräte-IDs keine Bindestriche (HTTP 400);
  beim Forwarding wird die Beacon-ID deshalb auf `A–Z a–z 0–9 . _` reduziert
  (`BEACON-TEST-1` → `BEACONTEST1`). Die Original-ID bleibt in der Bridge erhalten.
- Eltern-UI zeigt die letzten Positionen; API: `GET /api/v1/parent/findmy/locations`.

Test:

```bash
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"provider":"apple","beacon_id":"BEACON-1","lat":48.1372,"lon":11.5756,"timestamp":1770000000}' \
  http://localhost:8085/api/v1/findmy/locations
```

## 5. Noch nicht implementiert

- Automatischer Abruf der Apple-Berichte aus macless-haystack (API nicht
  dokumentiert) – derzeit manuell/per Skript einspeisen.
- Beacon-Verwaltung in der UI (Keys, Provider-Zuordnung) – aktuell über die
  jeweiligen Fremd-Tools.

## 6. Rechtliches

Beacons in Fremdnetzen sind für Dritte als „unbekannter Tracker“ sichtbar
(Anti-Stalking-Warnungen). Für das eigene Kind vertretbar, aber bewusst
entscheiden. Keine offiziellen APIs → Nutzung auf eigenes Risiko.

## 7. Quellen

- macless-haystack – <https://github.com/dchristl/macless-haystack>
- OpenHaystack – <https://github.com/seemoo-lab/openhaystack>
- Apple-Filterproblem – <https://github.com/seemoo-lab/openhaystack/issues/273>
- google-find-hub-sync (Microservice) – <https://github.com/rolsch/google-find-hub-sync>
- GoogleFindMyTools (Original) – <https://github.com/leonboe1/GoogleFindMyTools>
