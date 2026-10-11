// Host-Tests für die GNSS-Auswertung (AT+CGNSINF).

#include <unity.h>

#include "gnss.h"

void setUp() {}
void tearDown() {}

static void test_parses_simcom_example_line() {
  // Original-Beispielzeile aus dem SIMCom-GNSS-Application-Note
  const char* line =
      "+CGNSINF: 1,1,20191024051848.000,31.221946,121.355565,3.417,0.00,,0,,1.4,1.7,0.9,,6,,12.4,12.0";
  tracker::GnssFix fix;
  TEST_ASSERT_TRUE(tracker::parse_cgnsinf(line, fix));
  TEST_ASSERT_TRUE(fix.valid);
  TEST_ASSERT_DOUBLE_WITHIN(0.0001, 31.221946, fix.latitude);
  TEST_ASSERT_DOUBLE_WITHIN(0.0001, 121.355565, fix.longitude);
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 1.4f, fix.hdop);
  // 2019-10-24 05:18:48 UTC
  TEST_ASSERT_EQUAL_UINT32(1571894328u, fix.epoch_s);
}

static void test_rejects_no_fix() {
  const char* line = "+CGNSINF: 1,0,,0.000000,0.000000,0.000,0.00,,0,,0.0,0.0,0.0,,0,,,";
  tracker::GnssFix fix;
  TEST_ASSERT_FALSE(tracker::parse_cgnsinf(line, fix));
  TEST_ASSERT_FALSE(fix.valid);
}

static void test_rejects_gnss_off() {
  const char* line = "+CGNSINF: 0,,,,,,,,,,,,,,,,";
  tracker::GnssFix fix;
  TEST_ASSERT_FALSE(tracker::parse_cgnsinf(line, fix));
}

static void test_accepts_line_without_prefix_and_time() {
  const char* line = "1,1,,48.137200,11.575600,500.0,0.0,,0,,1.2,,,,,,,";
  tracker::GnssFix fix;
  TEST_ASSERT_TRUE(tracker::parse_cgnsinf(line, fix));
  TEST_ASSERT_DOUBLE_WITHIN(0.0001, 48.1372, fix.latitude);
  TEST_ASSERT_EQUAL_UINT32(0, fix.epoch_s);  // ohne Zeitfeld
}

static void test_rejects_zero_coordinates() {
  const char* line = "1,1,20260101120000.000,0.000000,0.000000,0.0,,,,,1.0,,,,";
  tracker::GnssFix fix;
  TEST_ASSERT_FALSE(tracker::parse_cgnsinf(line, fix));
}

static void test_epoch_conversion() {
  TEST_ASSERT_EQUAL_UINT32(0u, tracker::utc_to_epoch(1970, 1, 1, 0, 0, 0));
  TEST_ASSERT_EQUAL_UINT32(86400u, tracker::utc_to_epoch(1970, 1, 2, 0, 0, 0));
  TEST_ASSERT_EQUAL_UINT32(1767225600u, tracker::utc_to_epoch(2026, 1, 1, 0, 0, 0));
  // Schaltjahr
  TEST_ASSERT_EQUAL_UINT32(951782400u, tracker::utc_to_epoch(2000, 2, 29, 0, 0, 0));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_parses_simcom_example_line);
  RUN_TEST(test_rejects_no_fix);
  RUN_TEST(test_rejects_gnss_off);
  RUN_TEST(test_accepts_line_without_prefix_and_time);
  RUN_TEST(test_rejects_zero_coordinates);
  RUN_TEST(test_epoch_conversion);
  return UNITY_END();
}
