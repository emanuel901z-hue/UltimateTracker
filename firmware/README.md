# Firmware (ESP32-S3, PlatformIO)

Status: **Skelett** – die Hardware ist noch nicht geliefert. Die Struktur, die
Pin-Definitionen und die Wake-Logik sind angelegt; Audio-, Modem- und GNSS-Code
folgen nach der Inbetriebnahme (Messplan: `../docs/measurement-plan.md`).

## Bauen & Flashen

```bash
cd firmware
pio run                 # bauen
pio run -t upload       # flashen (USB-C am Board)
pio device monitor      # serielle Ausgabe (115200)
```

### Flash-Hinweise

- **USB-C** am Board = ESP32-S3 (Programmieren + Monitor).
  **Micro-USB** = nur SIM7080G-Firmware-Update (für unser Projekt nicht nötig,
  ggf. SIMCom-Treiber erforderlich).
- **Keine zusätzliche Flash-Software nötig:** `esptool` ist in PlatformIO enthalten.
  Falls doch gewünscht: `pip install esptool`, Adressen/Optionen siehe
  `pio run -t upload -v`.
- Windows-Treiber: Der native USB-CDC des ESP32-S3 funktioniert unter Win 10/11
  ohne Zusatztreiber.
- Upload schlägt fehl? BOOT halten → RST drücken → RST loslassen → BOOT loslassen;
  danach erscheint der Port und `pio run -t upload` läuft durch.

Board: `T-SIM7080G-S3 V1.0` (ESP32-S3-WROOM-1 **N16R8**). In `platformio.ini`
ist `esp32-s3-devkitc-1` mit QIO-Flash und OPI-PSRAM konfiguriert.

> **Wichtig:** Die Platform `espressif32@6.13.0` liefert Arduino-Core 2.x
> (ESP-IDF 4.4) – dort existiert der **neue** I2S-Treiber (`esp_driver_i2s`,
> Full-Duplex) noch nicht. Für die Audio-Pipeline entweder den Legacy-Treiber
> nutzen oder auf den pioarduino-Fork (Arduino-Core 3.x) wechseln; Hinweis
> steht in `platformio.ini`.
>
> Stand 2026-10-11: Das Skelett kompiliert (SUCCESS, ~4 % Flash), ist aber noch
> nicht auf Hardware geflasht.

## Aufbau

| Pfad | Inhalt |
|---|---|
| `include/pins.h` | Verbindliche Pin-Belegung (Quelle: `docs/pinout.md`) |
| `include/config.h` | Tunables (Poll-Intervalle, Wake-Drossel **3 min**, Lautstärke, Modem-Modus) |
| `src/main.cpp` | Einstiegspunkt, Wake-Logik-Skelett, TODOs |
| `lib/tracker_core/` | **Plattformunabhängige Logik** (kein Arduino): IMA-ADPCM-Codec, Sync-Protokoll, Wake-/Poll-Policy, AGC, Ereignis-Ringpuffer |
| `test/` | Host-Tests dieser Logik (Unity, `pio test -e native`) |

## Tests (ohne Hardware)

```bash
pio test -e native      # braucht gcc/g++ auf dem Host
# Unter Windows ohne MinGW in der WSL oder in der CI:
wsl -d UltimateTracker -- bash -lc 'cd ~/UltimateTracker/firmware && pio test -e native'
```

Aktuell: **23 Tests** (ADPCM-Round-Trip inkl. SNR-Prüfung, Protokoll-Bauen/Parsen
gegen das echte Bridge-Format, Wake-Drossel, Poll-Grenzen, AGC, Ringpuffer).
Details: `../docs/simulation.md`.

## Nächste Schritte (nach Hardware-Lieferung)

1. M1: Deep-Sleep-Strom messen (LEDs/PSRAM/Rails prüfen).
2. M2: I2S-Full-Duplex-Pipeline (INMP441 → ADPCM → MAX98357A).
3. Modem: TinyGSM + `AT+SGPIO=0,5,1,1` (GNSS-Antenne), GNSS→LTE-Sequenz.
4. PMU: TS-Pin-Detection deaktivieren, Akkustand lesen.
5. LIS3DH: Schwellwert-Interrupt konfigurieren, EXT1-Wake testen.

## Referenzen

- LilyGO-Beispiele: <https://github.com/Xinyuan-LilyGO/LilyGo-T-SIM7080G>
  (u. a. `MinimalDeepSleepExample`, `MinimalModemAndEspSleep`, `MinimalModemGPSExample`)
- TinyGSM: <https://github.com/vshymanskyy/TinyGSM>
- ESP-IDF I2S (Full-Duplex): <https://docs.espressif.com/projects/esp-idf/en/v5.3.4/esp32s3/api-reference/peripherals/i2s.html>
