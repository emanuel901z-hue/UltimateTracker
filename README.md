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
| `project.md` | Projektübersicht: Hardware, Verdrahtung, Systemlogik (Hauptdokument) |
| `docs/pinout.md` | Verbindliche GPIO-Belegung (T-SIM7080G-S3 V1.0) |
| `docs/hardware-review.md` | Prüfbericht: verifizierte Annahmen, Risiken, Quellen |
| `docs/architecture.md` | Systemarchitektur, Datenflüsse, Energiebudget |
| `docs/measurement-plan.md` | Mess- und Testplan für die Inbetriebnahme |
| `docs/deployment.md` | Server-Deployment (WSL, Docker, Thin Client) |
| `docs/decisions.md` | Entscheidungsprotokoll (ADR-Kurzform) |
| `firmware/` | ESP32-S3-Firmware (PlatformIO, Skelett) |
| `server/` | Docker-Stack: Traccar + Audio-Bridge |
| `scripts/` | Hilfsskripte (Repo → WSL synchronisieren) |

## Schnellstart (Server)

```bash
cp server/.env.example server/.env    # Token setzen!
cd server && docker compose up -d
```

Ports: `8082` Traccar-Web, `5055` Traccar-OsmAnd, `8085` Audio-Bridge.
Details und WSL-Setup: [`docs/deployment.md`](docs/deployment.md).

## Lizenz

Noch nicht festgelegt (TODO vor der ersten Veröffentlichung).
