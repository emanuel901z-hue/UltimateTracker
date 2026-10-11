// Host-Tests für die Wake-/Poll-Regeln (pio test -e native).

#include <unity.h>

#include "wake_policy.h"

using tracker::next_sleep_seconds;
using tracker::WakeReason;
using tracker::WakeSettings;

void setUp() {}
void tearDown() {}

static void test_motion_throttle_blocks_early_pushes() {
  WakeSettings settings;  // motion_min_sleep_s = 180
  TEST_ASSERT_TRUE(tracker::motion_push_allowed(5000, 0, settings));       // erster Push
  TEST_ASSERT_FALSE(tracker::motion_push_allowed(5100, 5000, settings));   // 100 s < 180 s
  TEST_ASSERT_FALSE(tracker::motion_push_allowed(5179, 5000, settings));   // 179 s
  TEST_ASSERT_TRUE(tracker::motion_push_allowed(5180, 5000, settings));    // genau 3 min
  TEST_ASSERT_TRUE(tracker::motion_push_allowed(9000, 5000, settings));    // später
}

static void test_motion_throttle_survives_reboot() {
  WakeSettings settings;
  // Uptime nach Reboot kleiner als der letzte Push-Zeitstempel → Push erlaubt
  TEST_ASSERT_TRUE(tracker::motion_push_allowed(30, 5000, settings));
}

static void test_sleep_after_motion_is_three_minutes() {
  WakeSettings settings;
  TEST_ASSERT_EQUAL_UINT32(180, next_sleep_seconds(WakeReason::Motion, 80.0f, false, settings));
}

static void test_sleep_in_search_mode_is_short() {
  WakeSettings settings;
  TEST_ASSERT_EQUAL_UINT32(60, next_sleep_seconds(WakeReason::Timer, 80.0f, true, settings));
  TEST_ASSERT_EQUAL_UINT32(60, next_sleep_seconds(WakeReason::Motion, 5.0f, true, settings));
}

static void test_sleep_on_low_battery_is_longer() {
  WakeSettings settings;
  TEST_ASSERT_EQUAL_UINT32(1800, next_sleep_seconds(WakeReason::Timer, 10.0f, false, settings));
  TEST_ASSERT_EQUAL_UINT32(900, next_sleep_seconds(WakeReason::Timer, 50.0f, false, settings));
}

static void test_server_interval_is_clamped() {
  WakeSettings settings;
  TEST_ASSERT_EQUAL_UINT32(60, tracker::sanitize_poll_interval(5, settings));
  TEST_ASSERT_EQUAL_UINT32(300, tracker::sanitize_poll_interval(300, settings));
  TEST_ASSERT_EQUAL_UINT32(3600, tracker::sanitize_poll_interval(100000, settings));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_motion_throttle_blocks_early_pushes);
  RUN_TEST(test_motion_throttle_survives_reboot);
  RUN_TEST(test_sleep_after_motion_is_three_minutes);
  RUN_TEST(test_sleep_in_search_mode_is_short);
  RUN_TEST(test_sleep_on_low_battery_is_longer);
  RUN_TEST(test_server_interval_is_clamped);
  return UNITY_END();
}
