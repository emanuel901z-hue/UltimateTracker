# UltimateTracker

Autarker Kinder-Tracker mit **Zwei-Wege-Audio** (Push-to-Talk), LTE-M/NB-IoT-Ortung
und **vollständig selbst gehosteter** Infrastruktur – kein Cloud-Anbieter, keine
Abos, alle Daten auf eigener Hardware.

> **Status (Okt 2026):** Board ist da (LilyGO T-SIM7080G-S3 V1.0), Selbsttest
> gelaufen, Server-Stack läuft. Firmware: Logik vollständig und host-getestet
> (53 Tests), Hardware-Anbindung (Modem-HTTP, I2S, PMU) folgt in der
> Inbetriebnahme – siehe [`docs/bring-up.md`](docs/bring-up.md).

## Was ist das?

Ein kompakter, am Körper getragener Tracker für Kinder:

- **Ortung** per GNSS und LTE-M/NB-IoT (OsmAnd-Protokoll → Traccar)
- **Sprachnachrichten in beide Richtungen**: Kind drückt PTT, Eltern antworten
  über eine Web-Oberfläche (auch als PWA aufs Handy installierbar)
- **Suchalarm** (Piezo) und **Bewegungs-Wake** über einen Beschleunigungssensor
- **Operationszentrale** für die Eltern: Karte (Traccar eingebettet), Kinder-Übersicht,
  Nachrichten, Geräteverwaltung, Benutzerkonten mit Login, SIM-/SMS-Verwaltung,
  Firmware-Updates, Monitoring, Einstellungen und Backup an einer Stelle
- **Optional**: Apple-/Google-Find-My-Anbindung als Zusatzortung (experimentell)

## Aufbau

```
 Kind trägt                 Server (Docker, selbst gehostet)            Eltern
┌──────────────┐        ┌──────────────────────────────────────┐    ┌──────────┐
│ T-SIM7080G-S3│  LTE-M │ Traccar   ── Karte/Geofence/Verlauf  │    │ Browser  │
│  GNSS · PTT  │ ─────► │ Audio-Bridge ── Nachrichten, Geräte, │ ─► │ (Handy,  │
│  Audio · IMU │  HTTP  │   Benutzer, SMS, OTA, Monitoring     │    │  PWA)    │
└──────────────┘        │ PostgreSQL · Caddy (TLS) · optional  │    └──────────┘
                        │ Find-My-Gegenstücke                  │
                        └──────────────────────────────────────┘
```

## Struktur

| Pfad | Inhalt |
|---|---|
| `TODO.md` | **Konsolidierte offene Aufgaben** (Start hier, wenn es losgeht) |
| `project.md` | Projektübersicht: Hardware, Verdrahtung, Systemlogik (Hauptdokument) |
| `docs/pinout.md` | Verbindliche GPIO-Belegung (T-SIM7080G-S3 V1.0) |
| `docs/esp32s3.md` | ESP32-S3-Eigenheiten (Wake, Pull-ups, USB-CDC, PSRAM, Emulation) |
| `docs/hardware-review.md` | Prüfbericht: verifizierte Annahmen, Risiken, Quellen |
| `docs/architecture.md` | Systemarchitektur, Datenflüsse, API, Energiebudget |
| `docs/bring-up.md` | Erste Schritte mit der Hardware (Tag 1, Selbsttest, Messungen) |
| `docs/measurement-plan.md` | Mess- und Testplan M1–M8 für die Inbetriebnahme |
| `docs/deployment.md` | Deployment: WSL, Docker, TLS, LAN/Internet, Betrieb, Troubleshooting |
| `docs/optimizations.md` | Optimierungs-Backlog (Server & Firmware, priorisiert, mit Status) |
| `docs/simulation.md` | Tests ohne Hardware (Tracker-Simulator, Host-Tests, QEMU-Grenzen) |
| `docs/sim-providers.md` | Anbieterneutrale SIM-/SMS-Schicht + Vorlagen für andere MVNOs |
| `docs/sms.md` | Identitäten (IMEI/MSISDN/ICCID) und SMS-Pfad (1NCE: A2P) |
| `docs/findmy.md` | Apple/Google Find My: Gegenstücke, Setup, Grenzen (experimentell) |
| `docs/decisions.md` | Entscheidungsprotokoll (ADR-Kurzform) |
| `firmware/` | ESP32-S3-Firmware: `lib/tracker_core` (host-getestete Logik) + `src/` (Hardware-Glue) |
| `server/` | Docker-Stack: Traccar + Audio-Bridge (Eltern-UI/API), Caddy, Provider-Vorlagen |
| `scripts/` | WSL-Sync, Smoke-Test, Simulator, Backups, Mess-Session, Git-Hook |

