# Hardware-Review & Prüfbericht

Zweck: Alle kritischen Annahmen des Projekts gegen Herstellerdokumentation prüfen,
Widersprüche auflösen, Risiken dokumentieren. Stand: 2026-10-11 (vor Hardware-Lieferung).

Methode: Abgleich der Planung mit LilyGO-Repository/Wiki, Header-Beschriftung des
bestellten Boards, SIMCom-AT-/Hardware-Dokumentation, ESP-IDF-Doku, Traccar-Doku,
Adafruit-MAX98357-Doku und Community-Berichten. Quellen siehe Abschnitt 9.

## 1. Bestätigt: Es wurde die alte V1.0 bestellt

Silkscreen „T-SIM7080G V1.0“, ESP32-S3-WROOM-1 (N16R8, Octal-PSRAM), AXP2101-PMU,
18650-Halter, Kamera-FPC, TF-Slot, 2× USB (USB-C + Micro-USB), u.FL für LTE und GPS.
Maße **111 × 32 × 20 mm**, 26 g (ohne Antennen).

Konsequenzen gegenüber der „Standard“-Edition (NR16R2):

| Thema | V1.0 (bestellt) | Standard-Edition |
|---|---|---|
| Deep-Sleep-Strom | ~0,36 mA (LilyGO-Beispielmessung) bis 1,1 mA (Wiki-Avg) | ~128 µA |
| PMU | AXP2101 auf GPIO 15/7/6 | kein PMU |
| PSRAM-Sperre | GPIO 35–37 | keine |
| Bauform | 111 × 32 × 20 mm, 18650-Halter | kleiner, LiPo-JST |
| Laden | max. 1 A, TS-Pin-Detection muss deaktiviert werden | 500 mA über USB/Solar |

## 2. Kritisch: GPIO-Plan war an 5 Stellen nicht umsetzbar

| geplant (alt) | Funktion | Board V1.0 | Ergebnis |
|---|---|---|---|
| GPIO 4 | LIS3DH INT1 | Modem RXD (UART) | Kollision → auf **14** |
| GPIO 5 | Piezo A | Modem TXD (UART) | Kollision → auf **11** |
| GPIO 6 | Piezo B | PMU IRQ | Kollision → auf **13** |
| GPIO 7 | PTT-Taster | PMU I2C SCL | Kollision → auf **9** |
| GPIO 15 | I2S BCLK | PMU I2C SDA | Kollision → auf **16** |
| GPIO 16 | I2S WS | Kamera VSYNC | ok (Kamera ungenutzt) → bleibt |
| GPIO 17 | I2S DIN | Kamera HREF | ok → bleibt |
| GPIO 18 | Mic SD | Kamera RESET | ok → auf **48** (Konsistenz) |
| GPIO 21 | Amp SD | Kamera D5 | ok → bleibt |
| GPIO 1/2 | I2C | Kamera SCL/SDA | ok (ideal) → bleibt |

Zusätzlich: GPIO 3 = Modem-RI (nur Eingang), GPIO 35–37 gesperrt, 41/42/46 Modem/Board.
Verbindliche neue Belegung: `docs/pinout.md`.

## 3. Bestätigt: GNSS und LTE sind nicht gleichzeitig nutzbar

SIMCom-Hardware-Design-Dokument (SIM7070x/SIM7080G, Abschnitt 4.3.2):
„the LTE and GNSS RX chains of SIM7070x and SIM7080G share some hardware blocks,
therefore concurrent WWAN and GNSS operations are not supported.“
LilyGO formuliert es kürzer: „mutually exclusive“.

Folgen: Ortung ist strikt sequenziell (GNSS → Fix → GNSS aus → LTE an → Upload).
Kein „paralleler“ Betrieb, auch nicht mit BLE oder Wiedergabe während der Ortung.
Die aktive GNSS-Antenne muss per `AT+SGPIO=0,5,1,1` versorgt werden.

## 4. Korrigiert: Ruhestrom und Laufzeit

| Quelle | Wert |
|---|---|
| LilyGO-Beispiel `MinimalDeepSleepExample` (V1.0) | ~360 µA |
| LilyGO-Wiki, T-SIM7080G-S3 (N16R8) | ~1,1 mA (Durchschnitt) |
| SIM7080G-Modul (Datenblatt-Werte) | PSM 3,2 µA; eDRX-Sleep 0,6 mA; Idle 10 mA |
| LilyGO-Referenz GNSS-Upload-Zyklus | ~1,2 mA Durchschnitt |

