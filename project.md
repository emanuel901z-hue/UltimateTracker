# Projektübersicht: Autarker Kinder-Wearable-Tracker mit Zwei-Wege-Audio (PTT)

Dieses Dokument fasst Hardwarekomponenten, elektrische Verdrahtung, das Zusammenspiel
der Teilsysteme sowie die Software- und Serverarchitektur für den Prototypenaufbau
zusammen. Details stehen in `docs/`; alle kritischen Annahmen wurden gegen die
Herstellerdokumentation geprüft (siehe `docs/hardware-review.md`).

> **Status (2026-10-12):** Board ist da und verifiziert (LilyGO **T-SIM7080G-S3 V1.0**,
> N16R8 bestätigt, PMU/WLAN/BLE/Modem-AT getestet – `docs/bring-up.md`).
> Der Docker-Stack läuft vollständig: Traccar, Audio-Bridge mit Eltern-UI
> (Login, Mehrkind-Betrieb, Monitoring, Einstellungen, Backup), PostgreSQL, TLS,
> SIM-Provider-Schicht. Firmware: Logik vollständig und host-getestet (53 Tests),
> Hardware-Anbindung (Modem-HTTP, I2S, PMU) folgt in der Inbetriebnahme.
> Messplan: `docs/measurement-plan.md`.

## 1. Hardware- & Materialstückliste

### 1.1 Kern-Elektronik & Energie

| Komponente | Details | Hinweis |
|---|---|---|
| Haupt-Recheneinheit & Funk | LilyGO **T-SIM7080G-S3 V1.0** (ESP32-S3-WROOM-1 **N16R8**: 16 MB Flash, 8 MB Octal-PSRAM; SIM7080G für LTE-M/NB-IoT; GNSS; AXP2101-PMU) | 111 × 32 × 20 mm, 26 g; GPIO 35–37 durch Octal-PSRAM gesperrt |
| SIM-Karte | 1NCE IoT Flat (500 MB, 250 SMS, 10 Jahre) | SMS-Funktion auf diesem Board noch unbestätigt (Abschnitt 3.4) |
| Stromversorgung | LiPo 103450 (3,7 V nominal, 2.000 mAh, 10,0 mm dick) mit PCM-Schutzschaltung | Alternativ: flat-top 18650 im Board-Halter (mehr Kapazität, aber ~22–24 mm Bauhöhe) |
| Antennen | LTE-FPC-Antenne + **aktive** GNSS-Antenne (3,3 V, Patch ~25 × 25 mm) | ⚠ Nicht in der ursprünglichen BOM – prüfen, was LilyGO mitliefert |
| Stützkondensator | 470 µF Low-ESR + 100 nF an den BAT-Pads | Für LTE-Sendespitzen (2× 28 AWG Leitung) |

### 1.2 Audio-, Sensor- & Bedienelemente

| Komponente | Details | Hinweis |
|---|---|---|
| Digitales Mikrofon (Audio In) | INMP441 I2S-MEMS-Mikrofonmodul | Stromaufnahme ~1–2 mA → **Load-Switch erforderlich** (siehe unten) |
| Mikrofon-Load-Switch | P-Kanal-MOSFET **oder** freie PMU-Rail (ALDO2/ALDO4, per I2C schaltbar) | Fehlte in der ursprünglichen BOM; ohne Schalter zieht das Mikrofon dauerhaft Strom |
| Audio-Verstärker (Audio Out) | MAX98357A I2S-Mono-Class-D-Breakout (SD-Pin) | SD = HIGH ⇒ Left-Channel (passt zu INMP441 L/R = GND); Breakout-Variante prüfen |
| Lautsprecher | 1510-Flachlautsprecher (15 × 10 × 3,0 mm, 8 Ω, 1 W) | Ausgänge sind BTL – **nie** eine Seite gegen GND legen |
| PTT-Bedienelement | PBS-110 Drucktaster (Momentary, 7 mm) | Externer 100-kΩ-Pull-up + 100 nF gegen GND |
| Akustischer Such-Alarm | Passiver 9-mm-Piezo (Resonanz ~4 kHz) | BTL-Gegentakt über LEDC; ~75–85 dB (kein „lauter Alarm“) |
| Bewegungssensor | LIS3DH (I2C, Schwellwert-Interrupt-Wakeup) | ~2 µA im Low-Power-Modus |

