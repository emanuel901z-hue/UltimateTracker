# Entscheidungsprotokoll (ADR-Kurzform)

Neue Einträge oben ergänzen. Format: Datum – Entscheidung – Begründung – Folgen.

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
  (README, Doku, .gitignore); Lizenz noch offen.
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
