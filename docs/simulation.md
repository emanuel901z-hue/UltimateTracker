# Simulation & Tests ohne Hardware

**Frage:** Lässt sich der Mikrocontroller (oder „die andere Hardware“) virtualisieren?
**Antwort:** teilweise – und der größte Nutzen kommt gar nicht aus der MCU-Emulation,
sondern aus drei pragmatischen Bausteinen, die sofort funktionieren.

## 1. Was geht – und was nicht

| Ansatz | Deckt ab | Deckt **nicht** ab |
|---|---|---|
| **QEMU** (Espressif-Fork) | CPU/RAM/Flash, UART, Timer, NVS, Partitionen/OTA-Abläufe, Panic-Handling, teils WLAN (virtuelles Netdev) | I2S-Audio, LTE-Modem, GNSS, echte BLE-Peripherie |
| **Wokwi** (Online-Simulator) | ESP32/S3-Boards, Buttons, einige I2C-Sensoren, Displays | I2S-Mikrofon/Verstärker, SIM7080G, GNSS |
| **Renode** | v. a. andere Architekturen; ESP32-S3-Support unvollständig | s. o. |
| **Host-native Tests** (PlatformIO `native` + Unity) | **reine Logik**: ADPCM-Codec, Protokoll-JSON, Zustandsmaschine, Config/NVS-Abstraktion | alles Hardwarenahe |
| **Modem-Mock** (Interface + aufgezeichnete AT-Transkripte) | kompletter Wake-Zyklus gegen simulierte Modemantworten | echte Funk-/Netzbedingungen |
| **Tracker-Simulator** (Python) | **gesamter Server-Stack** end-to-end | Firmware-Verhalten |

## 2. Empfohlene Reihenfolge (Nutzen/Aufwand)

1. **Tracker-Simulator** – `scripts/simulate-tracker.py` spielt den Tracker gegen
   den echten Stack (Sync, Audio-Upload, Poll, Suchmodus, Positionsmeldung).
   Sofort nutzbar; testet die Server-Seite vollständig.
2. **Host-native Unit-Tests** (`pio test -e native`) für reine Logik: ADPCM
   Round-Trip, Protokoll-Parsing, Zustandsübergänge – läuft in Sekunden.
3. **Modem-Mock:** `IModem`-Interface mit TinyGSM-Implementierung **und** Mock
   (skriptbasierte AT-Antworten) → Wake-Zyklus auf Host/QEMU testbar.
4. **QEMU** für OTA-/Partitions-/NVS-Abläufe (sinnvoll ab B7/OTA).
5. **Günstiges ESP32-S3-Devkit** (5–10 €, z. B. ESP32-S3-DevKitC-1) als
   Hardware-Ersatz für I2S-/BLE-/PMU-Experimente **jetzt**: Der Firmware-Code ist
   nahezu identisch, nur das Modem ist beim LilyGO-Board anders verdrahtet.
6. **Wokwi** nur für schnelle Sensor-/UI-Spielereien – für dieses Projekt wenig Mehrwert.

## 3. Grenzen

- **I2S-Audio und Funk (LTE/GNSS) sind nicht sinnvoll simulierbar** – dafür braucht
  es Hardware (Messungen M2/M3).
- Emulation ersetzt **keine Strommessung** (M1) – kein Simulator liefert µA-Werte.
- Ein Simulator kann Protokoll-/Logikfehler finden, aber keine Antennen-, EMV- oder
  Thermikprobleme.

## 4. Konkret vorhanden

| Werkzeug | Pfad | Zweck |
|---|---|---|
| Tracker-Simulator | `scripts/simulate-tracker.py` | Server-Stack ohne Hardware testen |
| Smoke-Test | `scripts/smoke-test.sh` | API-/Stack-Regression |
| Echo-Server | `scripts/dev-echo-server.py` | Benachrichtigungen/Webhooks lokal prüfen |
| CI | `.github/workflows/ci.yml` | Compose-Config, Bridge-Compile, Firmware-Build, Smoke-Test |
