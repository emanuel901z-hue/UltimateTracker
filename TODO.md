# TODO – offene Aufgaben

Konsolidierte Liste aller offenen Punkte (Stand **2026-10-13**), in empfohlener
Reihenfolge. Details jeweils in den verlinkten Dokumenten.

> **Seit dem letzten Stand erledigt:** Repo ist **öffentlich** und die CI ist grün
> (26 Smoke-Gruppen, 59 Bridge-Tests, UI-Screenshots); Setup-Assistent mit 9
> Schritten; **ein Login für alle Dienste** (SSO + Traccar-Auto-Login per Ticket);
> eigene Karte ohne zweite Anmeldung; **Sensor-Fusion** (Beacon-Zuordnung,
> Sprungfilter, Zustand); Zertifikat-Download über die UI; **Apple-Einrichtung im
> Assistenten**; Nachrichten-Chat mit „gehört"-Status; SMS-Verlauf; Traccar zeigt
> ein Gerät je Kind; **Eltern-Tauglichkeit** (`docs/parent-usability.md`):
> Assistent **pro Kind** + „Weiteres Kind hinzufügen", Geräte **bearbeiten/
> löschen** (Kaskade, Phantom-Erkennung, IMEI-Prüfziffer), Klartextfehler mit
> **Auto-Login bei abgelaufener Sitzung**, **Gesundheitsampel** je Kind,
> Einstellungen in Elternsprache, **Firmware-UI**.

Legende: `[ ]` offen · `[x]` erledigt · `(i)` interaktiv – braucht dein Konto/Passwort

## A. Sofort möglich (ohne Hardware)

- [x] **Lizenz entschieden: MIT** (`LICENSE`), README-Abschnitt ergänzt *(2026-10-12)*
- [x] **Traccar-Admin wieder zugänglich** (Passwort neu gesetzt, `ADMIN-ZUGANG.txt`) *(2026-10-12)*
- [ ] **(i) Traccar-Passwort in der UI ändern** (Einstellungen → Konto) – das in
      `~/UltimateTracker/server/ADMIN-ZUGANG.txt` steht nur lokal.
