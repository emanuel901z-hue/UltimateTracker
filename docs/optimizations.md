# Optimierungen – Backlog (Server & Firmware)

Stand 2026-10-11. Priorisiert nach Nutzen/Aufwand. „Nutzen“ = Betriebssicherheit,
Batterielaufzeit, Wartbarkeit oder Eltern-UX. Nichts hiervon ist ein Blocker –
die aktuelle Basis läuft.

## Umsetzungsstand (2026-10-11)

| Punkt | Status |
|---|---|
| A1 Healthchecks + Startreihenfolge | ✅ umgesetzt |
| A2 Versionen pinnen (Traccar 6.16.0, WebUI-Digest, Bridge-Commit) | ✅ umgesetzt |
| A4 Benachrichtigungen (Apprise) | ✅ umgesetzt + getestet (Echo-Server) |
| A4b **Web-Push + PWA** (VAPID, Service Worker, Abo-Verwaltung) | ✅ umgesetzt + getestet (Schlüssel, Abo, Versandpfad, Cleanup) |
| Hardware-Phase vorbereitet: `docs/bring-up.md`, Mess-Session-Generator | ✅ |
| **1NCE-SMS-API** (OAuth2, SIM-/SMS-Endpunkte, UI-Karte) | ✅ umgesetzt + mit echtem Konto getestet (read-only; SIM fehlt noch) |
| **Provider-Schicht** (`SimProvider`, nce/generic, 16 Unit-Tests) | ✅ anbieterneutral – 1NCE läuft sowohl als Code-Provider als auch über das JSON-Template (`docs/sim-providers.md`) |
| A5 Sync-Endpunkt (`POST /api/v1/device/sync`) | ✅ Server-Seite umgesetzt + getestet; Firmware folgt (B4) |
| A6 Bridge-Härtung (WAL, Upload-Limit, Fail-fast, Retention) | ✅ umgesetzt + getestet |
| A7 Log-Rotation + Backup-Skript | ✅ umgesetzt (`scripts/backup-volumes.sh`) |
| A8 CI (GitHub Actions) | ✅ angelegt (Compose, Bridge, Smoke, Firmware) |
| A9 Status-Dashboard (API + UI-Karte) | ✅ umgesetzt |
| A3 TLS-Reverse-Proxy (Caddy, Profil `tls`) | ✅ umgesetzt + getestet (HTTPS, Redirect, CA-Export) |
| A10 PostgreSQL statt H2 | ✅ umgesetzt + getestet (Tabellen verifiziert, Admin neu angelegt) |
| Firmware-Logik: ADPCM, Protokoll, Wake-Policy, AGC, Ring-Log | ✅ umgesetzt, **53 Host-Tests grün** (`pio test -e native`) |
| **B10 Modem-Abstraktion + Mock** (`IModem`, `MockModem`, `wake_cycle`) | ✅ umgesetzt + getestet (kompletter Wake-Zyklus ohne Hardware) |
| **B6 NVS-Provisioning** (`config_store`, JSON-Kommando, NVS-Blob) | ✅ umgesetzt + getestet |
| **B7 OTA** (Server-Endpunkte + Angebot im Sync + Prüflogik) | ✅ Server-Seite + Logik umgesetzt/getestet; Flash-Schreiben folgt mit Hardware |
| **B3 GNSS-Auswertung** (`AT+CGNSINF`-Parser, UTC→Epoch) | ✅ umgesetzt + getestet (SIMCom-Beispielzeile) |
| **B1 Modem-Power-Modi** (aus/PSM/eDRX als Config + AT-Sequenzen) | ✅ Struktur umgesetzt; Entscheidung braucht M1/M3 |
| **B8 Feldstabilität** (Ring-Log in RTC, Reset-Zähler, monotone Uptime) | ✅ umgesetzt |
| B2 Motion-Wake-Drossel **3 min** | ✅ Konstante + Logik + Tests |
| B5 Audio-AGC, B9 Low-Battery, B11 Selbsttest | 🟡 AGC/Policy als Logik vorhanden; **Bring-up-Selbsttest als Firmware-Env umgesetzt** (`tsim7080g-s3-bringup`) |

## A. Server / Stack

### A1 – Healthchecks & Startreihenfolge · klein · hoch
Compose hat bisher nur `depends_on` (nur Startreihenfolge, keine Bereitschaft).
Folge: Find-My-Forwarding und Bridge-Aufrufe können ins Leere laufen.
**Umsetzung:** `healthcheck` für `traccar` (`GET /api/server`) und `audio-bridge`
(`GET /healthz`), dann `depends_on: {traccar: {condition: service_healthy}}`.

