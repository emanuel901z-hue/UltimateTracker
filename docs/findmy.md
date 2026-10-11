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
| Docker-Gegenstück | `anisette` + `macless-haystack` | `google-findmy-webui` (empfohlen) bzw. `google-findmy` (minimal) |
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

## 3. Google: WebUI (empfohlen) oder Minimal-Microservice

Hintergrund: Das Google-Gegenstück basiert auf `GoogleFindMyTools` und existiert in
zwei Ausprägungen – **traccar/google-find-hub-sync** (Traccar-Organisation; Basis
der Minimal-Variante) und die **GoogleFindMyToolsWebUi** (P6g9YHK6), die den offenen
Fix für den Key-Rotations-Bug (leonboe1/GoogleFindMyTools#114) bereits enthält und
zusätzlich Web-UI, Scheduling und Firmware-Build mitbringt.

### 3a. WebUI – empfohlen (Profil `findmy`, Port 4321)

```bash
cd server
docker compose --profile findmy up -d google-findmy-webui
```

Dann <http://localhost:4321> → Config → „Sign in with Google“ (Chrome/Xvfb/noVNC
werden beim ersten Login im Container nachinstalliert; der Login läuft direkt im
Browser). Kernfunktionen:

- Geräteliste mit „Locate“/„Play sound“, **Poll-Schedule pro Gerät**
- Ziele mit Presets: **Traccar (OsmAnd)**, Nextcloud PhoneTrack, GpsLogger,
  OwnTracks, uLogger, Locus Map … plus generische HTTP-Ziele mit
  `{{latitude}}`-Platzhaltern → auch unser Bridge-Ingest ist als Ziel nutzbar
  (`POST http://audio-bridge:8085/api/v1/findmy/locations`)
- **ESP32-Tracker aus der UI registrieren** und Firmware im Browser bauen/flashen
  (Web Serial) – passt direkt zu den geplanten Beacon-„Mods“
- Logs + Apprise-Benachrichtigungen (ntfy, Telegram, E-Mail …), Rate-Limiting,
  `/metrics` (Prometheus)

Sicherheit (Empfehlungen des Projekts): Default ist HTTP ohne Auth → unbedingt
`WEBUI_USER`/`WEBUI_PASSWORD` setzen; optional `HTTPS_ENABLED=1` bzw. eigenes
Zertifikat; `SECRETS_ENCRYPTION_KEY` für Verschlüsselung der Tokens at rest.
Alle Daten liegen im Volume `google-findmy-data`.

### 3b. Minimal-Microservice (Profil `google-minimal`, Port 5500)

```bash
cd server
docker compose --profile google-minimal up -d google-findmy
```

Erst-Setup (Desktop mit Chrome, einmalig): `git clone
https://github.com/traccar/google-find-hub-sync`, `pip install -r requirements.txt`,
`python main.py` (Login + optional ESP32-Registrierung mit `r`), dann
`docker cp Auth/secrets.json ut-google-findmy:/app/Auth/secrets.json`.
Der Service pusht anschließend per `PUSH_URL` an die Bridge.

**Bekannter Bug:** Rotiert Google die E2EE-Owner-Keys des Kontos, schlägt die
Entschlüsselung fehl (Code fragt immer `owner_key_version=-1` an). Fix ist als
offener PR leonboe1/GoogleFindMyTools#114 vorhanden, aber nicht gemerged →
in diesem Fall auf 3a (WebUI) wechseln.

### 3c. Weitere Anbindungen (nicht in unserem Stack verbaut)

| Option | Ansatz | Wann sinnvoll |
|---|---|---|
| Traccar Relay (Android-App) | Offizielle App verbindet Find Hub mit Traccar | Wenn ein Handy dauerhaft online ist; braucht **Preview-Traccar** + `notificator.traccar.key` |
| Home-Assistant-Integration (BSkando/GoogleFindMy-HA) | Geräte/Standorte als HA-Entitäten | Wenn Home Assistant die Zentrale ist |
| MQTT-Fork (DominicWindisch) | Standorte → MQTT (Home-Assistant-Discovery) | Wenn MQTT im Haushalt läuft |
| go-findmy (dylanmazurek) | Go-Binary, FCM-Echtzeit, MQTT-Publisher | Schlanker eigener Service, Go-Stack |

*Hinweis:* Ein ioBroker-Adapter für Google Find Hub war nicht verifizierbar
(ioBroker-Adapter existieren für Apple-Geräte, z. B. `ioBroker.apple-find-me`).

**Google-Konto-Voraussetzung (alle Wege):** Auf einem Android-Gerät „Find My
Device“ mit „Mit Netzwerk in allen Bereichen“ aktivieren, sonst fehlen die
E2EE-Daten.

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
- Traccar-Fork (Minimal-Variante) – <https://github.com/traccar/google-find-hub-sync>
- GoogleFindMyToolsWebUi (empfohlen) – <https://github.com/P6g9YHK6/GoogleFindMyToolsWebUi>
- GoogleFindMyTools (Original) – <https://github.com/leonboe1/GoogleFindMyTools>
- Key-Rotations-Fix (offener PR) – <https://github.com/leonboe1/GoogleFindMyTools/pull/114>
- Traccar Relay (Android) – <https://www.traccar.org/relay/>
- MQTT-Fork – <https://github.com/DominicWindisch/googlefindmytools-homeassistant>
- go-findmy – <https://github.com/dylanmazurek/go-findmy>