Das Planungsziel **„< 50 µA“ ist nicht erreichbar**. Realistisch: 0,4–1,1 mA
Standby, Laufzeit **Tage bis wenige Wochen**. Zusätzlich: Der INMP441 zieht
~1–2 mA dauerhaft und muss über einen Load-Switch (oder eine PMU-Rail) geschaltet
werden – dieser fehlte in der ursprünglichen Stückliste.

## 5. Offen: SMS-Funktion

- Der AT-Befehlssatz der SIM7070/7080/7090-Serie enthält den kompletten
  SMS-Befehlssatz (`AT+CMGS`, `AT+CMGR`, `AT+CNMI`, …).
- TinyGSM implementiert eine SMS-Klasse für den SIM7080.
- Community-Bericht (M5Stack U137, gleicher Modemtyp): SMS senden/empfangen funktioniert.
- **Aber:** LilyGO deklariert SMS für dieses Board als ❌ und ihr `SendSMS`-Beispiel
  bricht für `TINY_GSM_MODEM_SIM7080` mit `#error` ab.
- Entscheidend für die Architektur: Im **PSM** ist das Modem nicht erreichbar –
  eine FIND-SMS würde erst beim nächsten Wake zugestellt (Minuten bis Stunden).
  RI (GPIO 3) weckt nur, solange das Modem registriert bleibt (kostet Ruhestrom).

Entscheidung: Suchalarm über **Polling/Suchmodus** (30–60 s), SMS erst nach
Breadboard-Test als optionaler Zusatzpfad.

## 6. Korrigiert: Audio-Mathematik

| Größe | Planung (falsch) | Korrekt |
|---|---|---|
| Datenrate 16 kHz IMA-ADPCM | 4 kB/s | **8 kB/s** (4 bit/Sample) |
| 10-s-Nachricht | 15–25 kB | **80 kB** (16 kHz) bzw. **40 kB** (8 kHz) |
| Abtastrate | 16 kHz + Bandpass 300–3400 Hz | **8 kHz** – passt exakt zum Bandpass |

Empfehlung (umgesetzt in Architektur/Entscheidungen): 8 kHz / 16 Bit / IMA-ADPCM
⇒ 4 kB/s, 10 s ≈ 40 kB. Upload via NB-IoT 10–30 s, via LTE-M 5–15 s ⇒ LTE-M bevorzugen.

## 7. Find My / Beacons: nicht im Prototyp

- **Google Find My Device** ist für DIY-Beacons nicht offen (nur zertifizierte
  Accessories/Finder-Network-Programm).