### A2 – Versionen pinnen · klein · hoch
`traccar:latest`, `ghcr.io/...:latest`, `python:3.12-slim` und der Bridge-`GIT_REF`
sind ungepinnt → ein Rebuild kann morgen etwas anderes bauen.
**Umsetzung:** Tags/Digests festschreiben, `GIT_REF` auf einen Commit setzen;
Renovate/Dependabot (A8) übernimmt Updates als PRs.

### A3 – TLS / Reverse-Proxy · mittel · **Pflicht vor Produktivbetrieb**
Aktuell HTTP ohne Verschlüsselung für Kinder-Audio und Positionen.
**Umsetzung:** Caddy-Dienst im Compose (`caddy:2` + `Caddyfile`), Let's Encrypt
für eine Domain oder interne CA; danach Container-Ports nicht mehr nach außen
veröffentlichen. Skizze liegt in `docs/deployment.md`.

### A4 – Benachrichtigung bei neuer Nachricht · klein · hoch
Eltern erfahren neue Audio-Nachrichten nur beim Öffnen der UI.
**Umsetzung:** `APPRISE_URL` in der Bridge (ntfy/Telegram/Pushover/E-Mail) und im
`device_upload`-Pfad auslösen; optional Web-Push (VAPID) für die UI.
Hinweis: Die Google-WebUI bringt Apprise bereits mit – wir nutzen es nur für Audio.

### A5 – Ein kombinierter Sync-Endpunkt + server-getriebenes Poll-Intervall · mittel · hoch
Heute: pro Wake bis zu 3 Funk-Roundtrips (Position → Traccar, `/pending`, ggf.
Download). Jeder Roundtrip kostet auf NB-IoT/LTE-M Sekunden und Energie.
**Umsetzung:** `POST /api/v1/device/sync` mit Body
`{device_id, battery, wake_reason, position?, fw}` →
Antwort `{search_mode, next_poll_s, message?{id,url,format}, config?, ota?}`.
Die Bridge reicht die Position intern an Traccar weiter (Funktion existiert schon
für Find My). **Ein** Attach, **ein** Request pro Wake. Alte Endpunkte bleiben
für Kompatibilität erhalten.

### A6 – Bridge-Härtung · klein · mittel
- SQLite **WAL** aktivieren (`PRAGMA journal_mode=WAL`) – weniger Locking bei parallelen Requests.
- **Upload-Limit** (z. B. 2 MB) gegen versehentliche Riesen-Uploads.
- **Fail-fast**: Start verweigern, wenn `DEVICE_TOKEN`/`PARENT_TOKEN` leer oder `change-me`.
- **Retention**: Nachrichten/Audiodateien älter als N Tage löschen (Cron im Container).
- Uplink-Nachrichten nach dem Anhören auf `read` setzen (UI zeigt sonst ewig „new“).

### A7 – Backups & Log-Rotation · klein · mittel
**Umsetzung:** `logging: {options: {max-size: "10m", max-file: "3"}}` für alle
Dienste; Backup-Skript (oder `offen/docker-volume-backup`) täglich, Ablage auf
dem Thin Client/NAS. Restore einmal testen.

### A8 – CI für Server **und** Firmware · mittel · mittel
GitHub Actions: `docker compose config`-Validierung, `python -m py_compile`,
`pio run` (Firmware-Build) + `scripts/smoke-test.sh` gegen den lokalen Stack.
Verhindert Bitrot und macht das Repo veröffentlichungsfähig.

### A9 – Eltern-UI: Status-Dashboard + PWA · mittel · hoch
Heute muss man für Position Traccar und für Audio die Bridge getrennt öffnen.
**Umsetzung:** Bridge speichert die zuletzt gemeldeten Positionen (kommt mit A5
ohnehin) und zeigt eine Karte „letzte Position, Akkustand, letzte Nachricht,
Suchmodus“; als PWA installierbar (Manifest + Service Worker) – damit auch
Push-Benachrichtigungen (A4) möglich.

### A10 – Traccar: PostgreSQL statt H2 · mittel · mittel
H2 als Datei-DB ist bei Stromausfall korruptionsgefährdet (Thin Client!).
**Umsetzung:** `postgres:16`-Dienst + `database.*`-Einträge in `traccar.xml`
(Driver/URL/User/Passwort aus `.env`). Dazu `database.registerUnknown` im
Produktivbetrieb abschalten und Geräte explizit anlegen.

### A11 – Feinschliff (klein)
- Per-Geräte-Token statt eines gemeinsamen `DEVICE_TOKEN` (Leak-Eingrenzung).
- Uptime-Überwachung (z. B. Uptime-Kuma) für 8082/8085 (und die Caddy-Adressen)
  mit Alarm per Apprise.
- 1NCE-Datenvolumen im Blick behalten (Portal-Alarm).

## B. Firmware

