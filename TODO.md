# TODO – offene Aufgaben

Konsolidierte Liste aller offenen Punkte (Stand 2026-10-11), in empfohlener
Reihenfolge. Details jeweils in den verlinkten Dokumenten.

Legende: `[ ]` offen · `(i)` interaktiv – braucht dein Konto/Passwort

## A. Sofort möglich (ohne Hardware)

- [ ] **(i) Traccar-Admin-Passwort ändern** – Benutzer `admin@ultimatetracker.local`,
      aktuelles Passwort in `~/UltimateTracker/server/ADMIN-ZUGANG.txt` (WSL).
- [ ] Testdaten in Traccar löschen: Geräte `TEST123`/`TEST456`, Geofence „Testzone“
      (Web-UI <http://localhost:8082>).
- [ ] **(i) Google-Find-Hub-WebUI einrichten:** <http://localhost:4321> → Config →
      „Sign in with Google“. Zugangsdaten: `WEBUI_USER`/`WEBUI_PASSWORD` in `server/.env`.
      Danach ein Ziel anlegen (Traccar-OsmAnd-Preset **oder** Bridge-Ingest).
- [ ] **(i) Apple-Account bereitlegen** (2FA **per SMS** nötig). Empfehlung:
      Zweit-Account verwenden; Ban-Risiko beachten (1 Abfrage/30 min gilt als sicher).
- [ ] **(i) Apple-Bridge initialisieren** (Befehl in der Kurzreferenz unten).
- [ ] **(i) Beacon-Keypair erzeugen** (macless-haystack `generate_keys.py`), privaten
      Key in `server/.env` als `APPLE_BEACON_KEYS=…` eintragen.
- [ ] **(i) 1NCE-SIM aktivieren**, MSISDN aus dem Portal in der Geräte-Registry
      (Eltern-UI → Geräte) eintragen.
- [ ] **Lizenz entscheiden** (MIT / GPL-3.0 / CERN-OHL) und in `README.md` eintragen.
- [ ] Optional: Versionen pinnen (Traccar-Image, Google-WebUI-Image, Bridge-`GIT_REF`).
- [ ] Optional: `FINDMY_TOKEN` setzen und beim Google-Ziel als Header hinterlegen.

## B. Bei Hardwareankunft – zuerst messen

Messplan: [`docs/measurement-plan.md`](docs/measurement-plan.md),
Vorlage: [`docs/measurements/TEMPLATE.md`](docs/measurements/TEMPLATE.md).

- [ ] Board prüfen: Ist **IO2 am Header** verfügbar? (Fallback für I2C: IO10/IO11)
- [ ] **Board-Maße nachmessen** (CAD-Grundlage; Datenblatt: 111 × 32 × 20 mm)
- [ ] **Akku-Polung am JST-Stecker messen** – erst danach einstecken
- [ ] Antennen prüfen: LTE-FPC + **aktive** GNSS-Antenne vorhanden?
- [ ] **M1** Ruhestrom (Board, Modem aus/PSM, Mikrofon aus)
- [ ] **M2** I2S-Loopback (INMP441 → ADPCM → MAX98357A)
- [ ] **M3** GNSS/LTE-Umschaltung (Zeiten + Energie pro Zyklus)
- [ ] **M4** SMS-Test → entscheidet endgültig über den SMS-Pfad
- [ ] **M5** Laden (TS-Pin-Detection deaktivieren!), Akkustand über PMU
- [ ] **M6** Ende-zu-Ende-Audio (Tracker ↔ Bridge ↔ Browser)
- [ ] **M7** Antennen/Reichweite (GNSS im Gehäuse, LTE-Feldstärke)
- [ ] **M8** 48-h-Laufzeittest
- [ ] Messwerte danach in `project.md` (Abschnitt 5) und `docs/architecture.md` nachziehen

## C. Firmware (`firmware/`)

- [ ] LIS3DH: I2C-Init, Schwellwert-Interrupt, EXT1-Wake
- [ ] PMU AXP2101: TS-Pin-Detection aus, Akkustand lesen, Ladestrom setzen
- [ ] I2S-Pipeline (8 kHz/16 Bit/IMA-ADPCM) + LEDC-Piezo (gegenphasig)
- [ ] Mikrofon-Load-Switch (GPIO 10 bzw. PMU-Rail) einbinden
- [ ] TinyGSM: Modem-Init, `AT+SGPIO=0,5,1,1` (GNSS-Antenne), GNSS→LTE-Sequenz
- [ ] OsmAnd-Upload (IMEI als `id`, `batt`), Poll-Client (`/pending`, Suchmodus)
- [ ] Audio-Uplink (POST) + Downlink (Download, ADPCM-Decode, Amp-SD schalten)
- [ ] PTT: Entprellung, Quittungs-/Doppelton, 10-s-Limit
- [ ] Wake-Logik + Fehlerfälle (Positions-Ringpuffer, Upload-Retry)
- [ ] Toolchain prüfen: pioarduino/Arduino-Core 3.x für den neuen I2S-Treiber
- [ ] **(i) Flashen** testen (USB-C; BOOT+RST-Prozedur in `firmware/README.md`)

## D. Server-Stack (vor Produktivbetrieb Pflicht)

- [ ] **TLS/Reverse-Proxy** (Caddy-Skizze in `docs/deployment.md`) + Ports schließen
- [ ] **Eltern-Benachrichtigung** bei neuer Nachricht (ntfy/Telegram/Apprise/Web-Push)
- [x] Audio-Retention/Cleanup implementieren (Standard 30 Tage, `RETENTION_DAYS`) *(2026-10-11)*
- [ ] Traccar: Geofence + Benachrichtigungen einrichten
- [x] Backup-Skript für Volumes (`scripts/backup-volumes.sh`) *(2026-10-11)*
- [ ] macless-haystack absichern (`endpoint_user`/`endpoint_pass`), falls exponiert
- [ ] Umzug auf den Thin Client (`docs/deployment.md`, Abschnitt 7)

## E. Optional / experimentell

- [ ] Beacon-Stromversorgung entscheiden (Always-on-Chip vs. Wake-Zyklen)
- [ ] Google: Beacon in der WebUI registrieren + Firmware im Browser flashen
- [ ] Apple: echte AirTags anbinden (Key-Extraktion braucht macOS)
- [ ] SMS-Gateway evaluieren (nur falls M4 erfolgreich und Server-SMS gewünscht)
- [ ] Traccar Relay (Android) evaluieren (braucht Preview-Traccar + `notificator.traccar.key`)

## F. Optimierungen (Backlog – Details in [`docs/optimizations.md`](docs/optimizations.md))

**Paket 1 – sofort, ohne Hardware:**
- [x] A1 Healthchecks + Startreihenfolge im Compose *(2026-10-11)*
- [x] A2 Versionen pinnen (Traccar 6.16.0, WebUI-Digest, Bridge-Commit) *(2026-10-11)*
- [x] A4 Benachrichtigung bei neuer Nachricht (Apprise; `APPRISE_URLS` in `.env`) *(2026-10-11)*
- [x] A6 Bridge-Härtung: WAL, Upload-Limit, Fail-fast, Retention *(2026-10-11)*
- [x] A7 Backups (`scripts/backup-volumes.sh`) + Log-Rotation *(2026-10-11)*
- [x] A8 CI für Server **und** Firmware (`.github/workflows/ci.yml`) *(2026-10-11)*
- [x] A5 Sync-Endpunkt (Server) + A9 Status-Dashboard *(2026-10-11)*
- [ ] **(i) `APPRISE_URLS` mit echtem Ziel füllen** (ntfy/Telegram/Mail – Beispiel in `.env.example`)
- [ ] **(i) Backup-Cron einrichten** (Beispielzeile in `scripts/backup-volumes.sh`)

**Paket 2 – mit Hardware:** A5/C1 Sync-Endpunkt (ein Roundtrip pro Wake),
B2 Motion-Wake-Drossel, B5 Audio-AGC/Lautstärke, B8 Feldstabilität, A9 Status-Dashboard

**Paket 3 – vor Produktivbetrieb:** ~~A3 TLS/Reverse-Proxy~~ ✅ *(2026-10-11)*,
B6 NVS-Provisioning, B7 OTA über LTE, ~~A10 PostgreSQL statt H2~~ ✅ *(2026-10-11)*
- [x] Firmware-Logikmodule + 23 Host-Tests (`lib/tracker_core`, `pio test -e native`) *(2026-10-11)*
- [ ] **(i) TLS aktivieren:** `SITE_*` in `.env` setzen, `docker compose --profile tls up -d caddy`,
      Root-CA auf die Eltern-Handys importieren (`docs/deployment.md`, Abschnitt 6)

## G. Vor der Veröffentlichung

- [ ] `LICENSE` anlegen
- [ ] Secrets-Check der Historie (`git log -p | grep -iE "token|password"`)
- [ ] README finalisieren (Status, Screenshots)
- [ ] Optional: englische Übersetzung

---

## Kurzreferenz (Befehle)

```bash
# Repo → WSL spiegeln
wsl -d UltimateTracker -- bash -lc 'bash /mnt/d/Projekte/UltimateTracker/scripts/sync-to-wsl.sh'

# Stack starten (Standard / mit Find My)
wsl -d UltimateTracker -- bash -lc 'cd ~/UltimateTracker/server && docker compose up -d'
wsl -d UltimateTracker -- bash -lc 'cd ~/UltimateTracker/server && docker compose --profile findmy up -d'

# Apple-Bridge initialisieren (interaktiv, Apple-ID + SMS-2FA)
wsl -d UltimateTracker -- bash -lc 'cd ~/UltimateTracker/server && docker compose --profile findmy exec findmy-bridge .venv/bin/findmy-traccar-bridge-init'

# Smoke-Test / Logs
wsl -d UltimateTracker -- bash -lc 'bash ~/UltimateTracker/scripts/smoke-test.sh'
wsl -d UltimateTracker -- bash -lc 'cd ~/UltimateTracker/server && docker compose logs -f audio-bridge'

# Zugangsdaten ansehen (nicht committen!)
wsl -d UltimateTracker -- bash -lc 'grep -E "^(DEVICE|PARENT|WEBUI|GOOGLE|FINDMY|APPLE)" ~/UltimateTracker/server/.env'
```

## URLs der Dev-Instanz

| Dienst | URL | Zugang |
|---|---|---|
| Eltern-UI (Audio) | <http://localhost:8085> | `PARENT_TOKEN` aus `server/.env` |
| Traccar | <http://localhost:8082> | `~/UltimateTracker/server/ADMIN-ZUGANG.txt` |
| Google-Find-Hub-WebUI | <http://localhost:4321> | `WEBUI_USER`/`WEBUI_PASSWORD` |
| Apple-Endpunkt (macless-haystack) | <http://localhost:6176> | optional `endpoint_user`/`endpoint_pass` |
| Google-Microservice (minimal) | <http://localhost:5500> | `GOOGLE_FINDMY_TOKEN` |
