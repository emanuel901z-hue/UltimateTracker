# Eltern-Tauglichkeit: Bestandsaufnahme & Umsetzungsplan

Diese Datei hält die Analyse der Server-/UI-Schicht (`server/audio-bridge`) aus
Sicht **nicht-technischer Eltern** fest. Zielgruppe: Eltern, die den fertig
installierten Stack „vorgesetzt" bekommen und zwischendurch **neue Tracker
hinzufügen und konfigurieren** müssen – auf allen Ebenen (Gerät, SIM, Karte,
Benachrichtigungen, Diagnose).

Maßstab: Eine Person ohne Terminal, ohne `.env`-Wissen und ohne Kenntnis der
Dienste (Traccar, Caddy, SIM-Provider) muss einen zusätzlichen Tracker
eigenständig in Betrieb nehmen und im Alltag Störungen einordnen können.

> **Status:** Bestandsaufnahme 2026-10-13. Die Umsetzung erfolgt in Sprints
> (siehe unten); nach jedem Sprint laufen die Prüfungen aus `AGENTS.md`.

## 1. Ausgangslage (kurz)

Die Server-Schicht ist funktional weit: Login/Benutzerkonten, Geräte-Registry,
Setup-Assistent (9 Schritte), Sensor-Fusion, SIM-Provider, OTA-Endpunkte,
Monitoring, Backup. Für **einen** Tracker ist der Weg tragfähig. Die Lücken
treten auf, sobald es **mehr als ein Kind** gibt oder ein **zweiter Tracker**
dazukommt – und überall dort, wo technische Rohwerte nach außen sichtbar sind.

## 2. Befunde

Priorität: **P1** = blockiert den Kernablauf, **P2** = Frust/Verwirrung im
Alltag, **P3** = Komfort/Vollständigkeit.

### A. Neuen Tracker hinzufügen & konfigurieren (Kern) — P1

| # | Befund | Beleg |
|---|---|---|
| A1 | **Setup-Assistent ist fest auf das erste Gerät verdrahtet.** `GET /api/v1/parent/setup` liefert `device = devices[0]`; SIM-Schritt und „done" sind global, nicht pro Kind. Ein zweites Kind lässt sich über den Assistenten nicht einrichten. | `main.py` (`setup_status`), `index.html` (`s-sim-save`, `loadSetup`) |
| A2 | **SMS geht an das falsche Kind.** SIM-Auswahl nutzt `sims[0]`, SMS-Verlauf nutzt `setupState.device.iccid` – beide ignorieren die oben gewählte Kinder-Auswahl. | `index.html` (`loadSmsStatus`, `loadSmsHistory`) |
| A3 | **Geräte sind in der UI nicht bearbeitbar/löschbar.** Die Liste ist reine Anzeige; Änderungen erfordern das Neutippen der 15-stelligen IMEI. Der `DELETE`-Endpunkt hat keinen Knopf. | `index.html` (`loadDevices`), `main.py` (`device_delete`) |
| A4 | **Löschen ohne Kaskade.** `device_delete` entfernt nur die `devices`-Zeile; `positions`, `messages`, `beacons`-Zuordnung und das Traccar-Gerät bleiben zurück. | `main.py` (`device_delete`) |
| A5 | **Geistergeräte.** `ensure_device` legt jedes unbekannte Gerät an; ein IMEI-Vertipper erzeugt ein zweites (nie gesehenes) Gerät – ohne Zusammenführen oder Aufräumen. | `main.py` (`ensure_device`) |
| A6 | **IMEI nur per Regex geprüft** (`^[0-9]{15}$`), kein Prüfziffern-Test (Luhn). | `index.html` (`requireImei`, `s-save`) |
| A7 | **Kein „warten auf ersten Kontakt"-Weg.** Realistisch wäre: Tracker einschalten → er meldet sich → „neu erkanntes Gerät benennen". Stattdessen IMEI vom Aufkleber abtippen (Verweis auf `AT+GSN`-Konsole ist für Eltern unbrauchbar). | `index.html` (Willkommen-Schritt) |
| A8 | **SIM-Semantik irreführend.** „SIM eintragen (optional) … nur für den SMS-Pfad" – die SIM ist aber für **jede** Ortung (LTE) Pflicht; nur die ICCID-Eingabe ist optional. | `index.html` (Schritt 2) |

### B. Erstinstallation / Übergabe — P1/P2

