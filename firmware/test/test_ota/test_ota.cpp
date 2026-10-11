// Host-Tests für die OTA-Entscheidung und -Vorprüfung (B7).

#include <unity.h>

#include <string>

#include "ota.h"

using tracker::FirmwareOffer;

void setUp() {}
void tearDown() {}

static void test_version_comparison() {
  TEST_ASSERT_TRUE(tracker::version_is_newer("0.1.1", "0.1.0"));
  TEST_ASSERT_TRUE(tracker::version_is_newer("0.2.0", "0.1.9"));
  TEST_ASSERT_TRUE(tracker::version_is_newer("1.0.0", "0.9.9"));
  TEST_ASSERT_TRUE(tracker::version_is_newer("1.0", "0.9.9"));
  TEST_ASSERT_FALSE(tracker::version_is_newer("0.1.0", "0.1.0"));
  TEST_ASSERT_FALSE(tracker::version_is_newer("0.0.9", "0.1.0"));
}

static void test_invalid_versions_never_update() {
  TEST_ASSERT_FALSE(tracker::version_is_newer("v0.2.0", "0.1.0"));
  TEST_ASSERT_FALSE(tracker::version_is_newer("0.2.0", ""));
  TEST_ASSERT_FALSE(tracker::version_is_newer("0.2.0-rc1", "0.1.0"));
}

static void test_offer_check_accepts_valid_offer() {
  FirmwareOffer offer;
  offer.present = true;
  offer.version = "0.2.0";
  offer.url = "/api/v1/device/firmware/0.2.0/download";
  offer.sha256 = std::string(64, 'a');
  offer.size = 300000;
  std::string error;
  TEST_ASSERT_TRUE(tracker::ota_offer_is_sane(offer, 2 * 1024 * 1024, error));
}

static void test_offer_check_rejects_bad_values() {
  FirmwareOffer offer;
  offer.present = true;
  offer.version = "0.2.0";
  offer.url = "/firmware";
  offer.sha256 = std::string(64, 'a');
  offer.size = 300000;
  std::string error;

  FirmwareOffer too_big = offer;
  too_big.size = 5 * 1024 * 1024;
  TEST_ASSERT_FALSE(tracker::ota_offer_is_sane(too_big, 2 * 1024 * 1024, error));
  TEST_ASSERT_TRUE(error.find("größer") != std::string::npos);

  FirmwareOffer bad_hash = offer;
  bad_hash.sha256 = "xyz";
  TEST_ASSERT_FALSE(tracker::ota_offer_is_sane(bad_hash, 2 * 1024 * 1024, error));

  FirmwareOffer non_hex = offer;
  non_hex.sha256 = std::string(63, 'a') + "z";
  TEST_ASSERT_FALSE(tracker::ota_offer_is_sane(non_hex, 2 * 1024 * 1024, error));

  FirmwareOffer empty_size = offer;
  empty_size.size = 0;
  TEST_ASSERT_FALSE(tracker::ota_offer_is_sane(empty_size, 2 * 1024 * 1024, error));

  FirmwareOffer not_present;
  TEST_ASSERT_FALSE(tracker::ota_offer_is_sane(not_present, 2 * 1024 * 1024, error));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_version_comparison);
  RUN_TEST(test_invalid_versions_never_update);
  RUN_TEST(test_offer_check_accepts_valid_offer);
  RUN_TEST(test_offer_check_rejects_bad_values);
  return UNITY_END();
}
