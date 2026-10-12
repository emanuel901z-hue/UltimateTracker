# Bring-up: die ersten Stunden mit der Hardware

Reihenfolge für den Tag, an dem das Board ankommt. Ziel: erst **prüfen**, dann
messen, dann entwickeln. Ablauf/Details: `docs/measurement-plan.md`,
Messprotokoll: `scripts/new-measurement-session.sh`.

## Ergebnisse des ersten Selbsttests (2026-10-12, Board nackt, ohne SIM)

| Prüfung | Ergebnis |
|---|---|
| Chip / PSRAM | **ESP32-S3, 2 Kerne, 16 MB Flash, PSRAM 8189 kB** → **N16R8 bestätigt** (qio_opi korrekt) |
| USB | COM8, `VID:PID 303A:1001` (Espressif USB-Serial/JTAG), MAC 94:a9:90:e5:0f:cc |
| **I2C PMU-Bus (Wire, 15/7)** | **AXP2101 @ 0x34 gefunden** ✓ |
| I2C Sensor-Bus (Wire1, 1/2) | 0 Geräte – korrekt, noch nichts verdrahtet |
| PMU | antwortet; **kein Akku angeschlossen** (0 mV), TS-Pin-Detection deaktiviert ✓ |
| LIS3DH | nicht gefunden – noch nicht verdrahtet ✓ |
| Modem | `AT` ✓; Modell/Firmware: `ATI` → **R1951.07**, `AT+CGMR` → **Revision:1951B17SIM7080** |
| Modem ohne SIM | `+CCID`/`+CPIN?` → ERROR, `+CSQ: 99,99`, `+CEREG: 0,2` (sucht) ✓ erwartet |
| **SMS-AT-Befehle (ohne SIM)** | **alle → ERROR** (`+CMGF`, `+CSCS`, `+CPMS?`, `+CSMS?`, `+CMGS=?`, `+CSCA?`, `+CNMI`, `+CMGL`) – ohne SIM erwartbar (SMS-Dienst braucht die SIM-Speicher), **nicht aussagekräftig** → mit SIM per `c`/`x` wiederholen |
| Modem PSM/eDRX | **`AT+CPSMS?`/`+CPSMS=?`/`+CEDRXS?`/`+CEDRXS=?` → ERROR** → mit SIM erneut prüfen (evtl. erst nach Netzregistrierung gültig) |
| GNSS | Antennen-Power ✓, GNSS an ✓, **kein Fix** (indoor) → mit Sichtverbindung wiederholen |
| WLAN | **8 Netze** (bestes -44 dBm) → **integrierte PCB-Antenne arbeitet** ✓ |
| BLE | **18 Geräte** gefunden ✓ |
| I2S-Ton / Mikrofon / Piezo / Taster | Test läuft; ohne verdrahtete Bauteile: Mikrofonpegel 0, Taster „nicht gedrückt“ ✓ erwartet |
| Werksfirmware | IDF v4.4.2, 4-MB-Partitionslayout; **Backup: `firmware/backup/factory-2026-10-12.bin`** |

**Zwei Erkenntnisse aus dem Selbsttest (beide im Code behoben):**
1. Ein zweiter PWRKEY-Puls bei bereits laufendem Modem verwirrt es → der Test
   prüft jetzt zuerst, ob `AT` antwortet.
2. Das Board hat **zwei getrennte I2C-Busse**: PMU (AXP2101) auf **15/7** (belegt)
   und unsere Sensoren auf **1/2** – im Arduino-Code `Wire` (PMU) vs. `Wire1` (Sensor).

**Nächste Schritte:** Peripherie auf dem Breadboard verdrahten (LIS3DH, INMP441,
MAX98357A, Taster, Piezo) → Selbsttest erneut → GNSS mit Sichtverbindung →
Akku anschließen und M1 messen → SIM einlegen und Modem-Teil (M3/M4) wiederholen.

## 0. Auspacken und prüfen (ohne Strom!)

| Schritt | Worauf achten |
|---|---|
| Board-Revision | Rückseite: **„T-SIM7080G V1.0"** + PMU-Chip (AXP2101) → gilt unser Pinplan (`docs/pinout.md`) |
| Lieferumfang | LTE-Antenne? **Aktive GNSS-Antenne**? (Falls nicht: nachbestellen, ohne gibt es keinen Fix) |
| SIM-Karte | **Nano-SIM** (1NCE). Wichtig: **vor** dem Einschalten einlegen (LilyGO-Vorgabe) |
| Sichtprüfung | Lötbrücken, verbogene Pins, Akku-Polster |
| IO2 am Header? | Durchgangsprüfung/Ansehen: unser I2C-SDA-Plan nutzt IO1/IO2 (Fallback: IO10/IO11) |
| Board-Maße | nachmessen (CAD-Grundlage), inkl. Höhe mit/ohne 18650-Halter |

