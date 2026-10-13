# Simulation & Tests ohne Hardware

**Frage:** Lässt sich der Mikrocontroller (oder „die andere Hardware“) virtualisieren?
**Antwort:** teilweise – und der größte Nutzen kommt gar nicht aus der MCU-Emulation,
sondern aus drei pragmatischen Bausteinen, die sofort funktionieren.

## 1. Was geht – und was nicht

| Ansatz | Deckt ab | Deckt **nicht** ab |
|---|---|---|
| **QEMU** (Espressif-Fork) | CPU (Dual-Core), UART, Timer, NVS, Partitionen/OTA-Abläufe, Panic-Handling, **PSRAM (QPI/OPI)**, Krypto-Beschleuniger, **Netzwerk über emuliertes Ethernet** | **WLAN**/Bluetooth, USB, **I2S**, I2C, LEDC (beim S3), GPIO-Matrix, ADC/DAC, LTE-Modem, GNSS – vollständige Matrix: `docs/esp32s3.md` |
| **Wokwi** (Online-Simulator) | ESP32/S3-Boards, Buttons, einige I2C-Sensoren, Displays | I2S-Mikrofon/Verstärker, SIM7080G, GNSS |
| **Renode** | v. a. andere Architekturen; ESP32-S3-Support unvollständig | s. o. |
| **Host-native Tests** (PlatformIO `native` + Unity) | **reine Logik**: ADPCM-Codec, Protokoll-JSON, Zustandsmaschine, Config/NVS-Abstraktion | alles Hardwarenahe |
| **Modem-Mock** (Interface + aufgezeichnete AT-Transkripte) | kompletter Wake-Zyklus gegen simulierte Modemantworten | echte Funk-/Netzbedingungen |
| **Tracker-Simulator** (Python) | **gesamter Server-Stack** end-to-end | Firmware-Verhalten |

## 2. Empfohlene Reihenfolge (Nutzen/Aufwand)

1. **Tracker-Simulator** – `scripts/simulate-tracker.py` spielt den Tracker gegen
   den echten Stack (Sync, Audio-Upload, Poll, Suchmodus, Positionsmeldung).
   Sofort nutzbar; testet die Server-Seite vollständig. ✅ vorhanden
2. **Host-native Unit-Tests** (`pio test -e native`): ADPCM, Protokoll, Wake-Policy,
   AGC, Ring-Log, GNSS-Parser, Provisioning, OTA-Prüfung. ✅ 53 Tests
3. **Modem-Mock + Wake-Zyklus** (`IModem`, `MockModem`, `wake_cycle`): der komplette
   Zyklus (GNSS → Sync → Download → Schlafentscheidung) läuft ohne Hardware,
   inklusive Fehlerfällen (kein Fix, Sync 500, Download 404, kein Netz, Suchmodus). ✅
4. **QEMU** für OTA-/Partitions-/NVS-Abläufe (sinnvoll, sobald das Flash-Schreiben steht).
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
| Smoke-Test | `scripts/smoke-test.sh` | API-/Stack-Regression (**24 Gruppen**, inkl. OTA, Karte, Fusion, Apple) |
| Echo-Server | `scripts/dev-echo-server.py` | Benachrichtigungen/Webhooks lokal prüfen |
| **Bridge-Unit-Tests** | `server/audio-bridge/tests/` | **59 Tests**: Auth, Passwortregeln, Provider (1NCE/generisch), **Sensor-Fusion** |
| **Host-Tests der Firmware-Logik** | `firmware/lib/tracker_core` + `firmware/test/` | **53 Tests**: ADPCM, Protokoll, Wake-Policy, AGC, Ring-Log, GNSS, Provisioning, OTA, **Wake-Zyklus mit Modem-Mock** |
| CI | `.github/workflows/ci.yml` | Compose-Config, Bridge-Compile, Smoke-Test, Firmware-Build (beide Envs) **und** native Tests |

**Native Tests ausführen** (braucht gcc/g++ auf dem Host; unter Windows läuft es
in der WSL, in der CI auf ubuntu-latest):

```bash
wsl -d UltimateTracker -- bash -lc 'cd ~/UltimateTracker/firmware && pio test -e native'
```

Aufbau: `firmware/lib/tracker_core` enthält **plattformunabhängige** Logik
(kein Arduino-Header), `firmware/src` den Arduino-Teil. Damit ist die Logik
schnell und ohne Hardware testbar – der Modem-Mock (Punkt 3 oben) ist der
nächste Ausbauschritt.