### 1.3 Montage-, Schutz- & Verbindungsmaterial

- **Verkabelung:** Fermerry 28 AWG Silikonlitze (6 Farben), temperaturbeständig.
- **Elektronikkleber:** T-8000 (säurefrei, zähelastisch, Feindosiernadel).
- **Schutzmembran & Dichtungen:** hydrophobes Lautsprecher-Mesh (15 × 4 mm) für Mikrofon und Lautsprecher, Silikonkappen für beide USB-Ports (USB-C = Laden/Programmieren, Micro-USB = Modem-Firmware).
- **Gehäuse:** TPU-3D-Druck. **Korrigierte Zielhöhe: ~20–22 mm** (Board mit Stiftleisten + 10-mm-Akku; 14–16 mm sind mit diesem Board nicht erreichbar, siehe `docs/hardware-review.md`). Servicefreundlich verschrauben statt verkleben (Akkuwechsel).

## 2. Elektrische Verdrahtung & GPIO-Belegung

> Verbindliche Fassung: [`docs/pinout.md`](docs/pinout.md).
> Die ursprüngliche Belegung aus der Planungsphase war an 5 Stellen nicht mit dem
> Board vereinbar (GPIO 4, 5, 6, 7, 15 sind Modem-UART bzw. PMU) und wurde ersetzt.

### 2.1 Reservierte Pins (nicht verwenden)

| GPIO | Funktion auf dem Board |
|---|---|
| 4 / 5 | Modem RXD / TXD (UART) |
| 6 / 7 / 15 | PMU IRQ / PMU I2C SCL / PMU I2C SDA (AXP2101) |
| 35 / 36 / 37 | Octal-SPI-PSRAM (nicht nutzbar) |
| 41 / 42 | Modem PWRKEY / Modem DTR |
| 46 | Board-PWRKEY |
| 3 | Modem RI – **nur als Eingang** nutzen (Reserve für optionalen Wake) |
| 38 / 39 / 40 | TF-Kartenslot (nicht empfohlen) |

### 2.2 Verbindliche Belegung

| Komponente | Pin am Modul | ESP32-S3 Pin | Signaltyp / Bemerkung |
|---|---|---|---|
| I2S gemeinsam | BCLK / SCK | GPIO 16 | Bit-Clock (geteilt Mic + Amp, Full-Duplex) |
| | LRC / WS | GPIO 17 | Word Select / Frame Sync (geteilt) |
| MAX98357A | DIN | GPIO 47 | I2S Data Out |
| | SD (Shutdown) | GPIO 21 | HIGH = aktiv (Left-Channel) |
| | VIN / GND | VBAT / GND | Direkt an Batteriestromkreis (2,5–5,5 V) |
| INMP441 | SD | GPIO 48 | I2S Data In |
| | L/R | GND | Linker Audiokanal |
| | VDD | Load-Switch (GPIO 10) | P-MOSFET oder PMU-Rail; im Sleep aus |
| PBS-110 (PTT) | Kontakt 1 / 2 | GPIO 9 / GND | RTC-Pin, INPUT_PULLUP, Deep-Sleep-Wakeup |
| LIS3DH | SDA / SCL | GPIO 1 / GPIO 2 | I2C (Kamera-Pins, Pull-ups vorhanden) |
| | INT1 | GPIO 14 | RTC-Pin, Schwellwert-Interrupt-Wakeup |
| | VIN / GND | 3V3 / GND | Dauerstrom (~2 µA Low-Power) |
| Piezo (9 mm) | Pin A / Pin B | GPIO 11 / GPIO 13 | LEDC-Gegentakt (6,6 V_pp, ~4 kHz) |
| LiPo-Akku | BAT+ / BAT- | JST-Stecker bzw. Lötpads | Je 2× 28 AWG parallel; **Polung vor dem Einstecken messen** |

