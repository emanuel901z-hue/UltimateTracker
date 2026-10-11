// Host-Tests für den kompletten Wake-Zyklus gegen den Modem-Mock
// (docs/simulation.md) – ohne Hardware.

#include <unity.h>

#include <cstdio>
#include <string>

#include "mock_modem.h"
#include "wake_cycle.h"

using tracker::DeviceConfig;
using tracker::MockModem;
using tracker::ModemPowerMode;
using tracker::WakeCycleDeps;
using tracker::WakeOutcome;
using tracker::WakeReason;

namespace {

const char* kSyncOk =
    R"({"server_time":"2026-10-11T18:00:00Z","search_mode":false,"next_poll_s":900,"message":null})";

const char* kSyncSearch =
    R"({"server_time":"2026-10-11T18:00:00Z","search_mode":true,"next_poll_s":60,"message":null})";

const char* kSyncWithMessage =
    R"({"server_time":"2026-10-11T18:00:00Z","search_mode":false,"next_poll_s":900,)"
    R"("message":{"id":"abc123","url":"/api/v1/device/messages/abc123/audio","format":"wav","size":4190}})";

const char* kSyncWithOta =
    R"({"server_time":"2026-10-11T18:00:00Z","search_mode":false,"next_poll_s":900,"message":null,)"
    R"("ota":{"version":"0.2.0","url":"/api/v1/device/firmware/0.2.0/download",)"
    R"("sha256":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","size":300000}})";

const char* kSyncWithConfig =
    R"({"server_time":"2026-10-11T18:00:00Z","search_mode":false,"next_poll_s":1200,"message":null,)"
    R"("config":{"audio_volume":65},"min_fw":"0.1.0"})";

void make_config(DeviceConfig& config) {
  std::snprintf(config.device_id, sizeof(config.device_id), "860000000000000");
  std::snprintf(config.server_url, sizeof(config.server_url), "http://server:8085");
  std::snprintf(config.device_token, sizeof(config.device_token), "token-123");
  config.valid = true;
  config.modem_power_mode = ModemPowerMode::Off;
}

}  // namespace

void setUp() {}
void tearDown() {}

static void test_happy_path_motion_with_fix() {
  MockModem modem;
  modem.fix = tracker::GnssFix();
  modem.fix.latitude = 48.1372;
  modem.fix.longitude = 11.5756;
  modem.fix.hdop = 1.4f;
  modem.fix.fix_time_ms = 12000;
  modem.responses.push_back(tracker::ScriptedResponse("/api/v1/device/sync", 200, kSyncOk));

  DeviceConfig config;
  make_config(config);
  WakeCycleDeps deps;
  deps.modem = &modem;
  deps.config = &config;

  const tracker::WakeCycleResult result = tracker::run_wake_cycle(WakeReason::Motion, 80.0f, deps);

  TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(WakeOutcome::Ok), static_cast<uint8_t>(result.outcome));
  TEST_ASSERT_TRUE(result.position_valid);
  TEST_ASSERT_EQUAL_UINT32(12000, result.fix_time_ms);
  TEST_ASSERT_EQUAL_UINT32(900, result.next_sleep_s);
  TEST_ASSERT_EQUAL_INT(1, modem.begin_calls);
  TEST_ASSERT_EQUAL_INT(1, modem.end_calls);
  TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(ModemPowerMode::Off), static_cast<uint8_t>(modem.last_power_mode));
  TEST_ASSERT_TRUE(modem.posted_bodies[0].find("860000000000000") != std::string::npos);
  TEST_ASSERT_TRUE(modem.posted_bodies[0].find("motion") != std::string::npos);
  TEST_ASSERT_TRUE(modem.posted_bodies[0].find("48.13") != std::string::npos);
}

