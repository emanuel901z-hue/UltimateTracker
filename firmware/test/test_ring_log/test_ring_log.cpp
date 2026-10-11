// Host-Tests für den Ereignis-Ringpuffer (pio test -e native).

#include <unity.h>

#include "ring_log.h"

void setUp() {}
void tearDown() {}

static void test_starts_empty() {
  tracker::RingLog log;
  TEST_ASSERT_EQUAL_UINT32(0, log.size());
}

static void test_keeps_insertion_order() {
  tracker::RingLog log;
  log.add(10, tracker::LogEvent::Boot);
  log.add(20, tracker::LogEvent::Motion, 3);
  TEST_ASSERT_EQUAL_UINT32(2, log.size());
  TEST_ASSERT_EQUAL_UINT32(10, log.at(0).uptime_s);
  TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(tracker::LogEvent::Motion),
                          static_cast<uint8_t>(log.at(1).event));
  TEST_ASSERT_EQUAL_INT16(3, log.at(1).value);
}

static void test_wraps_and_keeps_newest() {
  tracker::RingLog log;
  for (int i = 0; i < 30; ++i) {
    log.add(static_cast<uint32_t>(i), tracker::LogEvent::Motion, static_cast<int16_t>(i));
  }
  TEST_ASSERT_EQUAL_UINT32(tracker::RingLog::kCapacity, log.size());
  TEST_ASSERT_EQUAL_INT16(6, log.at(0).value);   // ältester: 30 - 24
  TEST_ASSERT_EQUAL_INT16(29, log.at(log.size() - 1).value);  // neuester
}

static void test_clear_resets() {
  tracker::RingLog log;
  log.add(1, tracker::LogEvent::Error, -5);
  log.clear();
  TEST_ASSERT_EQUAL_UINT32(0, log.size());
  TEST_ASSERT_EQUAL_UINT32(0, log.at(0).uptime_s);  // leerer Eintrag
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_starts_empty);
  RUN_TEST(test_keeps_insertion_order);
  RUN_TEST(test_wraps_and_keeps_newest);
  RUN_TEST(test_clear_resets);
  return UNITY_END();
}
