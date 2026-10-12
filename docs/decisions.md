# Entscheidungsprotokoll (ADR-Kurzform)

Neue Einträge oben ergänzen. Format: Datum – Entscheidung – Begründung – Folgen.

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
