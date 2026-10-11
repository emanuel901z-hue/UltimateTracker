# ESP32-S3-Eigenheiten (Firmware & Debugging)

Was auf dem ESP32-S3 anders ist als auf dem „klassischen“ ESP32 – jeweils mit
Bezug auf unser Board (ESP32-S3-WROOM-1 **N16R8**, LilyGO T-SIM7080G-S3 V1.0).
Quellen am Ende. Geprüft am 2026-10-11.

## 1. Deep-Sleep-Wake nur über RTC-GPIOs 0–21

`EXT0`/`EXT1`-Wake funktioniert ausschließlich mit RTC-GPIOs. Auf dem S3 sind das
**GPIO 0–21** (nicht wie beim ESP32 alle Pins). Unsere Wake-Pins liegen alle im
Bereich: PTT = **9**, LIS3DH-INT1 = **14**, Modem-RI = **3** (Reserve).
Nicht-RTC-Pins (z. B. 47/48) sind für I2S/Daten okay, aber **nicht** als Wake-Quelle.

## 2. Interne Pull-ups/-downs sind im Deep Sleep AUS ⚠

Ist die RTC-Peripherie-Domain im Sleep abgeschaltet (Standard), werden interne
Pull-up/-down-Widerstände **deaktiviert**. Konsequenz für uns:

- Der **PTT-Taster braucht zwingend einen externen 100-kΩ-Pull-up** (nicht nur
  „empfohlen“) – sonst floatet der Pin und erzeugt Fehl-Wakes.
- Der LIS3DH treibt INT1 aktiv (Push-Pull) → kein Pull-up nötig.
- Alternative (kostet wenige µA): RTC-Domain an lassen
  (`esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_PERIPH, ESP_PD_OPTION_ON)`) – dann
  funktionieren interne Pull-ups auch im Sleep. Für uns unnötig, der externe
  Widerstand ist billiger.

## 3. EXT1-Wake funktioniert auch bei abgeschalteter RTC-Domain

Anders als `EXT0` braucht `EXT1` die RTC-Domain **nicht** – ESP-IDF „hält“ den
Pegel der Wake-Pins beim Einschlafen automatisch. Wichtig:

- Nach einem **Deep-Sleep**-Wake sind die Pads automatisch wieder nutzbar.
- Nach einem **Light-Sleep** muss `rtc_gpio_hold_dis()` aufgerufen werden.
- Bekanntes Detail: Seit IDF 5.1.6 wird der EXT1-Pin intern hochgezogen (Regression);
  bei uns unkritisch, weil der Taster ohnehin gegen GND schaltet und extern
  hochgezogen ist.

## 4. USB-CDC beim Boot: im Akkubetrieb zwingend AUS ⚠⚠

Mit `-DARDUINO_USB_CDC_ON_BOOT=1` wartet der ESP32-S3 beim Start auf einen
USB-Host: **Am Akku/Powerbank startet die Firmware dann nicht** (bekanntes,
vielfach gemeldetes Verhalten; LilyGO weist für seine S3-Boards extra darauf hin).

Umsetzung bei uns: **zwei Umgebungen** in `platformio.ini`

| Env | CDC | Zweck |
|---|---|---|
| `tsim7080g-s3` (Default) | **aus** (`UT_DEBUG_SERIAL=0`) | Akkubetrieb/Release |
| `tsim7080g-s3-dev` | an (`UT_DEBUG_SERIAL=1`) | Entwicklung am USB |

Zusätzlich: `Serial.flush()` **blockiert** auf dem S3 – in der Firmware wird es
nicht verwendet (nur `printf` hinter `LOGF`, im Release wegkompiliert).

## 5. Strapping-Pins: 0, 3, 45, 46

- **GPIO 3** ist unser I2C-SDA – vom Board so vorgesehen und per Pull-up hoch
  gehalten, also unkritisch (Strapping wirkt nur beim Boot).
- **GPIO 45/46** bleiben Reserve und werden für nichts Boot-kritisches benutzt.
- **GPIO 0** (BOOT-Taster) nicht belegen.

## 6. Kein DAC

Der S3 hat **keinen** internen DAC (der klassische ESP32 hatte zwei). Audio-Ausgabe
läuft ausschließlich über **I2S** → bei uns der MAX98357A. (Deshalb ist der
ursprüngliche Piezo-Plan über zwei GPIOs + LEDC auch der richtige Weg.)

## 7. Octal-PSRAM (N16R8): Konfiguration und Deep-Sleep-Strom

- Der S3-WROOM-1 **N16R8** hat 16 MB QIO-Flash und **8 MB OPI-PSRAM** → in
  PlatformIO zwingend `board_build.arduino.memory_type = qio_opi` (falsche
  Einstellung = kein Boot bzw. kein PSRAM).
