// wake_policy.h – Entscheidungen rund um Aufwachen, Drossel und Poll-Intervalle.
//
// Kapselt die Regeln aus docs/optimizations.md (B2 Wake-Drossel, B4
// server-getriebenes Intervall, B9 Low-Battery) als reine Logik → host-testbar.

#pragma once

#include <cstdint>

namespace tracker {

struct WakeSettings {
  uint32_t motion_min_sleep_s = 180;   // Vorgabe: max. 3 Minuten (B2)
  uint32_t poll_interval_s = 900;      // Normalbetrieb
  uint32_t search_poll_interval_s = 60;
  uint32_t low_battery_poll_s = 1800;
  uint8_t battery_low_percent = 15;
  uint32_t min_poll_s = 60;            // Serverwerte außerhalb dieses Bereichs verwerfen
  uint32_t max_poll_s = 3600;
};

enum class WakeReason : uint8_t { Cold, Motion, Ptt, Timer, ModemRi };

// Drossel: darf nach einem Bewegungs-Interrupt wirklich ein Push erfolgen?
// Verhindert Wake-Stürme, wenn das Kind herumläuft.
bool motion_push_allowed(uint32_t now_s, uint32_t last_motion_push_s,
                         const WakeSettings& settings);

// Schlafdauer (Sekunden) nach einem Push.
uint32_t next_sleep_seconds(WakeReason reason, float battery_percent, bool search_mode,
                            const WakeSettings& settings);

// Vom Server geliefertes Poll-Intervall auf sinnvolle Grenzen begrenzen.
uint32_t sanitize_poll_interval(uint32_t server_value, const WakeSettings& settings);

// Name des Wake-Grunds für das Sync-Protokoll ("motion", "ptt", "timer", ...).
const char* wake_reason_name(WakeReason reason);

}  // namespace tracker