## Schnellstart (Server)

```bash
cd server
cp .env.example .env
# Tokens + Login setzen:  openssl rand -hex 24   → DEVICE_TOKEN, PARENT_TOKEN
#                         PARENT_USER/PARENT_PASSWORD für die Eltern-UI
docker compose up -d
```

| Dienst | URL | Hinweis |
|---|---|---|
| Eltern-UI/API (**Einstiegspunkt**) | <http://localhost:8085> | Login (Benutzer/Passwort) |
| Traccar (Karte) | <http://localhost:8082> | ersten Benutzer registrieren → wird Admin |
| Tracker-Uploads | `http://<host>:5055/?id=<IMEI>&lat=…&lon=…&batt=…` | OsmAnd-Protokoll |

Details (WSL-Setup, TLS, LAN-/Internet-Betrieb, Betrieb & Wartung):
[`docs/deployment.md`](docs/deployment.md). Tests: `bash scripts/smoke-test.sh`
(19 Gruppen), `pio test -e native` (53 Host-Tests der Firmware-Logik),
`python scripts/check-ui-a11y.py` (Quelltext: Labels, ARIA, Tab-Muster,
Kontraste hell/dunkel, Bedienziele) und `python scripts/ui-check.py`
(**headless Chrome**: rendert alle Tabs in Desktop- und Mobilansicht, legt
Screenshots ab und prüft den Accessibility-Baum – kein Eingabefeld ohne
zugänglichen Namen). Orientierung: **WCAG 2.2 AA**; beide UI-Prüfungen laufen
in der CI.

## Datenschutz & Sicherheit

Dieses Projekt verarbeitet **Standortdaten und Sprachaufnahmen von Kindern**.
Es ist ausdrücklich dafür gebaut, dass diese Daten **das eigene Netz nicht
verlassen** – trotzdem gilt:

- **Selbst gehostet:** Alle Daten liegen auf deiner Hardware (Docker-Volumes).
  Es gibt keinen Cloud-Dienst, kein Konto bei einem Anbieter, keine Telemetrie.
- **TLS ist Pflicht**, sobald der Server von außen erreichbar ist
  (`--profile tls`, Caddy holt Let's Encrypt-Zertifikate). Ohne TLS läuft der
  Login im Klartext.
- **Nur die nötigen Ports öffnen** (80/443). Datenbank, Traccar-API und
  Find-My-Dienste bleiben im internen Docker-Netz.
- **Aufbewahrung:** Audionachrichten werden standardmäßig nach 30 Tagen
  gelöscht (`RETENTION_DAYS`, in der UI einstellbar).
- **Zugänge:** Benutzerkonten mit PBKDF2-Hashes, Sitzungstoken mit Ablauf,
  Passwortregeln; der erste Administrator kommt aus `server/.env`.
- **Secrets:** `.env` und Zugangsdateien sind per `.gitignore` und
  Pre-Commit-Hook (`scripts/git-hooks/pre-commit`) vom Repo ausgeschlossen.
- **Kein Medizin- oder Sicherheitsprodukt:** Der Tracker ist ein
  Freizeit-/Bastelprojekt. Er ersetzt keine Aufsicht und ist nicht für
  Notfälle zertifiziert. Funklöcher, Akku-Ende und Ausfälle sind möglich.
- **Weitergabe:** Wenn du Audiodaten oder Standorte mit Dritten teilst
  (z. B. Find-My-Netzwerke von Apple/Google), verlassen diese Daten dein Netz.
  Diese Integrationen sind **optional** und standardmäßig aus.

## Lizenz

MIT – siehe [`LICENSE`](LICENSE). Hardware-nahe Teile (Pinbelegung, Schaltungs-
und Gehäuseplanung) sind davon mit abgedeckt; für eine formale
Hardware-Lizenzierung (z. B. CERN-OHL-S) wäre eine Ergänzung möglich.
