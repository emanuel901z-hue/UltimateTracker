// Host-Tests für Provisioning und Konfigurationsspeicher (B6).

#include <unity.h>

#include <cstdio>
#include <cstring>
#include <string>

#include "config_store.h"

using tracker::DeviceConfig;
using tracker::MemoryConfigStorage;

void setUp() {}
void tearDown() {}

static void test_valid_provisioning_command() {
  const char* json =
      R"({"cmd":"provision","device_id":"860000000000000","server":"http://192.168.1.10:8085",)"
      R"("token":"geheim-123","poll_s":600,"search_poll_s":45,"volume":70,"modem_mode":1})";
  DeviceConfig config;
  std::string error;
  TEST_ASSERT_TRUE(tracker::parse_provisioning_command(json, config, error));
  TEST_ASSERT_EQUAL_STRING("860000000000000", config.device_id);
  TEST_ASSERT_EQUAL_STRING("http://192.168.1.10:8085", config.server_url);
  TEST_ASSERT_EQUAL_STRING("geheim-123", config.device_token);
  TEST_ASSERT_EQUAL_UINT32(600, config.poll_interval_s);
  TEST_ASSERT_EQUAL_UINT32(45, config.search_poll_interval_s);
  TEST_ASSERT_EQUAL_UINT8(70, config.audio_volume);
  TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(tracker::ModemPowerMode::Psm),
                          static_cast<uint8_t>(config.modem_power_mode));
  TEST_ASSERT_TRUE(config.valid);
}

static void test_missing_token_is_rejected() {
  const char* json = R"({"cmd":"provision","device_id":"123","server":"http://host:8085"})";
  DeviceConfig config;
  std::string error;
  TEST_ASSERT_FALSE(tracker::parse_provisioning_command(json, config, error));
  TEST_ASSERT_TRUE(error.find("device_token") != std::string::npos);
}

static void test_bad_server_url_is_rejected() {
  const char* json =
      R"({"cmd":"provision","device_id":"123","server":"192.168.1.10:8085","token":"x"})";
  DeviceConfig config;
  std::string error;
  TEST_ASSERT_FALSE(tracker::parse_provisioning_command(json, config, error));
  TEST_ASSERT_TRUE(error.find("http") != std::string::npos);
}

static void test_wrong_command_is_rejected() {
  const char* json = R"({"cmd":"reboot","device_id":"123","server":"http://h:1","token":"x"})";
  DeviceConfig config;
  std::string error;
  TEST_ASSERT_FALSE(tracker::parse_provisioning_command(json, config, error));
  TEST_ASSERT_TRUE(error.find("provision") != std::string::npos);
}

static void test_invalid_json_is_rejected() {
  DeviceConfig config;
  std::string error;
  TEST_ASSERT_FALSE(tracker::parse_provisioning_command("{kein json", config, error));
}

static void test_volume_out_of_range_is_rejected() {
  const char* json =
      R"({"cmd":"provision","device_id":"123","server":"http://h:1","token":"x","volume":150})";
  DeviceConfig config;
  std::string error;
  TEST_ASSERT_FALSE(tracker::parse_provisioning_command(json, config, error));
}

static void test_long_values_are_truncated_safely() {
  std::string long_id(80, '9');
  const std::string json = std::string(R"({"cmd":"provision","device_id":")") + long_id +
                           R"(","server":"http://h:1","token":"x"})";
  DeviceConfig config;
  std::string error;
  TEST_ASSERT_TRUE(tracker::parse_provisioning_command(json, config, error));
  TEST_ASSERT_EQUAL_UINT32(tracker::kDeviceIdMax - 1, std::strlen(config.device_id));
}

static void test_memory_storage_roundtrip() {
  MemoryConfigStorage storage;
  DeviceConfig missing;
  TEST_ASSERT_FALSE(storage.load(missing));  // nichts gespeichert

  DeviceConfig config;
  std::snprintf(config.device_id, sizeof(config.device_id), "123");
  std::snprintf(config.server_url, sizeof(config.server_url), "http://h:1");
  std::snprintf(config.device_token, sizeof(config.device_token), "t");
  config.valid = true;
  TEST_ASSERT_TRUE(storage.save(config));

  DeviceConfig loaded;
  TEST_ASSERT_TRUE(storage.load(loaded));
  TEST_ASSERT_EQUAL_STRING("123", loaded.device_id);
  TEST_ASSERT_TRUE(loaded.valid);

  storage.clear();
  TEST_ASSERT_FALSE(storage.load(loaded));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_valid_provisioning_command);
  RUN_TEST(test_missing_token_is_rejected);
  RUN_TEST(test_bad_server_url_is_rejected);
  RUN_TEST(test_wrong_command_is_rejected);
  RUN_TEST(test_invalid_json_is_rejected);
  RUN_TEST(test_volume_out_of_range_is_rejected);
  RUN_TEST(test_long_values_are_truncated_safely);
  RUN_TEST(test_memory_storage_roundtrip);
  return UNITY_END();
}
