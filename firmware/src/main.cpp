// UltimateTracker – Firmware-Skelett
// Hardware: LilyGO T-SIM7080G-S3 V1.0 (ESP32-S3-WROOM-1 N16R8) + SIM7080G
// Pin-Belegung: include/pins.h (Quelle: docs/pinout.md)
// ESP32-S3-Eigenheiten: docs/esp32s3.md
//
// Status: Skelett. Modem-, GNSS-, Audio- und PMU-Code folgen nach der
// Inbetriebnahme (siehe docs/measurement-plan.md).

#include <Arduino.h>
#include "esp_attr.h"
#include "esp_sleep.h"
#include "config.h"
#include "pins.h"
#include "ring_log.h"
#include "wake_policy.h"

// --- Debug-Ausgabe ---------------------------------------------------------
// Release-Build (UT_DEBUG_SERIAL=0): keine serielle Ausgabe, kein CDC-Warten.
// Achtung: Serial.flush() blockiert auf dem S3 – hier bewusst nicht verwendet.
#if UT_DEBUG_SERIAL
#define LOGF(...) Serial.printf(__VA_ARGS__)
#else
#define LOGF(...) do { } while (0)
#endif

// Poll-Intervall für Server-Abfragen (Normalbetrieb); der Server kann es per
// /sync überschreiben (next_poll_s), Suchmodus verkürzt es zusätzlich.
static constexpr uint64_t POLL_INTERVAL_US =
    static_cast<uint64_t>(POLL_INTERVAL_S_DEFAULT) * 1000000ULL;

// Ereignis-Log überlebt Deep Sleep im RTC-Slow-Memory (16 KB, docs/esp32s3.md).
// Hinweis: bei Kaltstart wird es unten explizit geleert – bei einem Deep-Sleep-
// Wake bleibt es erhalten.
RTC_DATA_ATTR tracker::RingLog g_log;

enum class WakeReason { Cold, Motion, Ptt, Timer, ModemRi };

static tracker::WakeReason toPolicyReason(WakeReason reason) {
  switch (reason) {
    case WakeReason::Motion: return tracker::WakeReason::Motion;
    case WakeReason::Ptt: return tracker::WakeReason::Ptt;
    case WakeReason::ModemRi: return tracker::WakeReason::ModemRi;
    default: return tracker::WakeReason::Timer;
  }
}

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

static void initPins() {
  pinMode(PIN_PTT_BUTTON, INPUT_PULLUP);
  pinMode(PIN_AMP_SD, OUTPUT);
  digitalWrite(PIN_AMP_SD, LOW); // Verstärker aus
  pinMode(PIN_MIC_POWER, OUTPUT);
  digitalWrite(PIN_MIC_POWER, LOW); // Mikrofon aus
  // TODO: LIS3DH initialisieren (I2C 1/2, Adresse prüfen), Schwellwert-Register
  //       (MOTION_THRESHOLD_MG) und INT1 (latch, active-low) konfigurieren.
  // TODO: PMU (AXP2101, I2C 15/7) initialisieren, TS-Pin-Detection deaktivieren,
  //       Akkustand-Auslesung vorbereiten.
}

static void goToSleep(WakeReason reason, float battery_percent, bool search_mode) {
  // TODO: Modem je nach MODEM_POWER_MODE in PSM/Sleep versetzen bzw. abschalten.
  digitalWrite(PIN_AMP_SD, LOW);
  digitalWrite(PIN_MIC_POWER, LOW);

  const uint32_t sleep_s = tracker::next_sleep_seconds(
      toPolicyReason(reason), battery_percent, search_mode, tracker::WakeSettings{});
  LOGF("[UT] Schlafe %lu s (Grund %d)\n", static_cast<unsigned long>(sleep_s),
       static_cast<int>(reason));

  // EXT1-Wake für LIS3DH-INT1 und PTT.
  // S3-Eigenheit: interne Pull-ups sind im Deep Sleep AUS (RTC-Domain aus) →
  // der Taster braucht zwingend den externen 100k-Pull-up (docs/esp32s3.md).
  esp_sleep_enable_ext1_wakeup(
      (1ULL << PIN_LIS3DH_INT1) | (1ULL << PIN_PTT_BUTTON),
      ESP_EXT1_WAKEUP_ANY_LOW);
  esp_sleep_enable_timer_wakeup(static_cast<uint64_t>(sleep_s) * 1000000ULL);
  esp_deep_sleep_start();
}

// ---------------------------------------------------------------------------
// Ablauf-Bausteine (noch zu implementieren)
// ---------------------------------------------------------------------------
static void runLocationPush() { /* TODO: GNSS -> Fix -> /sync mit Position */ }
static void runPttUplink()     { /* TODO: Quittungston, 8 kHz ADPCM (AGC), Upload */ }
static void runServerPoll()    { /* TODO: /sync abfragen, ggf. Downlink + OTA */ }
static void runSearchMode()    { /* TODO: Piezo-Intervallton + kurzes Poll */ }
static void runPlayback()      { /* TODO: Download -> ADPCM-Decode -> Amp an */ }

void setup() {
#if UT_DEBUG_SERIAL
  Serial.begin(115200);
  delay(200);
#endif

  WakeReason reason = getWakeReason();
  if (reason == WakeReason::Cold) {
    g_log.clear(); // Kaltstart: RTC-Speicher ist nicht vertrauenswürdig
  }
  g_log.add(static_cast<uint32_t>(millis() / 1000), tracker::LogEvent::Boot,
            static_cast<int16_t>(reason));
  LOGF("\n[UT] Wake-Grund: %d\n", static_cast<int>(reason));
  initPins();

  switch (reason) {
    case WakeReason::Motion:  runLocationPush(); break;
    case WakeReason::Ptt:     runPttUplink();    break;
    case WakeReason::Timer:   runServerPoll();   break;
    case WakeReason::ModemRi: /* SMS-Pfad erst nach Messung M4 */ break;
    case WakeReason::Cold:    /* Erstinbetriebnahme/Reset */      break;
  }

  goToSleep(reason, -1.0f, false);
}

void loop() {
  // Alle Abläufe sind zustandsbasiert und enden in goToSleep(); loop() bleibt leer.
  delay(1000);
}
