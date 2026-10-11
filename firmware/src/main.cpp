// UltimateTracker – Firmware-Skelett
// Hardware: LilyGO T-SIM7080G-S3 V1.0 (ESP32-S3-WROOM-1 N16R8) + SIM7080G
// Pin-Belegung: include/pins.h (Quelle: docs/pinout.md)
//
// Status: Skelett. Modem-, GNSS-, Audio- und PMU-Code folgen nach der
// Inbetriebnahme (siehe docs/measurement-plan.md).

#include <Arduino.h>
#include "esp_sleep.h"
#include "pins.h"

// Poll-Intervall für Server-Abfragen (Normalbetrieb); Suchmodus wird vom
// Server signalisiert und verkürzt das Intervall auf 30–60 s.
static constexpr uint64_t POLL_INTERVAL_US = 15ULL * 60ULL * 1000000ULL;

enum class WakeReason { Cold, Motion, Ptt, Timer, ModemRi };

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
  //       und INT1 (latch, active-low) konfigurieren.
  // TODO: PMU (AXP2101, I2C 15/7) initialisieren, TS-Pin-Detection deaktivieren,
  //       Akkustand-Auslesung vorbereiten.
}

static void goToSleep() {
  // TODO: Modem in PSM/Sleep versetzen (GPIO 42/DTR bzw. AT+CPSMS).
  digitalWrite(PIN_AMP_SD, LOW);
  digitalWrite(PIN_MIC_POWER, LOW);
  // TODO: EXT1-Wake für LIS3DH-INT1 und PTT konfigurieren (Pegel prüfen!)
  // esp_sleep_enable_ext1_wakeup(BIT64(PIN_LIS3DH_INT1) | BIT64(PIN_PTT_BUTTON),
  //                              ESP_EXT1_WAKEUP_ANY_LOW);
  esp_sleep_enable_timer_wakeup(POLL_INTERVAL_US);
  esp_deep_sleep_start();
}

// ---------------------------------------------------------------------------
// Ablauf-Bausteine (noch zu implementieren)
// ---------------------------------------------------------------------------
static void runLocationPush() { /* TODO: GNSS -> Fix -> LTE -> OsmAnd-GET */ }
static void runPttUplink()     { /* TODO: Quittungston, 8 kHz ADPCM, Upload */ }
static void runServerPoll()    { /* TODO: /pending abfragen, ggf. Downlink */ }
static void runSearchMode()    { /* TODO: Piezo-Intervallton + kurzes Poll */ }
static void runPlayback()      { /* TODO: Download -> ADPCM-Decode -> Amp an */ }

void setup() {
  Serial.begin(115200);
  delay(200);
  WakeReason reason = getWakeReason();
  Serial.printf("\n[UltimateTracker] Wake-Grund: %d\n", static_cast<int>(reason));
  initPins();

  switch (reason) {
    case WakeReason::Motion:  runLocationPush(); break;
    case WakeReason::Ptt:     runPttUplink();    break;
    case WakeReason::Timer:   runServerPoll();   break;
    case WakeReason::ModemRi: /* SMS-Pfad erst nach Messung M4 */ break;
    case WakeReason::Cold:    /* Erstinbetriebnahme/Reset */      break;
  }

  goToSleep();
}

void loop() {
  // Alle Abläufe sind zustandsbasiert und enden in goToSleep(); loop() bleibt leer.
  delay(1000);
}
