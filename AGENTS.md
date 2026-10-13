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
- **Schichten trennen:** neue Ablauflogik gehört nach `firmware/lib/tracker_core`
  (ohne Arduino-Header, host-testbar, ggf. über `IModem`-Mock); nur echte
  Hardware-Anbindung (Serial, NVS, Sleep, `Update`) nach `firmware/src`.
- Zahlen (Datenraten, Ströme) immer aus `docs/hardware-review.md` bzw.
  `docs/architecture.md` übernehmen, nicht neu schätzen.
- **Server-Schichten:** SIM-/SMS-Anbieter nur über `app/providers/` anbinden
  (`SimProvider`-Schnittstelle; neue Anbieter möglichst als JSON-Konfiguration
  nach `server/sim-providers/`, sonst als Klasse wie `nce.py`). Endpunkte bleiben
  anbieterneutral – siehe `docs/sim-providers.md`.
- **Auth:** Eltern-Zugänge laufen über Benutzerkonten (`app/auth.py`, PBKDF2 +
  Sitzungstoken); `PARENT_TOKEN` bleibt als Rückfallweg für Skripte. Neue
  Eltern-Endpunkte immer mit `Depends(require_parent)` (Admin: `require_admin`).
- **Secrets:** `.env`, `ADMIN-ZUGANG.txt`, `caddy-root.crt` sind gitignoriert und
  vom WSL-Sync ausgenommen; der Pre-Commit-Hook (`scripts/git-hooks/pre-commit`)
  blockt `.env`-Dateien und Secret-Muster. Nach dem Klonen installieren:
  `cp scripts/git-hooks/pre-commit .git/hooks/pre-commit`.
- **Setup-Assistent:** Die Schritte sind serverseitig prüfbar (`GET /api/v1/parent/setup`)
  und werden in der UI als `SETUP_STEPS`/`SETUP_OPTIONAL` gespiegelt. Ein neuer
  Schritt braucht: Eintrag im Endpunkt, Markup (`#setup-step-<key>`), Eintrag in
  `SETUP_STEPS`/`SETUP_TITLES` und – wenn optional – in `SETUP_OPTIONAL`. Der
  Status ist **pro Kind** (`?device_id=<IMEI>`; ohne Parameter das erste Gerät) –
  „SIM", „Funktionstest" und „done" beziehen sich auf genau dieses Gerät
  (`docs/parent-usability.md`).
- **Verifikation:** `bash scripts/smoke-test.sh` (29 Gruppen) und
  `cd server/audio-bridge && python -m unittest discover -s tests`
  (Provider/Auth/**Fusion**/Apple-Config, 67 Tests) müssen grün bleiben; Firmware zusätzlich
  `pio run` + `pio test -e native`.
- **Sensor-Fusion:** Auswahlregeln (Vertrauen → Frische → Genauigkeit,
  Sprungfilter, Zustandserkennung) liegen in `app/fusion.py` – reine Funktionen,
  host-getestet in `tests/test_fusion.py`. Neue Quellen dort eintragen
  (`SOURCE_TRUST`/`SOURCE_VALID_S`), nicht in `main.py`.
- **Single Sign-on:** Dienste werden über die **Wurzel-URL** geöffnet
  (`https://<dienst>/?sso=<ticket>`); Tickets erzeugt
  `POST /api/v1/parent/sso/ticket` (120 s, einmalig). Nie nackte `/_sso/…`-URLs
  verlinken – Browser-Caches können dort alte Seiten zeigen.
- **Apple-Zugangsdaten** schreibt die Eltern-UI (Tab „Geräte" → „Apple Find My
  einrichten"; der Assistenten-Schritt verweist dorthin) nach
  `macless-data/config.ini` (`[Settings] appleid`, `appleid_pass`); vorhandene
  Werte bleiben erhalten, Rechte 0600. Der Dienst startet danach selbst
  (`restart: on-failure`).
- **Shell-Skripte immer mit LF schreiben** (z. B. `Path.write_bytes` bzw.
  `newline="\n"`); CRLF bricht bash in der WSL mit `$'\r': command not found`.
- Container-Namen nicht fest verdrahten (parallele Compose-Projekte, Testinstanz);
  in Skripten den Container dynamisch suchen (`docker ps --filter name=…`).
- **Eltern-UI** (`server/audio-bridge/app/static/index.html`): mobile-first,
  Orientierung **WCAG 2.2 AA** (Labels, sichtbarer Fokus, ≥44 px Bedienziele,
  Kontraste hell/dunkel, `aria-live` für Statusmeldungen, Tabs als
  `role="tablist"`/`tab`/`tabpanel` mit Pfeiltasten). Neue Formularfelder
  brauchen Label + `aria-describedby` + Fehlerfeld (`<id>-error`) und eine
  Prüfung in `validate…()`. Nach Änderungen `python scripts/check-ui-a11y.py`
  laufen lassen (ist in der CI). Fehler erscheinen **in Klartext** (`errText()`),
  ein 401 führt über den globalen `fetch`-Wrapper zurück zur Anmeldung – keine
  rohen HTTP-Codes anzeigen.

## Befehle

- Server starten: `cd server && docker compose up -d`
- Server-Logs: `cd server && docker compose logs -f audio-bridge`
- Firmware bauen: `cd firmware && pio run` (PlatformIO)
- Repo in die WSL-Distro spiegeln (aus WSL heraus): `bash scripts/sync-to-wsl.sh`
- Tests: `bash scripts/smoke-test.sh` · `pio test -e native` · `python -m unittest discover -s tests`
- UI-Prüfung: `python scripts/check-ui-a11y.py` (Quelltext: Labels, ARIA, Tab-Muster, Kontraste, Bedienziele)
- UI-Verifikation im Browser: `python scripts/ui-check.py` (headless Chrome, Screenshots aller Tabs in `ui-shots/`, Accessibility-Baum; braucht `pip install websockets` und `PARENT_PASSWORD` in `server/.env`)
- Parallele Test-Instanz: `bash scripts/start-test-instance.sh` (Ports +1000, Projekt `uttest`)

## Struktur-Konventionen

- `project.md` = Überblick, `docs/*` = Details, `firmware/` + `server/` = Code.
- Neue Entscheidungen als Eintrag in `docs/decisions.md` ergänzen.
