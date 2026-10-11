# UltimateTracker

Autarker Kinder-Tracker mit Zwei-Wege-Audio (Push-to-Talk), LTE-M/NB-IoT-Ortung
und vollständig selbst gehosteter Infrastruktur (Traccar + Audio-Bridge).

> **Status:** Hardware bestellt (LilyGO T-SIM7080G-S3 V1.0), Lieferung steht aus.
> Der Server-Stack (Docker) ist vorbereitet und lauffähig, die Firmware ist ein Skelett.

## Was ist das?

Ein kompakter, am Körper getragener Tracker für Kinder:

- **Ortung** per GNSS und LTE-M/NB-IoT (OsmAnd-Protokoll → Traccar)
- **Sprachnachrichten in beide Richtungen**: Kind drückt PTT, Eltern antworten über eine Web-Oberfläche
- **Akustischer Suchalarm** (Piezo) und Bewegungswake über einen Beschleunigungssensor
- **Kein Cloud-Anbieter**: alle Daten bleiben auf eigener Hardware (Docker)

## Struktur

| Pfad | Inhalt |
|---|---|
| `TODO.md` | **Konsolidierte offene Aufgaben** (Start hier, wenn es losgeht) |
| `project.md` | Projektübersicht: Hardware, Verdrahtung, Systemlogik (Hauptdokument) |
| `docs/pinout.md` | Verbindliche GPIO-Belegung (T-SIM7080G-S3 V1.0) |
| `docs/esp32s3.md` | ESP32-S3-Eigenheiten (Wake, Pull-ups, USB-CDC, PSRAM, Emulation) |
| `docs/hardware-review.md` | Prüfbericht: verifizierte Annahmen, Risiken, Quellen |
| `docs/architecture.md` | Systemarchitektur, Datenflüsse, Energiebudget |
| `docs/measurement-plan.md` | Mess- und Testplan für die Inbetriebnahme |
| `docs/optimizations.md` | Optimierungs-Backlog (Server & Firmware, priorisiert) |
| `docs/simulation.md` | Tests/Simulation ohne Hardware (Simulator, native Tests, QEMU) |
| `docs/deployment.md` | Server-Deployment (WSL, Docker, Thin Client) |
| `docs/findmy.md` | Apple/Google Find My: Gegenstücke, Setup, Grenzen (experimentell) |
| `docs/sms.md` | Identitäten (IMEI/MSISDN) und SMS-Pfad |
| `docs/decisions.md` | Entscheidungsprotokoll (ADR-Kurzform) |
| `firmware/` | ESP32-S3-Firmware (PlatformIO, Skelett) |
| `server/` | Docker-Stack: Traccar + Audio-Bridge |
| `scripts/` | WSL-Sync, Smoke-Test, Tracker-Simulator, Echo-Server, Backups |

## Schnellstart (Server)

```bash
cp server/.env.example server/.env    # Token setzen!
cd server && docker compose up -d
```

Ports: `8082` Traccar-Web, `5055` Traccar-OsmAnd, `8085` Audio-Bridge.
Details und WSL-Setup: [`docs/deployment.md`](docs/deployment.md).

## Lizenz

Noch nicht festgelegt (TODO vor der ersten Veröffentlichung).