### B1 – Modem-Power-Gating · mittel · **größter Batteriehebel**
Drei Betriebsarten, messbar in M1/M3:
1. **PSM** (heute geplant): wenige µA, aber lange Erreichbarkeitslücken.
2. **eDRX registriert**: schnell erreichbar (RI-Wake möglich), kostet ~0,5–1 mA.
3. **Modem komplett aus** (PWRKEY GPIO 41 bzw. PMU-Rail DC3/BLDO2 per I2C):
   spart auch die PSM-Leckströme, kostet pro Wake einen vollen Network-Attach.
**Empfehlung:** Variante 3 als Default, Variante 2 nur im Suchmodus.

**Welche Informationen für die Entscheidung nötig sind:**

*Aus Schaltplan/Board (LilyGO-Schematic bzw. beim Auspacken prüfen):*
1. Hängt der Modem-Zweig an einer **schaltbaren PMU-Rail**? (Power-Domain-Tabelle
   nennt DC3/BLDO2 für GPS/Modem.) Welche Rail versorgt Modemkern, welche die
   GNSS-Antenne?
   → **Verifiziert 2026-10-12:** DC3 ist an (3,0 V) und per PMU schaltbar →
   Variante 3 ist umsetzbar. BLDO1 (1,8 V) ist der Level-Shifter und muss anbleiben.
2. Ist **PWRKEY (GPIO 41)** für `AT+CPOWD=1`/Power-Cycle nutzbar und reagiert das
   Modem darauf sauber?
   → teilweise verifiziert: PWRKEY-Puls funktioniert (Modem startet), aber ein
   zweiter Puls bei laufendem Modem verwirrt es → immer erst `AT` prüfen.
3. Bleibt die **Level-Shift-Rail BLDO1** an? (LilyGO warnt: BLDO1 nicht abschalten.)
   → bestätigt (1,8 V aktiv).

*Messungen (M1/M3):*
4. Ruhestrom in allen drei Modi (Modem aus / PSM / eDRX registriert).
5. Dauer **und** Energie pro Wake-Zyklus je Modus (voller Attach vs. PSM-Wake vs. eDRX-Wake).
6. Welche **TAU-/eDRX-Werte** vergibt das 1NCE-Netz real (`AT+CPSMS?`, `AT+CEDRXS?`)
   ⇒ tatsächliche Erreichbarkeitslatenz.
   → **Achtung (2026-10-12):** Auf diesem Board liefern `AT+CPSMS?`, `AT+CPSMS=?`,
   `AT+CEDRXS?` und `AT+CEDRXS=?` **ERROR** (ohne SIM getestet). Mit SIM erneut
   prüfen – falls PSM/eDRX dort ebenfalls nicht unterstützt werden, wird die
   PMU-Rail-Abschaltung (Variante 3) zum einzigen sauberen Weg.

*Anforderungen (deine Vorgaben):*
7. **Erreichbarkeitslatenz:** Wie schnell muss eine Eltern-Aktion (Suchmodus/Nachricht)
   ankommen? (≤ 1 min ⇒ eDRX bzw. 1-min-Poll; ≤ 15 min ⇒ PSM + Poll; „egal“ ⇒ Modem aus.)
8. **Akku-Ziel:** Tage oder Wochen?
9. Wird der **RI-/SMS-Wake** gebraucht? (setzt registriertes Modem voraus.)
10. Nutzungsprofil: täglich unterwegs oder nur gelegentlich?

*Vorbereitung im Code:* Alle drei Modi werden hinter einer NVS-Option implementiert
plus ein Mess-Harness, das pro Wake Dauer/Energie loggt. Dann ist die Entscheidung
nach M1/M3 nur noch ein Konfigurationswert.

### B2 – Motion-Wake-Drossel · klein · hoch
Kinder bewegen sich ständig → ohne Drossel entstehen Wake-Stürme.
**Umsetzung (Vorgabe: maximal 3 Minuten):** Mindest-Schlafzeit nach einem Bewegungs-Push **3 min** (`MOTION_MIN_SLEEP_S = 180`),
N aufeinanderfolgende Schwellwert-Treffer abwarten, Schwellwert/Dauer im LIS3DH
tunen (Start: ~200 mg, 2 Samples). Im Suchmodus deaktivieren.

### B3 – GNSS: Hot-Start & Almanach · klein · mittel
Erster Fix ist teuer. **Umsetzung:** nach dem ersten Fix `AT+CGNSHOT` (Hot Start)
für Folge-Wakes nutzen, Almanach gelegentlich per `AT+CGNSXTRA` aktualisieren,
Antennen-Power (`AT+SGPIO=0,5,1,1`) nur während des Fixes an lassen.

### B4 – Server-getriebenes Poll-Intervall umsetzen · klein (paired mit A5)
Die Bridge liefert `next_poll_s`; die Firmware nutzt es für den nächsten Timer-Wake.
Vorteil: Intervalländerungen (Nacht, Suchmodus, Akku) ohne Reflash.

