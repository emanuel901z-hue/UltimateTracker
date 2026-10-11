// UltimateTracker – Firmware-Skelett
// Hardware: LilyGO T-SIM7080G-S3 V1.0 (ESP32-S3-WROOM-1 N16R8) + SIM7080G
// Pin-Belegung: include/pins.h (docs/pinout.md)
// ESP32-S3-Eigenheiten: docs/esp32s3.md
//
// Aufbau: Die Ablauflogik liegt in firmware/lib/tracker_core (host-testbar),
// hier steckt nur die Hardware-Glue (Modem-Serial, NVS, Sleep, Provisioning).
//
// Status: Skelett. Der Wake-Zyklus läuft über IModem/Sim7080Modem; die
// Modem-Sequenzen (HTTP-Engine) werden in der Hardware-Phase vervollständigt.

#include <Arduino.h>

#include "config.h"
#include "config_store.h"
#include "esp_attr.h"
#include "esp_sleep.h"
#include "modem_sim7080.h"
#include "nvs_config_store.h"
#include "pins.h"
#include "ring_log.h"
#include "wake_cycle.h"
#include "wake_policy.h"

#if UT_BRINGUP
#include "bringup.h"
#endif

// --- Debug-Ausgabe ---------------------------------------------------------
// Release-Build (UT_DEBUG_SERIAL=0): keine serielle Ausgabe, kein CDC-Warten.
// Achtung: Serial.flush() blockiert auf dem S3 – hier bewusst nicht verwendet.
#if UT_DEBUG_SERIAL
#define LOGF(...) Serial.printf(__VA_ARGS__)
#else
#define LOGF(...) do { } while (0)
#endif

// AT-Kanal des Modems (GPIO 4/5, docs/pinout.md)
static HardwareSerial ModemSerial(1);
static tracker::Sim7080Modem g_modem(ModemSerial);
static tracker::NvsConfigStorage g_storage;
static tracker::DeviceConfig g_config;

// Zustand, der Deep Sleep überlebt (RTC-Slow-Memory, 16 KB – docs/esp32s3.md)
RTC_DATA_ATTR tracker::RingLog g_log;
RTC_DATA_ATTR uint32_t g_uptime_offset_s;    // Summe der Uptimes vor diesem Boot
RTC_DATA_ATTR uint32_t g_last_motion_push_s; // für die 3-Minuten-Drossel (B2)
RTC_DATA_ATTR uint32_t g_reset_count;

enum class WakeReason { Cold, Motion, Ptt, Timer, ModemRi };

static tracker::WakeReason toPolicyReason(WakeReason reason) {
  switch (reason) {
    case WakeReason::Motion: return tracker::WakeReason::Motion;
    case WakeReason::Ptt: return tracker::WakeReason::Ptt;
    case WakeReason::ModemRi: return tracker::WakeReason::ModemRi;
    default: return tracker::WakeReason::Timer;
  }
}

// Monotone Uptime über Deep-Sleep-Zyklen hinweg (millis() startet sonst bei 0).
static uint32_t uptime_s() { return g_uptime_offset_s + millis() / 1000; }

static WakeReason getWakeReason() {
  esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
  if (cause == ESP_SLEEP_WAKEUP_EXT1) {
    uint64_t status = esp_sleep_get_ext1_wakeup_status();
    if (status & (1ULL << PIN_PTT_BUTTON)) return WakeReason::Ptt;
    if (status & (1ULL << PIN_LIS3DH_INT1)) return WakeReason::Motion;
    if (status & (1ULL << PIN_MODEM_RI)) return WakeReason::ModemRi;
  }
  if (cause == ESP_SLEEP_WAKEUP_TIMER) return WakeReason::Timer;
  return WakeReason::Cold;
}

// --- Provisioning über USB-Serial (B6) -------------------------------------
// Eine JSON-Zeile, z. B.:
//   {"cmd":"provision","device_id":"86…","server":"http://192.168.1.10:8085","token":"…"}
#if UT_DEBUG_SERIAL
static bool try_provision(uint32_t window_ms) {
  String line;
  const uint32_t start = millis();
  while (millis() - start < window_ms) {
    while (Serial.available()) {
      const char value = static_cast<char>(Serial.read());
      if (value == '\n') {
        if (line.startsWith("{")) {
          tracker::DeviceConfig candidate = g_config;
          std::string error;
          if (tracker::parse_provisioning_command(std::string(line.c_str()), candidate, error)) {
            candidate.valid = true;
            if (g_storage.save(candidate)) {
              g_config = candidate;
              LOGF("[UT] Provisioning OK (%s)\n", candidate.device_id);
              return true;
            }
          } else {
            LOGF("[UT] Provisioning abgelehnt: %s\n", error.c_str());
          }
        }
        line = "";
      } else if (value != '\r') {
        line += value;
      }
    }
    delay(10);
  }
  return false;
}
#endif

