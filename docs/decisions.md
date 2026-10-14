# Entscheidungsprotokoll (ADR-Kurzform)

Neue Einträge oben ergänzen. Format: Datum – Entscheidung – Begründung – Folgen.

## D-019 – 2026-10-13 – Ein Ingest für alle Find-My-Wege, Beacon-Schlüssel (provider, id)

- **Entscheidung:** Alle Positionsquellen laufen über **einen** Anlaufpunkt in der
  Bridge. Dafür ergänzt die Bridge einen **OsmAnd-kompatiblen Ingest**
  (`GET /api/v1/findmy/osmand?id=&lat=&lon=&timestamp=&hdop=&provider=`), und die
  Apple-Bridge (`findmy-bridge`) zeigt dorthin (`APPLE_BRIDGE_TARGET`) statt
  direkt auf Traccar. Der Beacon-Schlüssel der Fusion ist jetzt
  **(provider, beacon_id)** statt nur `beacon_id`; bestehende Zuordnungen werden
  migriert.
- **Begründung:** Zuvor hatten die beiden Find-My-Wege verschiedene Ziele: Google
  → Bridge (Fusion ✓), Apple → Traccar (an der Fusion **vorbei**). Damit war die
  in `README`/`project.md` beworbene Fusion „GNSS + Apple/Google" für Apple nicht
  wirksam, und Apple-Positionen erschienen als Fremdgerät in Traccar. Ein
  OsmAnd-Ingest genügt, weil dieses Protokoll die beteiligten Werkzeuge ohnehin
  sprechen. Der Provider im Beacon-Schlüssel verhindert, dass gleichnamige Beacons
  zweier Netze einander überschreiben (vorher war `beacon_id` der Primärschlüssel).
