// wake_cycle.h – ein kompletter Wake-Zyklus als testbare Logik.
//
// Ablauf: Modem an → (GNSS-Fix) → Sync (Position hoch, Nachricht/Config/OTA
// runter) → ggf. Audio-Download → Modem in den Schlafmodus.
//
// Alles läuft über die IModem-Schnittstelle → mit MockModem auf dem Host
// vollständig testbar, ohne Hardware (docs/simulation.md).

#pragma once

#include <cstdint>
#include <string>

#include "config_store.h"
#include "modem.h"
#include "protocol.h"
#include "wake_policy.h"

namespace tracker {

enum class WakeOutcome : uint8_t { Ok, NoFix, NoNetwork, SyncFailed, ConfigInvalid };

struct WakeCycleResult {
  WakeOutcome outcome;
  uint32_t next_sleep_s;
  bool search_mode;
  bool have_message;
  bool have_ota;
  bool position_valid;
  int http_status;
  uint32_t fix_time_ms;
  std::string error;

  WakeCycleResult()
      : outcome(WakeOutcome::Ok), next_sleep_s(900), search_mode(false), have_message(false),
        have_ota(false), position_valid(false), http_status(0), fix_time_ms(0) {}
};

struct WakeCycleDeps {
  IModem* modem;
  DeviceConfig* config;  // wird aus der Serverantwort aktualisiert (C2)
  WakeSettings settings;
  const char* firmware_version;
  bool want_fix;  // true = GNSS-Fix versuchen (Bewegung/Timer), false = nur Sync

  WakeCycleDeps() : modem(nullptr), config(nullptr), firmware_version("0.1.0"), want_fix(true) {}
};

// Führt den Zyklus aus. `reason` bestimmt den Wake-Grund im Sync,
// `battery_percent` (< 0 = unbekannt) fließt in die Schlafentscheidung ein.
WakeCycleResult run_wake_cycle(WakeReason reason, float battery_percent, WakeCycleDeps& deps);

}  // namespace tracker
