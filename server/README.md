# Server-Stack (Docker Compose)

Zwei Dienste im selben Docker-Netz:

| Dienst | Port(s) | Aufgabe |
|---|---|---|
| `traccar` | 8082 (Web), 5055 (OsmAnd) | Positionen, Karte, Geofence, Akkustand |
| `audio-bridge` | 8085 (Web/API) | Sprachnachrichten beide Richtungen, Eltern-UI, Poll-Queue |

## Starten

```bash
cp .env.example .env     # Tokens setzen!
docker compose up -d
docker compose logs -f audio-bridge
```

- Eltern-UI: <http://localhost:8085> (Parent-Token eingeben)
- Traccar: <http://localhost:8082> – **ersten Benutzer registrieren** (wird automatisch
  Administrator; Traccar legt keinen Standard-Admin mehr an)
- Tracker-Uploads: `http://<host>:5055/?id=<IMEI>&lat=..&lon=..&batt=..&timestamp=..`

## Konfiguration

- `server/.env` – Tokens und Suchmodusdauer (gitignored; Vorlage `.env.example`).
- `server/traccar/traccar.xml` – Auto-Registrierung + Event-Weiterleitung an die Bridge.

## API (Kurzfassung)

| Methode | Pfad | Auth | Zweck |
|---|---|---|---|
| POST | `/api/v1/device/messages` | Device-Token | Audio-Uplink |
| GET | `/api/v1/device/pending` | Device-Token | Nachricht/Suchmodus abfragen |
| GET | `/api/v1/device/messages/{id}/audio` | Device-Token | Downlink-Datei |
| POST | `/api/v1/parent/messages` | Parent-Token | Sprachnachricht aufnehmen |
| GET | `/api/v1/parent/messages` | Parent-Token | Nachrichtenliste |
| POST | `/api/v1/parent/search-mode` | Parent-Token | Suchmodus setzen |
| GET/PUT/DELETE | `/api/v1/parent/devices[/{id}]` | Parent-Token | Geräte-Registry (IMEI/MSISDN) |
| POST | `/api/v1/findmy/locations` | optional Token | Find-My-Ingest (Apple/Google) |
| GET | `/api/v1/parent/findmy/locations` | Parent-Token | Find-My-Positionen |
| POST | `/api/v1/traccar/events` | optional Token | Webhook-Empfänger |
| GET | `/api/v1/parent/push/key` | Parent-Token | VAPID-Schlüssel für die PWA |
| POST/DELETE | `/api/v1/parent/push/subscribe` | Parent-Token | Push-Abo registrieren/entfernen |
| POST | `/api/v1/parent/push/test` | Parent-Token | Testbenachrichtigung senden |
| GET/POST/DELETE | `/api/v1/parent/firmware[/{version}]` | Parent-Token | Firmware verwalten (OTA) |
| GET | `/api/v1/device/firmware/latest?fw=` | Device-Token | OTA-Angebot |
| GET | `/api/v1/device/firmware/{version}/download` | Device-Token | Firmware-Binary |
| GET | `/api/v1/parent/sms/status` | Parent-Token | 1NCE-Konto: SIMs + SMS-Kontingent |
| POST | `/api/v1/parent/sms` | Parent-Token | MT-SMS an den Tracker (`{iccid, text}`) |
| GET | `/api/v1/parent/sms?iccid=` | Parent-Token | MT-/MO-SMS-Verlauf einer SIM |

Token-Header: `X-Auth-Token: <token>`.

**Push/PWA:** Die Eltern-UI ist als PWA installierbar und kann Web-Push
(„Auf diesem Gerät aktivieren“). Push benötigt eine **sichere Verbindung** –
HTTPS über das Caddy-Profil (`--profile tls`) oder `localhost`.
Zusätzlich zu Push können Apprise-Ziele (`APPRISE_URLS`) benachrichtigt werden.

## Compose-Profile

| Profil | Dienste | Zweck |
|---|---|---|
| (Standard) | `traccar`, `audio-bridge` | Ortung, Geofence, Sprachnachrichten, Eltern-UI |
| `findmy` | `anisette`, `findmy-bridge`, `macless-haystack`, `google-findmy-webui` | Find My: Apple (automatisch → Traccar) + Google-WebUI (Port **4321**) – **experimentell**, siehe `../docs/findmy.md` |
| `google-minimal` | `google-findmy` | Nur Google-Microservice (Port **5500**), ohne WebUI – Minimal-Alternative |

```bash
docker compose up -d                              # Standard
docker compose --profile findmy up -d             # + Apple/Google Find My (empfohlen)
docker compose --profile google-minimal up -d     # nur Google-Microservice (minimal)
```

## Daten

- `audio-data`-Volume → `/data` im Container: `bridge.sqlite3`, `audio/`, `events.jsonl`.
- `traccar-data`-Volume → Traccar-Datenbank.
- Backup: `docker run --rm -v ultimatetracker_audio-data:/data -v "$PWD":/backup alpine tar czf /backup/audio-data.tgz -C /data .`

## Sicherheit

- Tokens stark wählen (`openssl rand -hex 24`), Traccar-Admin mit sicherem Passwort anlegen.
- **Nicht** direkt ins Internet exponieren: Reverse-Proxy mit TLS davor (Caddy/Traefik),
  siehe `../docs/deployment.md` (Abschnitt „TLS“).