| # | Befund | Beleg |
|---|---|---|
| B1 | **Traccar-Zugangsdaten im Klartext** in der UI, ohne Kopierknopf und ohne „bitte ändern"-Führung. | `index.html` (`setup-traccar-creds`) |
| B2 | **Erstanmeldung offen, solange kein Konto existiert** (`users_count()==0`). Ist die Box vor dem ersten Login erreichbar, kann sich jeder den Admin nehmen. | `main.py` (`auth_register`) |
| B3 | **Kein Eltern-Handbuch.** Die gesamte Doku ist Entwickler-orientiert (Terminal, `.env`, `docker compose`). | `docs/*` |
| B4 | **Hartkodierter Fortschrittstext** „Schritt 1 von 7" bei 9 Schritten. | `index.html` (`setup-progress`) |

### C. Fehler- und Zustandsmeldungen — P2

| # | Befund | Beleg |
|---|---|---|
| C1 | **Rohe HTTP-Codes / englische Fehler** erreichen die Eltern („HTTP 401", `err.message`). | `index.html` (viele Stellen) |
| C2 | **Keine globale 401-Behandlung.** Nach Sitzungsablauf oder Passwortwechsel auf einem anderen Gerät zeigt die UI weiter „angemeldet", aber überall „HTTP 401". | `index.html` (kein `fetch`-Wrapper), `main.py` (`auth_password`) |
| C3 | **`window.prompt` für Admin-Passwort-Reset** – inkonsistent, nicht barrierefrei, Klartext. | `index.html` (`data-reset`) |

### D. Diagnose „warum meldet mein Tracker nicht?" — P2

| # | Befund | Beleg |
|---|---|---|
| D1 | **Keine zusammengefasste Antwort** auf die häufigste Supportfrage; der Status-Tab ist ein Rohdump (Poll-Sekunden, 5 Nachkommastellen). | `index.html` (`loadStatus`) |
| D2 | **Keine Offline-Warnwirkung** in der Kinder-Übersicht (nur „zuletzt <Zeitstempel>"). | `index.html` (`loadChildren`) |
| D3 | **`probe_http` wertet 401/404 als „erreichbar"** – ein defekter Dienst kann „up" wirken. | `main.py` (`probe_http`) |

### E. Einstellungen — P2

| # | Befund | Beleg |
|---|---|---|
| E1 | **Technische Rohwerte** (Sekunden, Prozent, „(1/0)"), kein Schalter, kein Zurücksetzen. | `main.py` (`SETTING_DEFS`), `index.html` (`loadSettings`) |

### F. Benachrichtigungen — P2

| # | Befund | Beleg |
|---|---|---|
| F1 | **Nur Web-Push konfigurierbar** (braucht HTTPS/localhost). Über LAN-IP am Handy gibt es keinen Weg und keinen Fallback. | `index.html` |
| F2 | **`APPRISE_URLS` nur per `.env`** – Eltern können E-Mail/ntfy/Telegram nicht einrichten. | `main.py` |

### G. SIM-/SMS-Anbieter — P2

| # | Befund | Beleg |
|---|---|---|
| G1 | **Provider-Zugangsdaten nur per `.env`**; die UI verweist wörtlich auf `server/.env`. | `main.py` (`sim_provider`), `index.html` (`sms-state`) |
| G2 | **Keine SIM↔Kind-Zuordnung** in der UI. | `index.html` (SMS-Karte) |

### H. Kleinere Widersprüche / Doku-Drift — P3

| # | Befund | Beleg |
|---|---|---|
| H1 | **Firmware/OTA hat keine UI**, obwohl README/TODO „Firmware-Updates" in der Operationszentrale nennen. | `main.py` (Endpunkte), `index.html` (kein Markup) |
| H2 | **Kartenkacheln default OSM** (extern) – ohne Internet leere Karte ohne Erklärung. | `main.py` (`MAP_TILES`) |
| H3 | **Backup nur als Download**, kein Restore, keine Rahmung; Retention als rohe Tage. | `main.py`, `index.html` |

## 3. Sprintplan

| Sprint | Inhalt | Bezug | Status |
|---|---|---|---|
| **0** | Diese Bestandsaufnahme + Plan | – | ✅ |
| **1** | Mehrkind-Kern: Assistent gerätebewusst, SMS/SIM am gewählten Kind, „Weiteres Kind hinzufügen" | A1, A2, A8 | ✅ |
| **2** | Geräte-Verwaltung: bearbeiten/löschen in der UI, Lösch-Kaskade, Phantom-Erkennung | A3, A4, A5, A6 | ✅ |
| **3** | Fehler & Sitzung: globaler `fetch`-Wrapper (401 → Login), Klartextmeldungen, `window.prompt` ersetzen | C1, C2, C3 | ✅ |
| **4** | Onboarding & Diagnose: Traccar-Zugang kopierbar, Schritt-Zähler, Kinder-Gesundheitsampel | B1, B4, D1, D2 | ✅ |
| **5** | Einstellungen in Elternsprache + Zurücksetzen; Firmware-UI bzw. Doku-Korrektur | E1, H1 | ✅ |

**Verifikation nach jedem Sprint** (siehe `AGENTS.md`):
`python -m py_compile server/audio-bridge/app/main.py` ·
`cd server/audio-bridge && python -m unittest discover -s tests` ·
`python scripts/check-ui-a11y.py` ·
`bash scripts/smoke-test.sh` (WSL, laufender Stack) ·
`python scripts/ui-check.py` (headless Chrome, WSL).

## 4. Umsetzung (was sich geändert hat)

Alle Sprints sind umgesetzt, getestet und dokumentiert. Betroffene Dateien:
`server/audio-bridge/app/main.py`, `server/audio-bridge/app/static/index.html`,
`scripts/smoke-test.sh`.

**Sprint 1 – Mehrkind-Kern**
- `GET /api/v1/parent/setup?device_id=<IMEI>` prüft „SIM", „Funktionstest" und
  „done" **pro Kind**; ohne Parameter bleibt das erste Gerät (kompatibel). Die
  Antwort enthält die Geräteliste für die Auswahl.
- Der Setup-Assistent bezieht sich auf das oben gewählte Kind; **„Weiteres Kind /
  Tracker hinzufügen"** startet denselben Ablauf für eine neue IMEI und schaltet
  danach auf das neue Kind um.
- SMS-Versand und SMS-Verlauf nutzen die **ICCID des gewählten Kindes** (statt
  der ersten SIM im Konto); fehlt sie, gibt es einen klaren Hinweis.
- SIM-Schritt im Assistenten: eingelegte SIM als **Pflicht** benannt, ICCID-Eingabe
  als optional (nur SMS).

**Sprint 2 – Geräte-Verwaltung**
- Geräteliste mit **bearbeiten** (ID bleibt fest) und **löschen** (mit
  Bestätigung); nie gesehene Geräte sind markiert.
- `GET /api/v1/parent/devices` liefert `seen`/`last_seen`/Zähler.
- `DELETE /api/v1/parent/devices/{id}` räumt **kaskadierend** auf (Nachrichten +
  Audio-Dateien, Positionen, Beacon-Zuordnungen) und antwortet für unbekannte
  Geräte mit 404. Das Traccar-Gerät bleibt (ein aktiver Tracker meldet sich dort
  sonst sofort wieder an).
- IMEI wird zusätzlich über die **Luhn-Prüfziffer** validiert (fängt Zahlendreher).

**Sprint 3 – Fehler & Sitzung**
- Globaler `fetch`-Wrapper: **401 führt zurück zur Anmeldung** („Deine Anmeldung
  ist abgelaufen …") statt roher Codes; `/api/v1/auth/*` bleibt ausgenommen.
- `errText()` ersetzt rohe HTTP-Meldungen in der ganzen UI durch Klartext.
- Admin-Passwort-Reset über ein **Formular** statt `window.prompt`.

**Sprint 4 – Onboarding & Diagnose**
- Traccar-Zugangsdaten mit **Kopierknopf**.
- Kinder-Übersicht mit **Gesundheitsampel** (aktuell / zuletzt vor … / offline
  seit …) und Akku-Warnung; die Status-Karte spricht in Klartext
  („Letzter Kontakt: vor 2 Std.").
- Fortschrittstext des Assistenten zählt korrekt (9 Schritte).

**Sprint 5 – Einstellungen & Firmware**
- Einstellungen mit **Elternsprache, Kurzhilfen und Schalter** statt „(1/0)",
  plus **„Standardwerte einsetzen"**; der Endpunkt liefert Label/Hilfe/Standard.
- **Firmware-Karte** im Tab „Betrieb" (Version + `.bin` hochladen, Liste,
  entfernen) – die OTA-Endpunkte sind damit auch über die UI erreichbar.

**Offen geblieben** (bewusst): Benachrichtigungen jenseits von Web-Push (F2),
SIM-Provider-Zugangsdaten in der UI (G1), Kartenkacheln offline (H2), Backup
nur als Download (H3) – siehe unten.

## 5. Bewusst nicht im Scope

- **Kalman-Filter** (Sensor-Fusion) – eigenständiges Thema in `docs/fusion.md`.
- **Echte Echtzeit-PTT** – hardwarebedingt ausgeschlossen (siehe `project.md` 3.3).
- **Provider-Zugangsdaten in der UI (G1)** – bleibt `.env` (Secrets gehören nicht
  in die Weboberfläche); stattdessen klarere Fehlermeldung/Anleitung im Sprint 5.