## 1. Akku vorbereiten (noch nicht einstecken)

1. **Polung messen**: JST-Stecker des 103450-LiPo – Rot = Plus. Gegen das Board
   (Pinbelegung) prüfen. Falsch gepolt = Boardschaden.
2. Steckertyp prüfen (LilyGO liefert ein 2-Pin-Kabel mit; ggf. umcrimpen).
3. Minuspol/Pluspol am Board-Lötpad bzw. Stecker markieren.

## 2. Erstes Einschalten – nur über USB-C

1. USB-C (der obere Anschluss) an den PC, **ohne** Akku.
2. Seriellen Monitor öffnen (115200) – das Board meldet sich als USB-CDC.
3. **Bring-up-Firmware flashen** (Selbsttest, führt automatisch durch die Prüfungen):

   ```bash
   cd firmware
   pio run -e tsim7080g-s3-bringup -t upload
   pio device monitor            # 115200
   ```

   Der Selbsttest prüft der Reihe nach: Chip/PSRAM, **I2C-Bus** (LIS3DH 0x18,
   PMU 0x34), **PMU** (Akku/Spannung/TS-Pin), **LIS3DH** (WHO_AM_I + Achsen),
   **Modem** (PWRKEY, AT, CCID, CSQ, CEREG, CPSMS, CEDRXS), **GNSS** (Antenne,
   Fix bis 60 s), **I2S-Ton**, **Mikrofonpegel**, **Piezo**, **Taster**.

   Danach stehen Kommandos im Monitor bereit:

   | Taste | Wirkung |
   |---|---|
   | `r` | alle Tests erneut |
   | `m` / `g` | nur Modem / nur GNSS |
   | `t` / `i` | Ton / Mikrofonpegel |
   | `p` / `l` / `b` | Piezo / LIS3DH / Taster |
   | `s` | **Deep Sleep 60 s** – für die Strommessung M1 |
   | `h` | Hilfe |

4. Für den späteren Betrieb die normale Firmware flashen:
   `pio run -e tsim7080g-s3-dev -t upload` (Entwicklung) bzw.
   `pio run -e tsim7080g-s3 -t upload` (**Release für den Akkubetrieb** –
   bewusst ohne USB-CDC, siehe `docs/esp32s3.md`).
5. Wenn der Upload hakt: BOOT halten → RST → RST los → BOOT los, erneut flashen.

> **Merksatz:** USB-C = ESP32-S3 (Flashen/Seriell), Micro-USB = nur Modem-Firmware.

## 3. Funktionstest ohne Akku (Stromversorgung über USB)

| Test | Erwartung |
|---|---|
| Modem-AT | `AT` → `OK` (im Dev-Build per Serial-Konsole) |
| SIM erkannt | `AT+CCID` liefert die ICCID |
| Netz | `AT+CEREG?` → `0,1` (oder `0,5` Roaming) |
| GNSS | Antenne angeschlossen, `AT+SGPIO=0,5,1,1`, dann `AT+CGNSPWR=1`, `AT+CGNSINF` → Fix |
| PMU | Akkustand-Auslesung (später mit Akku) |

## 4. Akku anschließen und M1 messen

1. Board ausschalten, Akku einstecken (Polung geprüft!), Schalter auf ON.
2. **Ruhestrom messen** (M1): USB-Strommessgerät bzw. Shunt/µCurrent in der
   Akkuleitung. Erwartung laut LilyGO: 0,36–1,1 mA (N16R8 mit Octal-PSRAM).
3. Werte ins Messprotokoll. Auffällig hoch? Prüfen: LEDs, PSRAM-Anteil,
   PMU-Rails, ob das Mikrofon wirklich aus ist (Load-Switch!).

## 5. Dann der Reihe nach

M2 (I2S) → M3 (GNSS/LTE) → M4 (SMS) → M5 (Laden) → M6 (Ende-zu-Ende) →
M7 (Antennen) → M8 (48-h-Laufzeit).

Nach M1/M3 steht auch die Entscheidung für **B1 (Modem-Power-Modus)** an:
`MODEM_POWER_MODE` in `firmware/include/config.h` bzw. per Provisioning setzen.

## 6. Sicherheit (kurz)

- LiPo nie tiefentladen lagern, nicht quetschen, nicht im geschlossenen TPU-Gehäuse laden ohne Aufsicht.
- Antenne **immer** angeschlossen lassen, bevor das Modem sendet (sonst hohe Reflexionen/Erwärmung).
- Board nicht auf leitfähige Unterlagen legen (Akku + offene Pads).
- Beim Messen am Akku: Kurzschluss vermeiden, Shunt zuerst, dann einschalten.
