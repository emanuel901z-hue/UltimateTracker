// Host-Tests für das Sync-Protokoll (pio test -e native).
// Prüft Bauen und Parsen gegen das echte Antwortformat der Bridge.

#include <unity.h>

#include <ArduinoJson.h>

#include "protocol.h"

void setUp() {}
void tearDown() {}

static void test_build_request_roundtrip() {
  tracker::SyncRequest request;
  request.device_id = "860000000000000";
  request.battery_percent = 87.5f;
  request.wake_reason = "motion";
  request.firmware = "0.1.0";
  request.position = tracker::Position{true, 48.1372, 11.5756, 1.4f, 1791740000u};

  const std::string json = tracker::build_sync_request(request);

  JsonDocument doc;
  TEST_ASSERT_TRUE(deserializeJson(doc, json) == DeserializationError::Ok);
  TEST_ASSERT_EQUAL_STRING("860000000000000", doc["device_id"].as<const char*>());
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 87.5f, doc["battery"].as<float>());
  TEST_ASSERT_EQUAL_STRING("motion", doc["wake_reason"].as<const char*>());
  TEST_ASSERT_DOUBLE_WITHIN(0.0001, 48.1372, doc["position"]["lat"].as<double>());
  TEST_ASSERT_DOUBLE_WITHIN(0.0001, 11.5756, doc["position"]["lon"].as<double>());
  TEST_ASSERT_EQUAL_UINT32(1791740000u, doc["position"]["ts"].as<uint32_t>());
}

static void test_build_request_without_position_or_battery() {
  tracker::SyncRequest request;
  request.device_id = "TEST123";
  request.wake_reason = "timer";
  const std::string json = tracker::build_sync_request(request);

  JsonDocument doc;
  TEST_ASSERT_TRUE(deserializeJson(doc, json) == DeserializationError::Ok);
  TEST_ASSERT_FALSE(doc["battery"].is<float>());
  TEST_ASSERT_FALSE(doc["position"].is<JsonObjectConst>());
}

static void test_parse_response_with_message() {
  const char* json =
      R"({"server_time":"2026-10-11T18:00:00Z","search_mode":true,"next_poll_s":60,)"
      R"("message":{"id":"abc123","url":"/api/v1/device/messages/abc123/audio",)"
      R"("format":"wav","size":4190,"duration_ms":2000},)"
      R"("config":{"audio_volume":null,"log_level":null},"min_fw":null})";

  tracker::SyncResponse response;
  TEST_ASSERT_TRUE(tracker::parse_sync_response(json, response));
  TEST_ASSERT_TRUE(response.search_mode);
  TEST_ASSERT_EQUAL_UINT32(60, response.next_poll_s);
  TEST_ASSERT_TRUE(response.message.present);
  TEST_ASSERT_EQUAL_STRING("abc123", response.message.id.c_str());
  TEST_ASSERT_EQUAL_STRING("wav", response.message.format.c_str());
  TEST_ASSERT_EQUAL_UINT32(4190, response.message.size);
}

static void test_parse_response_without_message() {
  const char* json = R"({"server_time":"2026-10-11T18:00:00Z","search_mode":false,"next_poll_s":900,"message":null})";
  tracker::SyncResponse response;
  TEST_ASSERT_TRUE(tracker::parse_sync_response(json, response));
  TEST_ASSERT_FALSE(response.search_mode);
  TEST_ASSERT_EQUAL_UINT32(900, response.next_poll_s);
  TEST_ASSERT_FALSE(response.message.present);
}

static void test_parse_invalid_json_fails() {
  tracker::SyncResponse response;
  TEST_ASSERT_FALSE(tracker::parse_sync_response("{kein json", response));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_build_request_roundtrip);
  RUN_TEST(test_build_request_without_position_or_battery);
  RUN_TEST(test_parse_response_with_message);
  RUN_TEST(test_parse_response_without_message);
  RUN_TEST(test_parse_invalid_json_fails);
  return UNITY_END();
}