static void test_no_fix_still_syncs_without_position() {
  MockModem modem;
  modem.fix_ok = false;
  modem.responses.push_back(tracker::ScriptedResponse("/api/v1/device/sync", 200, kSyncOk));

  DeviceConfig config;
  make_config(config);
  WakeCycleDeps deps;
  deps.modem = &modem;
  deps.config = &config;

  const tracker::WakeCycleResult result = tracker::run_wake_cycle(WakeReason::Timer, 70.0f, deps);

  TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(WakeOutcome::NoFix), static_cast<uint8_t>(result.outcome));
  TEST_ASSERT_FALSE(result.position_valid);
  TEST_ASSERT_EQUAL_INT(1, modem.end_calls);  // Modem wurde trotzdem sauber beendet
  TEST_ASSERT_TRUE(modem.posted_bodies[0].find("position") == std::string::npos);
}

static void test_sync_failure_uses_battery_aware_policy() {
  MockModem modem;
  modem.responses.push_back(tracker::ScriptedResponse("/api/v1/device/sync", 500, "boom"));

  DeviceConfig config;
  make_config(config);
  WakeCycleDeps deps;
  deps.modem = &modem;
  deps.config = &config;

  const tracker::WakeCycleResult result = tracker::run_wake_cycle(WakeReason::Timer, 70.0f, deps);

  TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(WakeOutcome::SyncFailed), static_cast<uint8_t>(result.outcome));
  TEST_ASSERT_EQUAL_INT(500, result.http_status);
  TEST_ASSERT_EQUAL_UINT32(900, result.next_sleep_s);  // lokale Policy (Normalbetrieb)
  TEST_ASSERT_EQUAL_INT(1, modem.end_calls);
}

static void test_modem_not_ready() {
  MockModem modem;
  modem.begin_ok = false;

  DeviceConfig config;
  make_config(config);
  WakeCycleDeps deps;
  deps.modem = &modem;
  deps.config = &config;

  const tracker::WakeCycleResult result = tracker::run_wake_cycle(WakeReason::Timer, 70.0f, deps);

  TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(WakeOutcome::NoNetwork), static_cast<uint8_t>(result.outcome));
  TEST_ASSERT_EQUAL_INT(0, modem.fix_calls);
}

static void test_missing_config_is_reported() {
  MockModem modem;
  DeviceConfig config;  // valid = false
  WakeCycleDeps deps;
  deps.modem = &modem;
  deps.config = &config;

  const tracker::WakeCycleResult result = tracker::run_wake_cycle(WakeReason::Timer, 70.0f, deps);

  TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(WakeOutcome::ConfigInvalid), static_cast<uint8_t>(result.outcome));
  TEST_ASSERT_EQUAL_INT(0, modem.begin_calls);
}

static void test_search_mode_shortens_sleep() {
  MockModem modem;
  modem.responses.push_back(tracker::ScriptedResponse("/api/v1/device/sync", 200, kSyncSearch));

  DeviceConfig config;
  make_config(config);
  WakeCycleDeps deps;
  deps.modem = &modem;
  deps.config = &config;

  const tracker::WakeCycleResult result = tracker::run_wake_cycle(WakeReason::Timer, 70.0f, deps);

  TEST_ASSERT_TRUE(result.search_mode);
  TEST_ASSERT_EQUAL_UINT32(60, result.next_sleep_s);
  TEST_ASSERT_EQUAL_UINT32(900, config.poll_interval_s);  // Basisintervall bleibt unberührt
}

static void test_pending_message_is_downloaded() {
  MockModem modem;
  modem.responses.push_back(tracker::ScriptedResponse("/api/v1/device/sync", 200, kSyncWithMessage));
  modem.responses.push_back(tracker::ScriptedResponse("/messages/abc123/audio", 200, "RIFF...."));

  DeviceConfig config;
  make_config(config);
  WakeCycleDeps deps;
  deps.modem = &modem;
  deps.config = &config;

  const tracker::WakeCycleResult result = tracker::run_wake_cycle(WakeReason::Timer, 70.0f, deps);

  TEST_ASSERT_TRUE(result.have_message);
  TEST_ASSERT_EQUAL_INT(2, static_cast<int>(modem.requests.size()));
  TEST_ASSERT_TRUE(modem.requests[1].find("/api/v1/device/messages/abc123/audio") != std::string::npos);
}

