#include "wake_policy.h"

namespace tracker {

bool motion_push_allowed(uint32_t now_s, uint32_t last_motion_push_s,
                         const WakeSettings& settings) {
  if (last_motion_push_s == 0) return true;  // erster Push seit dem Boot
  // Unsigned-Arithmetik: nach einem Reboot (Uptime zurückgesetzt) läuft die
  // Differenz über und ergibt einen großen Wert → Push erlaubt (sicher).
  return (now_s - last_motion_push_s) >= settings.motion_min_sleep_s;
}

uint32_t next_sleep_seconds(WakeReason reason, float battery_percent, bool search_mode,
                            const WakeSettings& settings) {
  if (search_mode) return settings.search_poll_interval_s;
  if (reason == WakeReason::Motion) return settings.motion_min_sleep_s;
  if (battery_percent < static_cast<float>(settings.battery_low_percent)) {
    return settings.low_battery_poll_s;
  }
  return settings.poll_interval_s;
}

uint32_t sanitize_poll_interval(uint32_t server_value, const WakeSettings& settings) {
  if (server_value < settings.min_poll_s) return settings.min_poll_s;
  if (server_value > settings.max_poll_s) return settings.max_poll_s;
  return server_value;
}

}  // namespace tracker
