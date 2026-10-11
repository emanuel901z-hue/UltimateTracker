# AGENTS.md — Hinweise für Coding-Agents

## Projekt

Autarker Kinder-Tracker (ESP32-S3 + SIM7080G) mit selbst gehostetem Server
(Traccar + FastAPI-Audio-Bridge). Dokumentationssprache: **Deutsch**.

## Wichtige Regeln

- `docs/pinout.md` ist die **verbindliche** GPIO-Belegung. Änderungen dort zuerst
  eintragen, dann `firmware/include/pins.h` und `project.md` nachziehen.
- GPIOs **4, 5, 6, 7, 15, 35, 36, 37, 41, 42, 46** des T-SIM7080G-S3 V1.0 nicht
  verwenden (Modem-UART, PMU, PSRAM). GPIO 3 nur als Eingang (Modem-RI).
- Keine Secrets committen. Server-Konfiguration über `server/.env` (gitignored),
  Vorlage: `server/.env.example`.
- Beim SIM7080G sind **GNSS und LTE hardwarebedingt nicht gleichzeitig** nutzbar
  (sequenzielle Abläufe planen).
- **ESP32-S3-Eigenheiten beachten** (`docs/esp32s3.md`): Wake nur über RTC-GPIOs
  0–21; interne Pull-ups sind im Deep Sleep aus (Taster braucht den externen
  100-kΩ-Pull-up); im Release-Build **kein** `ARDUINO_USB_CDC_ON_BOOT=1` (Board
  startet sonst am Akku nicht); kein DAC → Audio nur über I2S.
- **Geräte-ID ist die IMEI** (Bridge-Registry, `docs/sms.md`); MSISDN nur für den
  optionalen SMS-Pfad mitführen.
- Find My (Apple/Google) ist **experimentell** und läuft im Compose-Profil `findmy`
  (`docs/findmy.md`) – nicht als stabilen Pfad voraussetzen.
- `firmware/lib/tracker_core` muss **C++11-kompatibel** bleiben (der Arduino-Build
  nutzt `gnu++11`); die Host-Tests laufen bewusst mit demselben Standard
  (`pio test -e native`), damit Abweichungen auffallen.
- Zahlen (Datenraten, Ströme) immer aus `docs/hardware-review.md` bzw.
  `docs/architecture.md` übernehmen, nicht neu schätzen.

## Befehle

- Server starten: `cd server && docker compose up -d`
- Server-Logs: `cd server && docker compose logs -f audio-bridge`
- Firmware bauen: `cd firmware && pio run` (PlatformIO)
- Repo in die WSL-Distro spiegeln (aus WSL heraus): `bash scripts/sync-to-wsl.sh`

## Struktur-Konventionen

- `project.md` = Überblick, `docs/*` = Details, `firmware/` + `server/` = Code.
- Neue Entscheidungen als Eintrag in `docs/decisions.md` ergänzen.