### B5 – Audio-Qualität & Lautstärke · klein–mittel · hoch
- **AGC/Verstärkung** vor der ADPCM-Kodierung (INMP441 ist leise) → deutlich
  bessere Verständlichkeit; simpel als Peak-Normalisierung.
- **MAX98357A-GAIN-Pin** auf 15 dB (statt Default 9 dB) → lautere Wiedergabe;
  Modul-Pads prüfen. Für Kinderohren Lautstärke begrenzen.
- Optional **VAD** (Sprachaktivität): Stille trimmen → kürzere Uploads.

### B6 – Provisioning in NVS statt Compile-Time · mittel · hoch
Tokens/Server-URL/Intervalle/Volume in `Preferences` (NVS) speichern;
Einrichtung per USB-Serial (JSON-Kommando, nur in den ersten Sekunden nach Boot).
Danach: kein Reflash mehr für Konfigurationsänderungen.

### B7 – OTA-Update über LTE · mittel · hoch
Bei einem Gerät am Kind ist Zerlegen zum Flashen keine Option.
16 MB Flash bieten Platz für zwei App-Slots (`default_16MB` → OTA-Partitionen).
**Umsetzung:** Bridge stellt `/api/v1/device/firmware/latest` (Binär + SHA256 +
Version) bereit; Firmware lädt nach dem Poll, schreibt mit `Update`, prüft Hash,
rebootet, Rollback bei Fehlschlag.

### B8 – Feldstabilität · klein · hoch
- Brownout-Detector aktiv lassen, **Reset-Grund** und Zähler in NVS loggen.
- Task-Watchdog aktivieren; Modem-TX-Stromspitzen mit 470 µF abfangen (BOM ✓).
- **Ringpuffer-Log** (letzte ~20 Ereignisse) in NVS → bei Problemen auslesbar
  oder mit dem nächsten Sync hochladen.

### B9 – Low-Battery-Verhalten · klein · mittel
Akkustand über AXP2101 lesen; unter ~15 %: Poll-Intervall verlängern, Audio-Uplink
weiter erlauben, Wiedergabe begrenzen, Akkustand als `batt` mitsenden (Traccar
zeigt ihn bereits an).

### B10 – Struktur & Toolchain · mittel · mittel
- Modem-Code in eigenen Task mit Mutex (TinyGSM ist blockierend), Audio-Task
  getrennt; klare Zustandsmaschine (Skelett vorhanden).
- **Arduino-Core 3.x (pioarduino)** evaluieren: neuer I2S-Treiber (Full-Duplex)
  ist sauberer als der Legacy-Treiber; Aufwand einmalig, Risiko klein.

### B11 – Selbsttest beim Boot (POST) · klein · mittel
Modem-AT, GNSS-Antennenstrom, I2S-Loopback, Akku, Reset-Grund prüfen und als
Attribut im ersten Sync mitsenden – spart Fehlersuche im Feld.

## C. Gemeinsames Protokoll (Firmware ↔ Bridge)

### C1 – Ein Roundtrip pro Wake
Siehe A5/B4: Position, Konfiguration, Nachrichten und OTA-Info in **einem**
Request/Antwort-Paar.

### C2 – Konfiguration vom Server
Poll-Intervall, Suchmodus, Lautstärke, Log-Level – alles im Sync-Response;
Firmware wendet es an und meldet die aktive Konfiguration zurück.

### C3 – Versions-Handshake
Firmware sendet `fw`-Version + Feature-Flags; Bridge antwortet mit `min_fw` und
Feature-Liste. Ältere Firmware fällt automatisch auf die alten Endpunkte zurück
(Abwärtskompatibilität bleibt erhalten).

## Empfehlung: „Paket 1“ (sofort umsetzbar, ohne Hardware)

| Punkt | Warum jetzt |
|---|---|
| A1 Healthchecks | verhindert stille Forwarding-Fehler |
| A2 Versionen pinnen | reproduzierbare Deployments vor dem Umzug |
| A6 Bridge-Härtung | WAL, Limits, Fail-fast, Retention – kleine Eingriffe, große Wirkung |
| A7 Backups + Log-Rotation | einmal einrichten, dauerhaft Ruhe |
| A4 Benachrichtigungen | größter UX-Gewinn für die Eltern |
| A8 CI | hält Server + Firmware baubar |

„Paket 2“ (mit Hardware): A5+C1 (Sync-Endpunkt), B2 (Wake-Drossel), B5 (Audio),
B8 (Feldstabilität), A9 (Status-Dashboard).
„Paket 3“ (vor Produktivbetrieb): A3 (TLS), B6 (NVS), B7 (OTA), A10 (PostgreSQL).