- **Folgen:** Ein Prinzip statt drei Ziel-Konfigurationen („alles postet an den
  Ingest; die Bridge entscheidet"). Neuer Endpunkt `GET /api/v1/parent/sources`
  (letzte Position je Quelle) plus UI-Karte. Smoke-Gruppe 30 deckt Ingest,
  Quellen-Status und Provider-Trennung ab. Der Traccar-Forward bleibt optional
  (`TRACCAR_FORWARD_URL`).

## D-018 – 2026-10-13 – SSO-Gate: Sitzungscookie per Einmal-Ticket auf dem Ziel-Host

- **Entscheidung:** Dienste hinter dem Eltern-Gate (`findmy.localhost`,
  `apple.localhost`) öffnen sich über
  `https://<dienst>/_sso/session?ticket=<ticket>&next=/`. Die Bridge validiert
  das Einmal-Ticket und setzt **auf dem Ziel-Host** ein **host-only**
  Sitzungscookie (ohne `Domain`); Caddy leitet `/_sso/*` **vor** `forward_auth`
  an die Bridge.
- **Begründung:** Das Sitzungscookie der Eltern-UI wird mit `Domain=localhost`
  gesetzt – das verwerfen die Browser (RFC 6265 verlangt einen Punkt), deshalb
  kam von `audio.localhost` nie ein Cookie bei `findmy.localhost`/
  `apple.localhost` an und `forward_auth` antwortete mit „HTTP ERROR 401"
  (dasselbe Problem, das D-013 für Traccar gelöst hat). Für die Gate-Dienste
  fehlte die Ticket-Mechanik.
- **Folgen:** `/_sso/session` (Bridge, erzeugt aus dem Ticket eine echte
  Sitzung), `handle /_sso/*` in den Find-My-Blöcken des Caddyfiles,
  `gate`-Flag in `/api/v1/parent/services` und Ticket-Links in der UI.
  Smoke-Gruppe 29 prüft 302, host-only-Cookie und `verify=200`.
  (Apple bleibt bei fehlender Apple-ID ein 502 des Upstreams – nicht mehr 401.)

## D-017 – 2026-10-13 – Eltern-Tauglichkeit: Mehrkind, Geräteverwaltung, Fehlerbild

- **Entscheidung:** Der Server/UI wird für **nicht-technische Eltern** gehärtet
  (Analyse und Umsetzung in `docs/parent-usability.md`):
  - Der Setup-Assistent arbeitet **pro Kind** (`/api/v1/parent/setup?device_id=`),
    inklusive „Weiteres Kind / Tracker hinzufügen"; SMS/SIM folgen der
    Kinder-Auswahl.
  - Geräte lassen sich in der UI **bearbeiten und löschen**; das Löschen räumt
    kaskadierend auf. Nie gesehene Geräte werden markiert; die IMEI wird per
    **Luhn-Prüfziffer** geprüft.
  - Ein globaler `fetch`-Wrapper führt bei **401 zurück zur Anmeldung**; rohe
    HTTP-Codes werden durch Klartextmeldungen ersetzt.
  - Einstellungen erscheinen in Elternsprache (mit Standardwerte-Knopf), die
    Firmware-Verwaltung ist jetzt auch in der UI.
- **Begründung:** Die Box wird fertig installiert übergeben; ein zweiter Tracker
  und Störungen im Alltag müssen ohne Terminal und ohne `.env`-Wissen
  beherrschbar sein. Zuvor war der Assistent fest auf das erste Gerät verdrahtet,
  SMS ging bei mehreren Kindern an das falsche, und Fehler erschienen als
  „HTTP 401".
- **Folgen:** `main.py` (setup/ devices/ settings/ firmware), `index.html`,
  zwei neue Smoke-Gruppen (25: Mehrkind-Setup/Aktivität, 26: Firmware) → 26
  Gruppen. Offen bleiben Web-Push-Alternativen, Provider-Zugangsdaten in der UI
  und Offline-Kartenkacheln (`docs/parent-usability.md` 5).

## D-016 – 2026-10-12 – Lizenz: MIT

- **Entscheidung:** Das Projekt steht unter **MIT** (`LICENSE`).
- **Begründung:** Kurz, permissiv, für ein Bastel-/Freizeitprojekt mit
  Server-, Firmware- und Dokuanteil die einfachste Wahl. Die hardware-nahen
  Teile (Pinbelegung, Schaltungs-/Gehäuseplanung) sind mit abgedeckt; eine
  formale Hardware-Lizenz (CERN-OHL-S) wäre später ergänzbar.
- **Folgen:** README nennt die Lizenz; Haftungsausschluss inklusive
  („kein Medizin-/Sicherheitsprodukt", siehe `SECURITY.md`).

## D-015 – 2026-10-12 – Operationszentrale ist die Bridge, nicht Traccar

- **Entscheidung:** Die Eltern-Oberfläche der Audio-Bridge ist der **eine
  Einstiegspunkt** (Login, Kinder-Übersicht, Nachrichten, Geräte, Benutzer,
  SIM/SMS, OTA, Monitoring, Einstellungen, Backup). Traccar bleibt die
  Karten-/Tracking-App und wird **eingebettet** (iframe) und verlinkt.
- **Begründung:** Traccar ist eine Java-Anwendung mit kompilierter Vue-Oberfläche;
  eigene Seiten/Logik darin zu integrieren hieße, die Web-App zu ersetzen – und
  damit bei jedem Update zu brechen. Geprüft: Traccar liefert kein
  `X-Frame-Options`, das Einbetten ist also erlaubt.
- **Folgen:** Ein Login statt zwei; Kartenwechsel entfällt. Wenn Traccar hinter
  denselben Login soll, wäre das über Caddy `forward_auth` nachrüstbar.

## D-014 – 2026-10-12 – Eltern-Zugänge: Benutzerkonten statt nur Token

- **Entscheidung:** Login mit Benutzername/Passwort (PBKDF2-HMAC-SHA256,
  120 000 Runden, Sitzungstoken 30 Tage), Benutzerverwaltung mit Rollen,
  Passwortwechsel und Admin-Reset. Der feste `PARENT_TOKEN` bleibt als
  Rückfallweg (Skripte, Smoke-Test, Erstinstallation).
- **Begründung:** Ein einzelnes Token im Browserfeld ist kein Login und nicht
  geeignet, wenn mehrere Erwachsene und mehrere Kinder dazukommen. Der erste
  Administrator entsteht aus `PARENT_USER`/`PARENT_PASSWORD` in `server/.env`.
- **Folgen:** Suchmodus ist **pro Kind** (`search_mode_until:<device_id>`);
  Kinder-Übersicht über `/api/v1/parent/overview`. Details: `docs/deployment.md` 5b.

## D-013 – 2026-10-12 – SIM-/SMS-Anbieter hinter einer Provider-Schicht

- **Entscheidung:** Die Bridge spricht SIM-/SMS-Anbieter nur über
  `app/providers/` an (`SimProvider`). 1NCE und wherever SIM sind eigene
  Klassen, weitere Anbieter werden über eine JSON-Konfiguration angebunden
  (Vorlagen für EMnify, Onomondo, Twilio Super SIM).
- **Begründung:** Anbieter unterscheiden sich in Auth (OAuth2, Header, Basic,
  Zwei-Schritt), Adressierung (ICCID vs. interne ID) und API-Stil (REST vs.
  GraphQL). Ein Fork/Anbieterwechsel soll eine Konfigurationsfrage sein, kein
  Umbau – und ein API-Versionssprung (v2→v3) eine Umgebungsvariable.
- **Folgen:** Endpunkte bleiben anbieterneutral; WhereverSIM bringt zusätzlich
  Echtzeit-SMS per WebSocket-Subscription (`SMS_SUBSCRIBE=1`).
  Details: `docs/sim-providers.md`.

## D-012 – 2026-10-11 – Apple-Pfad: automatische Traccar-Bridge statt manueller Auswertung

- **Entscheidung:** `findmy-bridge` (jannisko/findmy-traccar-bridge, findmy.py) läuft
  im Profil `findmy` und synchronisiert die Standorte der DIY-/OpenHaystack-Beacons
  automatisch nach Traccar. `anisette` bleibt Auth-Dienst; `macless-haystack` bleibt
  für Key-Generierung und optionale Web-UI.
- **Begründung:** Die bisherige Apple-Auswertung war manuell/skriptbasiert. Geprüfte
  Alternativen: `traccar/apple-find-my-sync` ist ein **nativer macOS-Service**
  (unbrauchbar für Linux/Docker); `nikita-skakun/apple-find-my-sync` ist AirTag-first
  (DIY nur „planned“) und braucht macOS-Bootstrap. Nur die jannisko-Bridge unterstützt
  DIY-Beacons ohne Mac.
- **Folgen:** `APPLE_BEACON_KEYS` + `APPLE_POLL_INTERVAL` in `server/.env`;
  interaktive Erst-Initialisierung der Bridge; Ban-Risiko dokumentiert
  (Default 1 Abfrage/Stunde). Details: `docs/findmy.md`.

## D-011 – 2026-10-11 – Google-Pfad: WebUI als Standard, Microservice als Minimal-Option

- **Entscheidung:** Für Google Find Hub läuft standardmäßig die
  `google-findmy-webui` (Profil `findmy`, Port 4321). Der reine Microservice
  bleibt als Profil `google-minimal` erhalten und baut jetzt aus dem
  **Traccar-Fork** (`traccar/google-find-hub-sync`) statt aus einem Dritt-Fork.
- **Begründung:** Die WebUI enthält den offenen Key-Rotations-Fix
  (leonboe1/GoogleFindMyTools#114), bietet Geräte-/Schedule-Verwaltung, ein
  Traccar-OsmAnd-Preset und Firmware-Build/-Flash im Browser – genau die
  „Initialisieren und Auswerten“-Anforderungen. Der Traccar-Fork ist die
  vertrauenswürdigste Minimal-Quelle, hat den Bug aber noch.
- **Folgen:** `docs/findmy.md` beschreibt beide Wege plus Alternativen
  (Traccar Relay, MQTT-Fork, go-findmy, ioBroker). WebUI braucht
  `WEBUI_USER`/`WEBUI_PASSWORD` (Default: HTTP ohne Auth) und optional
  `SECRETS_ENCRYPTION_KEY`.

## D-010 – 2026-10-11 – Geräte-Registry mit IMEI als Primär-ID

- **Entscheidung:** Die Bridge führt eine Geräte-Registry (`id` = IMEI, dazu Name,
  MSISDN, Notizen); unbekannte Geräte werden beim ersten Kontakt automatisch angelegt.
- **Begründung:** IMEI/SIM ist die natürliche Identität des Trackers (Traccar-OsmAnd
  `id=`), die MSISDN wird für den optionalen SMS-Pfad mitgeführt.
- **Folgen:** Eltern-UI mit Geräteverwaltung; ein späteres SMS-Gateway kann an die
  Registry andocken. Details: `docs/sms.md`.

## D-013 – 2026-10-13 – Dienst-Anmeldung per Einmal-Ticket statt Cookie

- **Entscheidung:** Dienste werden über `https://<dienst>/?sso=<ticket>` geöffnet;
  das Ticket erzeugt die Bridge (120 s, einmalig) und löst es serverseitig ein.
- **Begründung:** Browser verwerfen Cookies mit `Domain=localhost` (RFC 6265
  verlangt einen Punkt), deshalb kann das Sitzungscookie fremde Hosts nicht
  erreichen. Zusätzlich lieferte Traccar seine SPA mit `max-age=3600` aus, was
  für unbekannte Pfade zu schwarzen Seiten führte.
- **Folgen:** Traccar bekommt kein `forward_auth` (eigenes Konto bleibt),
  die Wurzel-URL ist der Einstieg; Find-My-Oberflächen bleiben hinter dem Gate.

## D-012 – 2026-10-13 – Sensor-Fusion: auswählen statt mitteln

- **Entscheidung:** Mehrere Quellen (GNSS, Apple/Google Find My, Funkzelle)
  werden nach Vertrauensstufe → Frische → Genauigkeit **ausgewählt**, nie
  gemittelt; Traccar erhält genau eine Position je Kind.
- **Begründung:** Mitteln von GNSS (3–10 m) mit Crowd-Netz-Positionen
  (50–100 m) würde die gute Quelle verschlechtern.
- **Folgen:** `app/fusion.py` (host-getestet), Beacon-Zuordnung in der UI,
  Sprungfilter und Zustandserkennung; Kalman-Filter bleibt offen (docs/fusion.md).

## D-011 – 2026-10-13 – Erststart ohne Terminal

- **Entscheidung:** `docker compose up -d` + Browser genügt: Tokens erzeugt die
  Bridge selbst (in der Datenbank), den Traccar-Administrator legt sie an,
  das Eltern-Konto entsteht über „Konto anlegen" beim ersten Aufruf.
- **Begründung:** Der Einstieg muss ohne Konsole funktionieren (Rückmeldung:
  „ein DAU hat nie eine Konsole geöffnet").
- **Folgen:** `server/.env` ist optional; Apple-Zugangsdaten schreibt der
  Assistent (D-010).

## D-010 – 2026-10-13 – Apple-Einrichtung über den Setup-Assistenten

- **Entscheidung:** Apple-ID und Passwort werden in der UI erfasst; die Bridge
  schreibt sie nach `macless-data/config.ini` und der Dienst startet selbst neu.
- **Begründung:** Das Image fragt beim ersten Start interaktiv ab (`input()`) –
  im Container ohne Terminal endet das im `EOFError` (Neustart-Schleife).
- **Folgen:** `PUT /api/v1/parent/apple`; vorhandene Werte bleiben erhalten,
  Rechte 0600; `restart: on-failure` statt Limit 3.
- **Nachtrag 2026-10-13:** Das Formular liegt dauerhaft im Tab **„Geräte"**
  („Apple Find My einrichten") und ist damit auch für **bestehende** Geräte
  erreichbar; der Assistenten-Schritt verweist nur noch dorthin (vorher war das
  Formular ausschließlich im Assistenten und praktisch unauffindbar).

## D-009 – 2026-10-11 – Find My optional im Stack (Apple + Google), experimentell

- **Entscheidung:** Compose-Profil `findmy` mit `anisette` + `macless-haystack` (Apple)
  und `google-findmy` (Google Find Hub, Community-Microservice). Die Bridge bekommt
  einen toleranten Ingest (`/api/v1/findmy/locations`) und optionales Traccar-Forwarding.
- **Begründung:** Beide Netze sind für DIY inzwischen über Community-Projekte nutzbar
  (Apple: macless-haystack; Google: google-find-hub-sync mit fertigem Docker-Microservice).
  Initialisierung und Auswertung sollen im eigenen Stack laufen.
- **Folgen:** **D-004 ist damit überholt** (Find My nicht mehr ausgeschlossen). Beide
  Wege bleiben experimentell (Apple filtert Klone, Google ist Community-Code);
  Beacon-Dauerbetrieb (Strom) ist separat zu lösen. Details: `docs/findmy.md`.

## D-008 – 2026-10-11 – Repository wird öffentlich vorbereitet

- **Entscheidung:** Git-Repository lokal anlegen, Struktur für Veröffentlichung
  (README, Doku, .gitignore); Lizenz: **MIT** (siehe D-012).
- **Begründung:** Projekt soll „früher oder später“ öffentlich verfügbar sein.
- **Folgen:** Keine Secrets im Repo (`server/.env` gitignored); Lizenzentscheidung
  (MIT/GPL/CERN-OHL) vor dem Push.

## D-007 – 2026-10-11 – Gehäusehöhe ~20–22 mm statt 14–16 mm

- **Entscheidung:** Bauhöhenziel korrigieren.
- **Begründung:** Board ist 111 × 32 × 20 mm (mit 18650-Halter); mit 103450-LiPo
  (10 mm) statt Halter ergibt sich realistisch ~18–20 mm Elektronikpaket.
- **Folgen:** CAD entsprechend; Tragekonzept (Anhänger/Gürteltasche) prüfen.

## D-006 – 2026-10-11 – Dedizierte WSL-Distro „UltimateTracker“

- **Entscheidung:** Eigene WSL-Distro für Entwicklung/Test des Docker-Stacks,
  Installation auf `D:\WSL\UltimateTracker`.
- **Begründung:** Sauberste Trennung; bestehende Distros (Wartesystem, AG2) bleiben
  unberührt; C: ist fast voll.
- **Folgen:** Repo wird per Skript in die Distro gespiegelt (`scripts/sync-to-wsl.sh`);
  Umzug auf den Thin Client später per `docker compose` + Volumes.

## D-005 – 2026-10-11 – Server: Traccar + FastAPI-Bridge (Docker Compose)

- **Entscheidung:** Traccar für Position/Geofence/Karte, FastAPI-Bridge für Audio,
  Poll-Queue und Eltern-UI; Traccar-Ereignisse per `event.forward` an die Bridge.
- **Begründung:** Traccar kann Audio nicht abbilden (keine Event-Injection);
  Bridge bleibt schlank und self-hosted.
- **Folgen:** Zwei Dienste im selben Compose-Netz; TLS/Reverse-Proxy als TODO.

## D-004 – 2026-10-11 – Kein Find-My-Beacon im Prototyp *(überholt durch D-009)*

- **Entscheidung:** Apple/Google-Find-My nicht implementieren.
- **Begründung:** Google FMD für DIY nicht offen; Apple/OpenHaystack seit 2025
  unzuverlässig; Deep-Sleep-Advertising unmöglich (Kosten/Nutzen).
- **Folgen:** Optional später separater Always-on-Beacon-Chip (z. B. ST17H66).
- **Nachtrag 2026-10-11:** Durch D-009 überholt – Find My wird als optionales
  Compose-Profil aufgenommen (Apple + Google), weiterhin experimentell.

## D-003 – 2026-10-11 – Downlink per Polling, kein SMS-Wake

- **Entscheidung:** Nachrichten und Suchmodus werden vom Tracker gepollt
  (Standard 15 min, Suchmodus 30–60 s). SMS nur nach erfolgreichem Test (M4).
- **Begründung:** Im PSM ist SMS nicht zeitnah zustellbar; LilyGO deklariert SMS
  für dieses Board als nicht unterstützt; Traccar-Commands erreichen OsmAnd-Geräte nicht.
- **Folgen:** Latenz der Eltern→Kind-Nachrichten hängt am Poll-Intervall;
  Suchmodus begrenzt zeitlich (Akku).

## D-002 – 2026-10-11 – Audioformat 8 kHz / 16 Bit / IMA-ADPCM

- **Entscheidung:** Abtastrate 8 kHz, ADPCM ⇒ 4 kB/s, 10 s ≈ 40 kB.
- **Begründung:** Bandpass 300–3400 Hz entspricht dem Telefonband; halbiert
  Datenmenge/Uploadzeit gegenüber 16 kHz; die ursprünglichen Zahlen (4 kB/s bei
  16 kHz, 15–25 kB/10 s) waren rechnerisch falsch.
- **Folgen:** Bridge konvertiert per ffmpeg in beide Richtungen.

## D-001 – 2026-10-11 – Board: T-SIM7080G-S3 V1.0 (bestellt) bleibt im Einsatz

- **Entscheidung:** Mit der gelieferten V1.0 arbeiten; Pinplan anpassen
  (siehe `docs/pinout.md`), Ruhestrom- und Bauformkompromisse akzeptieren.
- **Begründung:** Bereits bestellt; Vorteile: AXP2101 (Akkumessung, 1 A Laden),
  18650-Option, gute Dokumentation. Die „Standard“-Edition wäre stromsparender,
  ist aber nicht verfügbar.
- **Folgen:** Ruhestrom ~0,4–1,1 mA statt < 50 µA; Gehäuse größer; bei einer
  späteren Serienversion Boardwechsel evaluieren.