static void test_failed_download_is_reported() {
  MockModem modem;
  modem.responses.push_back(tracker::ScriptedResponse("/api/v1/device/sync", 200, kSyncWithMessage));
  modem.responses.push_back(tracker::ScriptedResponse("/messages/abc123/audio", 404, "weg"));

  DeviceConfig config;
  make_config(config);
  WakeCycleDeps deps;
  deps.modem = &modem;
  deps.config = &config;

  const tracker::WakeCycleResult result = tracker::run_wake_cycle(WakeReason::Timer, 70.0f, deps);

  TEST_ASSERT_FALSE(result.have_message);
  TEST_ASSERT_TRUE(result.error.find("Download") != std::string::npos);
}

static void test_ota_offer_is_reported() {
  MockModem modem;
  modem.responses.push_back(tracker::ScriptedResponse("/api/v1/device/sync", 200, kSyncWithOta));

  DeviceConfig config;
  make_config(config);
  WakeCycleDeps deps;
  deps.modem = &modem;
  deps.config = &config;

  const tracker::WakeCycleResult result = tracker::run_wake_cycle(WakeReason::Timer, 70.0f, deps);

  TEST_ASSERT_TRUE(result.have_ota);
}

static void test_server_config_is_applied() {
  MockModem modem;
  modem.responses.push_back(tracker::ScriptedResponse("/api/v1/device/sync", 200, kSyncWithConfig));

  DeviceConfig config;
  make_config(config);
  WakeCycleDeps deps;
  deps.modem = &modem;
  deps.config = &config;

  const tracker::WakeCycleResult result = tracker::run_wake_cycle(WakeReason::Timer, 70.0f, deps);

  TEST_ASSERT_EQUAL_UINT32(1200, config.poll_interval_s);
  TEST_ASSERT_EQUAL_UINT8(65, config.audio_volume);
  TEST_ASSERT_EQUAL_UINT32(1200, result.next_sleep_s);
}

static void test_low_battery_on_failure_lengthens_sleep() {
  MockModem modem;
  modem.responses.push_back(tracker::ScriptedResponse("/api/v1/device/sync", 0, ""));  // Transportfehler

  DeviceConfig config;
  make_config(config);
  WakeCycleDeps deps;
  deps.modem = &modem;
  deps.config = &config;

  const tracker::WakeCycleResult result = tracker::run_wake_cycle(WakeReason::Timer, 10.0f, deps);
  TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(WakeOutcome::SyncFailed), static_cast<uint8_t>(result.outcome));
  TEST_ASSERT_EQUAL_UINT32(1800, result.next_sleep_s);  // Low-Battery-Policy
}

static void test_server_interval_wins_over_local_policy() {
  // Der Server kennt Akkustand und Suchmodus – sein Wert hat Vorrang.
  MockModem modem;
  modem.responses.push_back(tracker::ScriptedResponse("/api/v1/device/sync", 200, kSyncOk));

  DeviceConfig config;
  make_config(config);
  WakeCycleDeps deps;
  deps.modem = &modem;
  deps.config = &config;

  const tracker::WakeCycleResult result = tracker::run_wake_cycle(WakeReason::Timer, 10.0f, deps);
  TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(WakeOutcome::Ok), static_cast<uint8_t>(result.outcome));
  TEST_ASSERT_EQUAL_UINT32(900, result.next_sleep_s);  // Serverwert (der Server verdoppelt selbst bei < 15 %)
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_happy_path_motion_with_fix);
  RUN_TEST(test_no_fix_still_syncs_without_position);
  RUN_TEST(test_sync_failure_uses_battery_aware_policy);
  RUN_TEST(test_modem_not_ready);
  RUN_TEST(test_missing_config_is_reported);
  RUN_TEST(test_search_mode_shortens_sleep);
  RUN_TEST(test_pending_message_is_downloaded);
  RUN_TEST(test_failed_download_is_reported);
  RUN_TEST(test_ota_offer_is_reported);
  RUN_TEST(test_server_config_is_applied);
  RUN_TEST(test_low_battery_on_failure_lengthens_sleep);
  RUN_TEST(test_server_interval_wins_over_local_policy);
  return UNITY_END();
}