- Der Octal-PSRAM ist ein wesentlicher Anteil am **Deep-Sleep-Strom**: LilyGO
  nennt ~0,36–1,1 mA für dieses Board (vs. ~128 µA bei der Standard-Version mit
  Quad-PSRAM). ⇒ Messung M1; wenn der PSRAM nichts beiträgt, im Release-Build
  überdenken (unsere Puffer passen in den internen SRAM: 10 s Roh-Audio = 160 kB
  von 512 kB, ADPCM nur 40 kB).
- `GPIO 35–37` sind beim N16R8 durch den PSRAM belegt (siehe `docs/pinout.md`).

## 8. RTC-Speicher (16 KB) für Zustand über Deep Sleep

Deep Sleep ist im Arduino-Framework ein **kompletter Neustart** – nur
`RTC_DATA_ATTR`-Variablen (RTC-Slow-Memory, 16 KB) überleben. Bei uns liegt dort
der **Ereignis-Ringpuffer** (`g_log` in `src/main.cpp`); bei Kaltstart wird er
explizit geleert, weil der Speicher dann nicht vertrauenswürdig ist.
Alles andere (Konfiguration, Positionen, Upload-Queue) gehört ins **NVS**.

## 9. Native USB auf GPIO 19/20

Der USB-C-Anschluss des Boards hängt am nativen USB des S3 (GPIO 19/20) – diese
Pins sind für uns tabu (siehe `docs/pinout.md`). Der zweite USB-Port (Micro-USB)
geht zum SIM7080G.

## 10. ADC, LEDC, I2S

- **ADC1 = GPIO 1–10**; ADC2 wird von WLAN belegt. Wir messen den Akku ohnehin
  über den PMU (I2C) → kein ADC-Konflikt.
- **LEDC** (Piezo-PWM) ist auf dem S3 auf jedem GPIO möglich.
- **I2S**: zwei Controller; Full-Duplex (geteilte BCLK/WS) auf einem Port möglich
  – der *neue* Treiber dafür braucht Arduino-Core 3.x (siehe unten).

## 11. Arduino-Core 2.x vs. 3.x

`espressif32@6.13.0` liefert Core 2.x (ESP-IDF 4.4): S3 wird voll unterstützt,
aber nur der **Legacy-I2S-Treiber**. Der neue `esp_driver_i2s` (Full-Duplex,
sauberere API) kommt mit Core 3.x (pioarduino-Fork) – Entscheidung fällt bei der
Audio-Implementierung (`docs/optimizations.md` B10).

## 12. Emulation: was QEMU/Wokwi beim S3 abdecken (korrigiert)

| Emuliert (ESP32-S3 in Espressif-QEMU) | **Nicht** emuliert |
|---|---|
| CPU (Dual-Core), UART, Interrupt-Matrix, GPIO-Strapping | **WLAN**, Bluetooth, USB |
| NOR-Flash-SPI + MMU, Flash-Verschlüsselung | **I2C**, **I2S**, RMT, GP-SPI, GPIO-Matrix/IOMUX |
| **PSRAM QPI/OPI (2–32 MB)**, eFuse, RNG, GDMA | ADC/DAC, Touch, MCPWM, ULP |
| AES/SHA/RSA/HMAC/DS, SysTimer, Timer-Gruppen, TWAI/CAN | **LEDC** (beim S3 nicht emuliert), SD/MMC |
| **Ethernet (OpenCores) für Netzwerk**, RGB-Framebuffer | – |

Konsequenz: QEMU kann **Boot, NVS, Partitionen, OTA-Abläufe und (über das
emulierte Ethernet) HTTP** testen – aber **kein** I2S-Audio, keine I2C-Peripherie
(PMU, LIS3DH), keinen Piezo und kein LTE/GNSS. Deshalb bleibt der Weg:
reine Logik auf dem Host (`firmware/lib/tracker_core`, 23 Tests) + Modem-Mock;
QEMU für OTA-/Partitions-Flows. Details: `docs/simulation.md`.

## Quellen

- Sleep Modes (ESP32-S3) – <https://docs.espressif.com/projects/esp-idf/en/v5.3/esp32s3/api-reference/system/sleep_modes.html>
- QEMU-Feature-Matrix – <https://github.com/espressif/esp-toolchain-docs/blob/main/qemu/README.md>
- QEMU für ESP32-S3 – <https://github.com/espressif/esp-toolchain-docs/blob/main/qemu/esp32s3/README.md>
- USB-CDC-Bootproblem – <https://github.com/espressif/arduino-esp32/issues/8238>
- LilyGO-Hinweis (S3 + CDC) – <https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series/issues/163>
- LilyGO T-SIM7080G README (PSRAM, Deep Sleep) – <https://github.com/Xinyuan-LilyGO/LilyGo-T-SIM7080G>