- **Apple Find My / OpenHaystack:** seit 2025 unzuverlässig (Apple filtert geklonte
  AirTag-Advertisements, OpenHaystack-Issue #273); macless-haystack bräuchte Apple-ID,
  2FA und einen Anisette-Docker-Dienst.
- Im Deep Sleep kann der ESP32-S3 nicht advertisen; periodisches Advertising aus
  Wake-Zyklen kostet ~1–3 mA Durchschnitt. Alternative: separater Always-on-Chip
  (z. B. ST17H66) – später.
- Wi-Fi-Scanning zur Ortung widerspricht „vollständig autark“ (Google/Mozilla-API)
  und ist stromhungrig → gestrichen.

## 8. Server: bestätigt und korrigiert

- Traccar-Ports stimmen: **5055** = OsmAnd-Protokoll, **8082** = Web-UI. `batt`
  wird im OsmAnd-Decoder unterstützt.
- Traccar kann Ereignisse per `event.forward.url` als JSON an einen Webhook senden
  (Doku „Forwarding“) → nutzen wir für die Bridge.
- **Nicht möglich:** Audionachrichten in Traccars Event-Feed „verlinken“ –
  Traccar-Events entstehen serverseitig, es gibt keine Inject-API. Die Bridge ist
  für Audio die führende UI.
- Downlink nicht über Traccar-Commands (vom OsmAnd-Protokoll nicht unterstützt),
  sondern über die Nachrichten-Queue der Bridge (Polling).
- Geräte-Registrierung: `database.registerUnknown=true` im Compose-Setup gesetzt.

## 9. Quellen

1. LilyGO T-SIM7080G (V1.0) Repository & README – <https://github.com/Xinyuan-LilyGO/LilyGo-T-SIM7080G>
2. LilyGO Wiki T-SIM7080-S3 (Produktdaten, 18650, PMU) – <https://wiki.lilygo.cc/products/t-sim-series/t-sim7080-s3/>
3. LilyGO Wiki Modellvergleich (Deep-Sleep-Ströme) – <https://wiki.lilygo.cc/products/t-sim-series/sim.html>
4. LilyGo-Modem-Series, S3-Standard-README (Pinout, GNSS/LTE-Hinweis) – <https://github.com/Xinyuan-LilyGO/LilyGo-Modem-Series/blob/main/docs/en/esp32s3/sim7080-s3-standard/README.MD>
5. SIMCom GNSS Application Note (SIM7070/7080/7090) – <https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/datasheet/unit/sim7080g/en/SIM7070_SIM7080_SIM7090%20Series_GNSS_Application%20Note_V1.02.pdf>
6. SIMCom AT Command Manual (SIM7070/7080/7090) – <https://www.tinytronics.nl/product_files/004318_SIM7070_SIM7080_SIM7090_Series_AT_Command_Manual_V1.03.pdf>
7. SIM7080G GNSS-vs-TCP-Limitierung (StackOverflow) – <https://stackoverflow.com/questions/61857667/sim7080g-module-cant-send-data-over-tcp-while-using-gnss>
8. M5Stack-Community: SMS mit SIM7080G – <https://community.m5stack.com/topic/7517/sms-using-m5core-u137-sim7080g-cat-m-nb-iot-gnss-unit/4>
9. ESP-IDF I2S-Doku (Full-Duplex) – <https://docs.espressif.com/projects/esp-idf/en/v5.3.4/esp32s3/api-reference/peripherals/i2s.html>
10. Adafruit MAX98357 (SD/Channel-Verhalten) – <https://learn.adafruit.com/adafruit-max98357-i2s-class-d-mono-amp/pinouts>
11. Traccar „Forwarding“ (event.forward) – <https://www.traccar.org/forward/>
12. OpenHaystack-Issue #273 (Apple filtert Klone) – <https://github.com/seemoo-lab/openhaystack/issues/273>
13. macless-haystack (Apple-ID + Anisette) – <https://github.com/dchristl/macless-haystack>
14. CNX Software: SIM7080G-Stromwerte (PSM/eDRX/Idle) – <https://www.cnx-software.com/2023/03/04/esp32-s3-sim7080g-board-wifi-bluetooth-nb-iot-cat-m-gps/>
15. Board-Maße/Gewicht (Händlerdaten) – <https://www.tinytronics.nl/en/development-boards/microcontroller-boards/with-telecommunication/lilygo-t-sim7080g-s3-esp32-s3-development-board-with-18650-battery-holder>

## 10. Restrisiken (nach Lieferung zu verifizieren)

1. SMS-Funktion (M4 im Messplan).
2. Ruhestrom real (M1) und Laufzeit (M8).
3. Ist GPIO 2 am Header herausgeführt? (Fallback IO10/IO11.)
4. PSM/TAU-Zeiten der 1NCE-SIM (Latenz für Suchmodus/Poll).
5. GNSS-Performance mit aktiver Antenne im Gehäuse (M7).
6. Ladeverhalten mit TS-Pin-Deaktivierung (M5).

## 11. Verifiziert am echten Board (2026-10-12)

| Prüfung | Ergebnis |
|---|---|
| Chip | ESP32-S3 (QFN56) Rev v0.2, 2 Kerne, 40 MHz Crystal, USB-Serial/JTAG |
| PSRAM | **8 MB embedded → N16R8 bestätigt** (unsere `qio_opi`-Konfiguration ist korrekt) |
| Flash | 16 MB (GigaDevice), eFuse: **quad, 3,3 V** → passt zu `flash_mode = qio` |
| MAC | `94:a9:90:e5:0f:cc` |
| PMU | AXP2101 @ **0x34 auf Wire (15/7)**; Rails aktiv: DC1 3,3 V, **DC3 3,0 V (Modem/GPS)**, DC5 3,3 V, BLDO1 1,8 V (Level-Shifter), BLDO2 3,3 V → **DC3 ist per PMU schaltbar (B1)** |
| WLAN/BLE | integrierte PCB-Antenne: **8 WLAN-Netze / 18 BLE-Geräte** ✓ |
| Modem | `AT` ✓; ohne SIM: `+CCID`/`+CPIN?` ERROR, `+CSQ: 99,99`, `+CEREG: 0,2`; **`CPSMS`/`CEDRXS` → ERROR** (mit SIM erneut prüfen) |
| GNSS | Antennen-Power + `CGNSPWR` ✓; indoor kein Fix (erwartet) |
| Werks-Firmware | IDF v4.4.2, „arduino-lib-builder", 4-MB-Partitionslayout; **Backup: `firmware/backup/factory-2026-10-12.bin`** |

Details und Rohausgaben: `docs/bring-up.md` (Abschnitt „Ergebnisse des ersten Selbsttests").