static void goToSleep(WakeReason reason, float battery_percent, bool search_mode) {
  const uint32_t sleep_s = tracker::next_sleep_seconds(toPolicyReason(reason), battery_percent,
                                                       search_mode, tracker::WakeSettings{});
  LOGF("[UT] Schlafe %lu s (Grund %d)\n", static_cast<unsigned long>(sleep_s),
       static_cast<int>(reason));

  // Uptime für den nächsten Boot mitnehmen (monotone Zeit über Deep Sleep)
  g_uptime_offset_s = uptime_s();

  // EXT1-Wake für LIS3DH-INT1 und PTT.
  // S3-Eigenheit: interne Pull-ups sind im Deep Sleep AUS → der Taster braucht
  // zwingend den externen 100k-Pull-up (docs/esp32s3.md).
  esp_sleep_enable_ext1_wakeup((1ULL << PIN_LIS3DH_INT1) | (1ULL << PIN_PTT_BUTTON),
                               ESP_EXT1_WAKEUP_ANY_LOW);
  esp_sleep_enable_timer_wakeup(static_cast<uint64_t>(sleep_s) * 1000000ULL);
  esp_deep_sleep_start();
}

void setup() {
#if UT_DEBUG_SERIAL
  Serial.begin(115200);
  delay(200);
#endif

#if UT_BRINGUP
  // Bring-up/Selbsttest: prüft Hardware und bietet eine Kommando-Konsole.
  pinMode(PIN_AMP_SD, OUTPUT);
  digitalWrite(PIN_AMP_SD, LOW);
  pinMode(PIN_MIC_POWER, OUTPUT);
  digitalWrite(PIN_MIC_POWER, LOW);
  ModemSerial.begin(115200, SERIAL_8N1, PIN_MODEM_RX, PIN_MODEM_TX);
  bringup::run_all(ModemSerial, Serial);
  return;
#endif

  const WakeReason reason = getWakeReason();
  if (reason == WakeReason::Cold) {
    g_log.clear();          // RTC-Speicher beim Kaltstart nicht vertrauen
    g_uptime_offset_s = 0;
    g_last_motion_push_s = 0;
    ++g_reset_count;
  }
  g_log.add(uptime_s(), tracker::LogEvent::Boot, static_cast<int16_t>(reason));
  LOGF("\n[UT] Wake-Grund: %d (Reset #%lu)\n", static_cast<int>(reason),
       static_cast<unsigned long>(g_reset_count));

  pinMode(PIN_AMP_SD, OUTPUT);
  digitalWrite(PIN_AMP_SD, LOW);
  pinMode(PIN_MIC_POWER, OUTPUT);
  digitalWrite(PIN_MIC_POWER, LOW);
  pinMode(PIN_PTT_BUTTON, INPUT_PULLUP);

  bool have_config = g_storage.load(g_config);
#if UT_DEBUG_SERIAL
  if (try_provision(5000)) have_config = true;
#endif
  if (!have_config) {
    LOGF("[UT] Keine Konfiguration – Provisioning nötig, schlafe 60 min\n");
    goToSleep(reason, -1.0f, false);
  }

  // Bewegungs-Drossel (B2): höchstens ein Push pro MOTION_MIN_SLEEP_S.
  if (reason == WakeReason::Motion) {
    const uint32_t now = uptime_s();
    if (!tracker::motion_push_allowed(now, g_last_motion_push_s, tracker::WakeSettings{})) {
      g_log.add(now, tracker::LogEvent::Motion, -1);  // gedrosselt
      goToSleep(reason, -1.0f, false);
    }
    g_last_motion_push_s = now;
  }

  ModemSerial.begin(115200, SERIAL_8N1, PIN_MODEM_RX, PIN_MODEM_TX);

  tracker::WakeCycleDeps deps;
  deps.modem = &g_modem;
  deps.config = &g_config;
  deps.firmware_version = FIRMWARE_VERSION;
  deps.want_fix = (reason == WakeReason::Motion || reason == WakeReason::Timer);

  const tracker::WakeCycleResult result =
      tracker::run_wake_cycle(toPolicyReason(reason), -1.0f, deps);

  g_log.add(uptime_s(), tracker::LogEvent::Upload, static_cast<int16_t>(result.http_status));
  if (result.have_message) g_log.add(uptime_s(), tracker::LogEvent::Download, 1);
  if (result.have_ota) {
    // TODO(Hardware): OTA ausführen – ota.h prüfen, Binär laden, mit Update
    // schreiben, SHA256 vergleichen, Rollback bei Fehlschlag (B7).
    g_log.add(uptime_s(), tracker::LogEvent::Error, 77);
  }
  if (result.error[0] != '\0') {
    LOGF("[UT] Zyklus-Ergebnis: %d (%s)\n", static_cast<int>(result.outcome), result.error.c_str());
  }

  g_storage.save(g_config);  // vom Server aktualisierte Konfiguration sichern

  goToSleep(reason, -1.0f, result.search_mode);
}

void loop() {
#if UT_BRINGUP
  bringup::loop(ModemSerial, Serial);
  delay(50);
  return;
#endif
  // Alle Abläufe sind zustandsbasiert und enden in goToSleep(); loop() bleibt leer.
  delay(1000);
}