### 2.3 Elektrische Hinweise

- **I2S Full-Duplex:** TX und RX teilen sich BCLK/WS; das ist im ESP-IDF (neuer
  `i2s`-Treiber) offiziell unterstützt. Neuen und alten I2S-Treiber nicht mischen
  („CONFLICT!“-Reboots).
- **MAX98357A:** SD direkt vom GPIO (HIGH ⇒ Left-Channel). Manche Breakouts haben
  einen Pull-up (1 MΩ ⇒ Mix-Modus) – prüfen und ggf. anpassen.
- **Piezo:** zwei LEDC-Kanäle gegenphasig, ~100 Ω in Reihe; nicht per Software togglen.
- **Akku:** Board-/Modem-Minimum 3,5 V (≈ 80 % der Nennkapazität nutzbar).
- **AXP2101:** TS-Pin-Detection in der Firmware deaktivieren, sonst lädt der Akku nicht;
  Akkustand über den PMU lesen (I2C 15/7), nicht über einen ADC-Pin.

## 3. Interaktionsmodell & Systemlogik

```
                    ┌──────────────────────────┐
                    │  Deep Sleep              │
                    │  ~0,4–1,1 mA (Board)     │
                    └────────────┬─────────────┘
                                 │
        ┌────────────────┬───────┴────────┬──────────────────┐
        ▼                ▼                ▼                  ▼
  [Bewegung]        [PTT-Taster]     [Timer-Poll]      [RI, optional]
  LIS3DH → IO14     PBS-110 → IO9    RTC-Timer         Modem-RI → IO3
        │                │                │                  │
        ▼                ▼                ▼                  ▼
  Ortungs-Pipeline  Audio-Uplink     Server-Poll       SMS-Kommando
  (sequenziell!)    (8 kHz ADPCM)    (Nachricht?       (erst nach
                                      Suchmodus?)       Verifikation)
```

### 3.1 Energie- & Ruhemanagement

- **Realistischer Ruhestrom: ~0,4–1,1 mA** (Board-Messungen LilyGO: ~0,36 mA
  Beispielmessung, 1,1 mA Wiki-Durchschnitt für N16R8). Das ursprüngliche Ziel
  „< 50 µA“ ist mit diesem Board **nicht erreichbar** (Octal-PSRAM, LEDs, PMU).
- Mikrofon und Verstärker werden im Sleep abgeschaltet (Load-Switch bzw. SD = LOW).
- Aufwecken per Bewegung: LIS3DH-INT1 an RTC-GPIO 14 (EXT1).
- Zusätzlich Timer-Wake für Server-Poll und ein optionaler RI-Wake (GPIO 3).

### 3.2 Ortung & Positions-Push

- **GNSS und LTE sind beim SIM7080G hardwarebedingt nicht gleichzeitig nutzbar**
  (gemeinsame RX-Kette; SIMCom-Hardware-Design-Doku). Der Ablauf ist daher strikt
  sequenziell: GNSS an → Fix (warm 5–15 s, kalt 30–60 s) → GNSS aus → LTE an →
  Upload → LTE aus.
- Die GNSS-Antenne ist eine **aktive** Antenne und muss per `AT+SGPIO=0,5,1,1`
  versorgt werden, sonst ist kein Fix möglich.
- Upload via LTE-M per OsmAnd-Protokoll (HTTP-GET) an Traccar; bevorzugt LTE-M
  (deutlich kürzere Latenz als NB-IoT). Akkustand wird mitgesendet (`batt`).
- Find-My-Beacons (Apple/Google) sind **optional** (Compose-Profil `findmy`,
  siehe `docs/findmy.md`): Apple über `anisette` + `macless-haystack`, Google über
  einen Community-Microservice. Positionen laufen tolerant in die Bridge
  (`/api/v1/findmy/locations`) und optional weiter an Traccar (eigenes Gerät je
  Beacon). Bleibt experimentell; der Beacon-Dauerbetrieb (Strom) ist separat zu lösen.

