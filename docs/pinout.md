# GPIO-Belegung – LilyGO T-SIM7080G-S3 V1.0

**Verbindlich** für Firmware (`firmware/include/pins.h`), Verdrahtung und CAD.
Grundlage: LilyGO-Repository `LilyGo-T-SIM7080G`, Header-Beschriftung des bestellten
Boards (Fotos), ESP32-S3-Datasheet. Prüfbericht: `docs/hardware-review.md`.

## 1. Reservierte Pins (nicht verwenden!)

| GPIO | Funktion auf dem Board | Anmerkung |
|---|---|---|
| 4 | Modem RXD (UART) | am Header als „RXD“ beschriftet |
| 5 | Modem TXD (UART) | am Header als „TXD“ beschriftet |
| 6 | PMU IRQ (AXP2101) | |
| 7 | PMU I2C SCL | AXP2101-Adresse 0x34 |
| 15 | PMU I2C SDA | |
| 35 / 36 / 37 | Octal-SPI-PSRAM | am Header, aber **nicht nutzbar** (N16R8) |
| 41 | Modem PWRKEY | |
| 42 | Modem DTR | Sleep-Steuerung des Modems |
| 46 | Board-PWRKEY | |
| 3 | Modem RI | **nur als Eingang**; Reserve für optionalen Wake |
| 38 / 39 / 40 | TF-Kartenslot | nur nutzbar, wenn Slot dauerhaft leer – nicht empfohlen |

## 2. Belegung (verbindlich)

| Funktion | GPIO | Richtung | Anmerkung |
|---|---|---|---|
| I2C SDA (LIS3DH) | **1** | I/O | Kamera-I2C, Pull-ups vorhanden |
| I2C SCL (LIS3DH) | **2** | I/O | dito; falls IO2 nicht am Header: IO10/IO11 verwenden |
| LIS3DH INT1 (Wake) | **14** | IN | RTC-GPIO, Deep-Sleep-Wake (EXT1) |
| PTT-Taster (Wake) | **9** | IN | RTC-GPIO; **externer 100-kΩ-Pull-up zwingend** (interne Pull-ups sind im Deep Sleep aus, siehe `docs/esp32s3.md`) + 100 nF gegen GND |
| I2S BCLK (Mic + Amp) | **16** | OUT | geteilte Clock, Full-Duplex |
| I2S WS/LRC (Mic + Amp) | **17** | OUT | dito |
| I2S DIN → MAX98357A | **47** | OUT | |
| I2S Mic-SD ← INMP441 | **48** | IN | |
| MAX98357A SD | **21** | OUT | HIGH = aktiv (Left-Channel) |
| Mikrofon-Load-Switch | **10** | OUT | P-MOSFET oder PMU-Rail (ALDO2/ALDO4) |
| Piezo A | **11** | OUT | LEDC-Kanal, gegenphasig zu B |
| Piezo B | **13** | OUT | LEDC-Kanal, gegenphasig zu A |
| Reserve | 12, 18, 45, 46 | – | 45/46 sind Strapping-Pins (nur nach dem Boot nutzen) |

## 3. RTC-Fähigkeit (Deep-Sleep-Wake)

Nur GPIO **0–21** sind RTC-GPIOs. Für Wake genutzt: **9** (PTT), **14** (LIS3DH),
optional **3** (Modem-RI, nur bei registriertem Modem sinnvoll).

## 4. PMU (AXP2101)

- I2C: SDA **15** / SCL **7** (belegt), IRQ **6** (belegt) – Adresse `0x34`.
- **Zwei getrennte Busse:** PMU hängt an **GPIO 15/7**, unsere Sensoren an **1/2**.
  Im Arduino-Code deshalb `Wire` (PMU) und `Wire1` (Sensoren) verwenden –
  ein einzelner `Wire` kann nur eine Pin-Belegung gleichzeitig.
- Akkustand **über den PMU** lesen (kein ADC-Pin für die Batterie vorhanden).
- **TS-Pin-Detection in der Firmware deaktivieren** (kein NTC auf dem Board),
  sonst wird das Laden gesperrt.
- Ladestrom max. 1 A (Standardwert prüfen); Rail-Nutzung für das Mikrofon
  (ALDO2/ALDO4) ist eine Option ohne zusätzlichen MOSFET.
- Verifiziert (2026-10-12): PMU antwortet auf `0x34`, alle Rails der Werksfirmware
  sichtbar; **DC3 = Modem/GPS-Rail ist per PMU schaltbar** (B1-Variante 3).

## 5. Varianten-Hinweis: T-SIM7080G-S3-**Standard** (NR16R2)

Falls später auf die Standard-Edition gewechselt wird (kleiner, ~128 µA Deep Sleep),
gilt ein **anderes** Pinout. Kernpunkte:

| Funktion | Standard-Edition |
|---|---|
| Modem UART / RING / DTR / PWRKEY | 4 / 5 / 6 / 7 / 46 |
| Dedizierter I2C (QWIIC, nur I2C nutzbar) | SDA 3, SCL 2 |
| Solar-ADC | 18 (Spannungsteiler – nicht als GPIO nutzen) |
| Kamera-Pins (frei ohne Kamera) | 1, 9, 14, 15, 16, 21, 35, 36, 37, 38, 39, 40, 41, 47 |
| PSRAM-Sperre | keine (Quad-PSRAM), 33–37 nutzbar |
| PMU | kein AXP2101; 3,3 V-Rail, Lade-IC |

## 6. Änderungsregel

Diese Datei ist die Quelle der Wahrheit. Änderungen hier eintragen und danach
`firmware/include/pins.h` sowie `project.md` (Abschnitt 2) nachziehen.