- [ ] **(i) Eltern-UI-Passwort ändern** (UI → „Passwort ändern"); Startwert aus `PARENT_PASSWORD`.
- [ ] **(i) LAN-Zugriff einrichten** (Handy → Host): `scripts\windows-lan-forward.ps1`
      als Administrator, danach `http://<host-ip>:8085` testen (`docs/deployment.md`, 8.3).
- [x] **Repo veröffentlicht** (öffentlich, MIT, Beschreibung + Topics gesetzt, CI grün) *(2026-10-13)*
- [x] Testdaten in Traccar aufgeräumt: Beacon-Relikte gelöscht, es bleibt **ein**
      Gerät je Kind (`TEST123`) *(2026-10-13)*
- [x] Google-Find-Hub-WebUI erreichbar (**ohne** zweite Anmeldung: `https://findmy.localhost`,
      hinter dem SSO) *(2026-10-13)*; offen bleibt **(i) „Sign in with Google“** und ein Ziel
      (Traccar-Preset **oder** Bridge-Ingest)
- [ ] **(i) Apple-Account bereitlegen** (2FA **per SMS** nötig). Empfehlung:
      Zweit-Account verwenden (keine Testkonten verfügbar, siehe `docs/findmy.md` 4b);
      Ban-Risiko beachten (1 Abfrage/30 min gilt als sicher).
- [x] Apple-Einrichtung läuft über den **Setup-Assistenten** (Schritt „Apple Find My“)
      statt interaktiv im Container *(2026-10-13)* – offen: echte Apple-ID eintragen
- [ ] **(i) Beacon-Keypair erzeugen** (macless-haystack `generate_keys.py`), privaten
      Key in `server/.env` als `APPLE_BEACON_KEYS=…` eintragen.
- [ ] **(i) 1NCE-SIM aktivieren**, ICCID + MSISDN aus dem Portal in der Geräte-Registry
      (Eltern-UI → Geräte) eintragen – danach `sms/status` und MT-Versand testen.
- [ ] Optional: `FINDMY_TOKEN` setzen und beim Google-Ziel als Header hinterlegen.
- [x] Traccar per Einmal-Ticket automatisch angemeldet; Find-My-WebUIs hinter dem SSO
      (Traccar bewusst **nicht** hinter `forward_auth`, siehe `docs/decisions.md` D-013) *(2026-10-13)*

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

- [x] ESP32-S3-Eigenheiten geprüft + dokumentiert (`docs/esp32s3.md`) *(2026-10-11)*
      → Release-Env ohne USB-CDC (startet sonst am Akku nicht), externer PTT-Pull-up
      zwingend, Ring-Log in RTC-Speicher, QEMU-Erwartungen korrigiert
- [x] Modem-Abstraktion + Mock + **kompletter Wake-Zyklus** host-testbar *(2026-10-11)*
- [x] NVS-Provisioning (JSON-Kommando per USB-Serial) *(2026-10-11)*
- [x] OTA: Server-Endpunkte, Angebot im Sync, Prüflogik *(2026-10-11)*
      → offen: Flash-Schreiben (`Update`/esp_ota) mit Hardware
- [x] GNSS-Auswertung `AT+CGNSINF` + UTC→Epoch *(2026-10-11)*
- [x] Feldstabilität: Ring-Log (RTC), Reset-Zähler, monotone Uptime über Sleeps *(2026-10-11)*
- [x] **Bring-up-Firmware** (`tsim7080g-s3-bringup`): Selbsttest I2C/PMU/LIS3DH/Modem/GNSS/I2S/Piezo/Taster/WLAN/BLE + Kommando-Konsole *(2026-10-11)*
- [x] **Erster Selbsttest am echten Board** (2026-10-12): N16R8 bestätigt, PMU @0x34 ✓,
      WLAN/BLE ✓, Modem-AT ✓ (ohne SIM), Werks-Image gesichert – Ergebnisse in `docs/bring-up.md`
- [ ] **(i) Peripherie auf Breadboard verdrahten** (LIS3DH, INMP441, MAX98357A, Taster, Piezo) → Selbsttest erneut
- [ ] **(i) GNSS mit Sichtverbindung testen** (indoor kein Fix – erwartet)
- [ ] **(i) SIM einlegen** und Modem-Teil wiederholen (CCID/CEREG/CSQ, **PSM/eDRX-Kommandos**, M4-SMS)
- [ ] **(i) HTTP-Engine des Modems implementieren** (`AT+SHCONF/SHBOD/SHREQ/SHREAD`) – Hardware-Phase M6
- [ ] **(i) PWRKEY/Power-Zyklus + Rail-Handling messen** (B1, M1/M3)
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

- [x] **TLS/Reverse-Proxy** (Caddy-Profil `tls`, Site-Fallback, `default_sni`) *(2026-10-12)*
- [x] **Eltern-Benachrichtigung** bei neuer Nachricht (Apprise + Web-Push/PWA) *(2026-10-11)*
- [x] Audio-Retention/Cleanup implementieren (Standard 30 Tage, `RETENTION_DAYS`) *(2026-10-11)*
- [x] **Login + Benutzerverwaltung** (PBKDF2, Sitzungen, Passwortwechsel/-Reset) *(2026-10-12)*
- [x] **Mehrkind-Betrieb** (Kinder-Übersicht, Suchmodus pro Kind) *(2026-10-12)*
- [x] **Operationszentrale**: Monitoring, Laufzeit-Einstellungen, Backup-Download *(2026-10-12)*
- [x] **SIM-Provider-Schicht** (1NCE, WhereverSIM, Vorlagen für EMnify/Onomondo/Twilio) *(2026-10-12)*
- [ ] Traccar: Geofence + Benachrichtigungen einrichten
- [x] Backup-Skript für Volumes (`scripts/backup-volumes.sh`) *(2026-10-11)*
- [ ] macless-haystack absichern (`endpoint_user`/`endpoint_pass`), falls exponiert
- [ ] Umzug auf den Thin Client (`docs/deployment.md`, Abschnitt 7)
- [ ] Optional: Rate-Limits (Caddy-Plugin/fail2ban), Traccar hinter den Bridge-Login
- [ ] Benachrichtigungen jenseits von Web-Push **in der UI** einrichtbar machen
      (Apprise-Feld statt nur `APPRISE_URLS`; `docs/parent-usability.md` F2)
- [ ] Karte: Offline-/Kachel-Hinweis, wenn kein Internet erreichbar ist (H2)
- [ ] Backup für Eltern rahmen (Wiederherstellen/„wohin damit"); Anleitung statt tar.gz (H3)

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
- [x] **Web-Push + PWA** (Service Worker, VAPID, Abo in der UI) *(2026-10-11)*
- [x] Hardware-Phase vorbereitet: `docs/bring-up.md` + `scripts/new-measurement-session.sh` *(2026-10-11)*
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

- [x] `LICENSE` anlegen (**MIT**, Copyright 2026 Manu) *(2026-10-12)*
- [x] Secrets-Check der getrackten Dateien **und** der Historie (Audit in
      `docs/deployment.md`, Abschnitt 10) – sauber *(2026-10-12)*
- [x] README finalisiert (Status, Aufbau, Schnellstart, Datenschutz, Lizenz) *(2026-10-12)*
- [x] `SECURITY.md` (Meldeweg + Betriebs-Checkliste) *(2026-10-12)*
- [x] Pre-Commit-Hook gegen versehentliche Secrets (`scripts/git-hooks/pre-commit`) *(2026-10-12)*
- [ ] Optional: englische Übersetzung
- [ ] Optional: Screenshots/Statusbadges, sobald das Repo öffentlich ist

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
| Eltern-UI (Audio) | <http://localhost:8085> | Login (`PARENT_USER`/`PARENT_PASSWORD`) |
| Traccar | <http://localhost:8082> | `~/UltimateTracker/server/ADMIN-ZUGANG.txt` |
| Google-Find-Hub-WebUI | <https://findmy.localhost> | hinter dem SSO, keine eigene Anmeldung |
| Apple-Endpunkt (macless-haystack) | <http://localhost:6176> | optional `endpoint_user`/`endpoint_pass` |
| Google-Microservice (minimal) | <http://localhost:5500> | `GOOGLE_FINDMY_TOKEN` |