### 3.3 Zwei-Wege-Sprachkanal (Push-to-Talk)

- **Vom Kind zu den Eltern (Uplink):**
  - Kind drückt und hält den PBS-110; der Tracker quittiert mit einem kurzen Ton
    („Bereit“) über den 1510-Lautsprecher.
  - Aufnahme über INMP441: **8 kHz / 16 Bit Mono**, Bandpass 300–3400 Hz
    (passt exakt zur Abtastrate), Kompression IMA-ADPCM ⇒ **4 kB/s**.
  - Loslassen (oder 10 s Limit) → Doppelton; Upload als HTTP-POST.
  - Dateigröße: **10 s ≈ 40 kB** (korrigiert; die früheren Angaben 4 kB/s bzw.
    15–25 kB waren rechnerisch falsch).
- **Von den Eltern zum Kind (Downlink):**
  - Eltern sprechen über die Web-Oberfläche der Audio-Bridge eine Nachricht ein
    (Browser liefert Opus/WebM; der Server konvertiert per ffmpeg nach IMA-ADPCM-WAV).
  - Der Tracker holt Nachrichten **per Polling** beim nächsten Aufwachen ab
    (Traccar-Commands kennt das OsmAnd-Protokoll nicht; SMS-Wake ist unzuverlässig,
    siehe 3.4).
  - Wiedergabe: MAX98357A aktivieren (GPIO 21 = HIGH), Datei abspielen, danach
    Verstärker sofort wieder abschalten.
- Es bleibt **Store-and-Forward** (Sprachnachricht), kein Echtzeit-PTT –
  NB-IoT/LTE-M-Latenzen lassen nichts anderes zu.

### 3.4 Akustischer Suchalarm & Suchmodus

- Auslöser ist **kein SMS-Primärpfad**, sondern der **Suchmodus**: Eltern setzen ihn
  in der Bridge-UI oder über Traccar; der Tracker pollt dann alle 30–60 s, aktiviert
  den Piezo-Intervallton und schickt häufiger Positionen.
- Begründung: SMS ist im PSM erst beim nächsten Wake zustellbar (Minuten bis Stunden),
  und LilyGO deklariert SMS für dieses Board als nicht unterstützt. Der AT-Befehlssatz
  und Community-Berichte sprechen dafür, dass SMS grundsätzlich funktioniert –
  **erst auf dem Breadboard verifizieren**, dann ggf. als Zusatzpfad aktivieren.
- Der Modem-RI liegt auf GPIO 3 und ist als Wake-Reserve vorgesehen (nur nutzbar,
  solange das Modem registriert bleibt – kostet Ruhestrom).
- Identitäten (IMEI/MSISDN/Beacon-IDs), SMS-Pfade und die Kommando-Spezifikation:
  [`docs/sms.md`](docs/sms.md).

## 4. Software- & Server-Architektur

```
┌────────────────────────────────────────────────────────────────────────┐
│ Host: Docker-Environment (WSL-Distro „UltimateTracker“, später Thin Client) │
│                                                                        │
│  ┌───────────────────────────────┐   ┌──────────────────────────────┐  │
│  │ Traccar Server                │   │ Audio-Bridge (FastAPI)       │  │
│  │  - Port 5055 (OsmAnd API)     │◄──┼──► event.forward (JSON)      │  │
│  │  - Port 8082 (Web-Interface)  │   │  - Port 8085 (Web & API)     │  │
│  │  - Karte, Geofence, `batt`    │   │  - Upload/Download PTT       │  │
│  └───────────────────────────────┘   │  - HTML5-Web-Sprachrekorder  │  │
│                                      │  - Nachrichten-Queue (Poll)  │  │
│                                      └──────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Tracker-Firmware (ESP32-S3, PlatformIO)

- FreeRTOS-Task-Management; TinyGSM für das SIM7080G (TCP/SSL/Battery-Klasse).
- I2S mit DMA-Ringpuffern für INMP441/MAX98357A. **Achtung:** Der neue
  `esp_driver_i2s`-Treiber (Full-Duplex mit geteilter BCLK/WS) ist erst mit
  Arduino-Core 3.x (pioarduino-Fork) verfügbar; mit Core 2.x den Legacy-Treiber
  verwenden. Treiber nicht mischen („CONFLICT!“).
- GNSS über `AT+CGNSPWR` / `AT+CGNSINF` (sequenziell zu LTE, siehe 3.2).
- Software-Bandpass (300 Hz–3,4 kHz) zur Sprachvorfilterung.
- NimBLE als Reserve (z. B. Diagnose), kein Beacon-Dauerbetrieb im Prototyp.

### 4.2 Server-Dienste (Docker Compose, `server/`)

- **traccar:** Standard-Container; OsmAnd-Positionsdaten, Geofencing, Karte,
  Akkustand. Ereignis-Weiterleitung per `event.forward.url` an die Bridge.
  Geräte werden automatisch registriert (`database.registerUnknown`).
- **audio-bridge:** FastAPI/Python-Service im selben Docker-Netz. Verwaltet
  Sprach-Uploads beider Richtungen, konvertiert mit ffmpeg, stellt den Eltern eine
  HTML5-Oberfläche bereit, hält die Nachrichten-Queue für den Poll des Trackers und
  führt die **Geräte-Registry** (IMEI ↔ MSISDN ↔ Name, Auto-Registrierung).
- **Optional (Profil `findmy`, experimentell):** `anisette` + `macless-haystack`
  (Apple Find My) und die **Google-Find-Hub-WebUI** (Port 4321: Geräteverwaltung,
  Scheduling, Firmware-Build im Browser, Traccar-OsmAnd-Preset). Positionen können
  direkt an Traccar oder über `/api/v1/findmy/locations` in die Bridge laufen.
  Minimal-Alternative ohne WebUI: Profil `google-minimal` (Traccar-Fork).
  Details: [`docs/findmy.md`](docs/findmy.md).
- Hinweis: Audionachrichten lassen sich **nicht** in den Traccar-Event-Feed
  injizieren (keine API dafür). Die Bridge ist für Audio die führende Oberfläche;
  Traccar liefert Karte und Geofence-Ereignisse.

### 4.3 Schnittstellen (Überblick)

| Richtung | Methode | Endpunkt |
|---|---|---|
| Tracker → Bridge | POST | `/api/v1/device/messages` (Audio-Uplink) |
| Tracker → Bridge | GET | `/api/v1/device/pending` (Nachricht/Suchmodus abfragen) |
| Tracker ← Bridge | GET | `/api/v1/device/messages/{id}/audio` (Audio-Downlink) |
| Eltern → Bridge | POST | `/api/v1/parent/messages` (Sprachnachricht aufnehmen) |
| Eltern ← Bridge | GET | `/` (Web-UI), `/api/v1/parent/messages` (Liste) |
| Traccar → Bridge | POST | `/api/v1/traccar/events` (event.forward) |

## 5. Energiebudget (Schätzung, nachzumessen)

| Zustand | Strom / Energie | Auswirkung auf 2.000-mAh-Akku |
|---|---|---|
| Deep Sleep (Board + LIS3DH) | ~0,4–1,1 mA | 9–26 mAh/Tag |
| Modem registriert (eDRX, optional) | ~0,6 mA zusätzlich | +14 mAh/Tag |
| Ortungszyklus (GNSS + LTE + Upload) | ~1–2 mAh pro Push | 20 Pushes/Tag ≈ 30–60 mAh/Tag |
| Audio-Nachricht (10 s, 40 kB) | ~1,5–2 mAh | – |
| Server-Poll alle 15 min | ~0,5–1 mAh pro Poll | +50–100 mAh/Tag |
| Server-Poll alle 5 min (Suchmodus) | dito | +150–300 mAh/Tag |

**Erwartung: Tage bis wenige Wochen** Laufzeit (nicht Monate). LilyGO-Referenzwert:
periodischer GNSS-Upload-Zyklus ≈ 1,2 mA Durchschnittsstrom.

## 6. Sicherheit & Datenschutz

- Audio und Positionen betreffen ein Kind → **TLS und Token sind Pflicht vor dem
  Produktiveinsatz** (Reverse-Proxy mit Let's-Encrypt-Zertifikat, z. B. Caddy).
- Bridge-API: getrennte Tokens für Tracker und Eltern (`server/.env`).
- Traccar: Admin-Passwort ändern; nicht direkt ins Internet exponieren.
- SMS-Kommandos (falls später aktiviert): nur mit PIN/Nummernfilter.
- Aufbewahrungsfrist für Audiodateien definieren und automatisch löschen.
- Betrieb auf eigener Infrastruktur (kein Cloud-Anbieter) – DSGVO-freundliche Basis.

## 7. Offene Punkte & Risiken

| # | Punkt | Status / nächster Schritt |
|---|---|---|
| 1 | SMS-Funktion des SIM7080G auf diesem Board | Breadboard-Test (M4 in `docs/measurement-plan.md`) |
| 2 | Ruhestrom & Laufzeit | Messung M1/M8 nach Lieferung |
| 3 | IO2 physisch am Header verfügbar? | Beim Löten prüfen (Fallback IO10/IO11) |
| 4 | Aktive GNSS-Antenne im Gehäuse | Platz prüfen, Ausrichtung weg vom Körper |
| 5 | Akku-Polung JST-Stecker | Vor dem ersten Einstecken messen |
| 6 | PSM/TAU-Latenz der 1NCE-SIM | Messung M3/M7 |
| 7 | Gehäusemaße (Board 111 × 32 × 20 mm) | CAD nach Nachmessung |
| 8 | Lizenz für die Veröffentlichung | **MIT** (entschieden 2026-10-12, `LICENSE`) |
| 9 | Find My: Apple-Filter/Google-Experiment kann brechen | Auswertung im Stack vorbereitet; Fallback bleibt GNSS |
| 10 | SMS-Pfad (Messung M4) | Kommandos spezifiziert in `docs/sms.md`; erst nach Test aktivieren |

## 8. Implementierungs-Roadmap

1. **Elektronik-Testaufbau:** Breadboard-Verdrahtung LilyGO + INMP441 + MAX98357A +
   Taster + Piezo; I2S-Loopback (Aufnahme → ADPCM → Wiedergabe) validieren.
2. **Charakterisierung:** Messungen M1–M5 (Ruhestrom, GNSS/LTE-Umschaltung, SMS,
   Ladeverhalten) gemäß `docs/measurement-plan.md`.
3. **Server-Deployment:** Traccar + Audio-Bridge (bereits vorbereitet), End-to-End-Test
   Sprachupload vom ESP32-S3 an die Bridge.
4. **Mechanische Integration:** CAD-Gehäuse in TPU unter Berücksichtigung von
   PBS-110-Kragen, Lautsprecher-Dichtkammer, Mikrofon-Aussparung, GNSS-Antennenplatz
   und Servicezugang; Montage mit T-8000 und Schutz-Mesh.

## 9. Dokumente & Quellen

- [`docs/pinout.md`](docs/pinout.md) – verbindliche GPIO-Belegung
- [`docs/hardware-review.md`](docs/hardware-review.md) – Prüfbericht mit Quellen
- [`docs/architecture.md`](docs/architecture.md) – Architektur & Datenflüsse
- [`docs/measurement-plan.md`](docs/measurement-plan.md) – Mess- und Testplan
- [`docs/deployment.md`](docs/deployment.md) – Server-Deployment
- [`docs/findmy.md`](docs/findmy.md) – Apple/Google Find My (Gegenstücke, Setup)
- [`docs/sms.md`](docs/sms.md) – Identitäten (IMEI/MSISDN) und SMS-Pfad
- [`docs/decisions.md`](docs/decisions.md) – Entscheidungsprotokoll
