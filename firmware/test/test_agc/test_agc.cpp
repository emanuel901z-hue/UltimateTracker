// Host-Tests für die Pegel-Normalisierung (pio test -e native).

#include <unity.h>

#include <cstdlib>

#include "agc.h"

namespace {
int16_t g_buffer[512];
}

void setUp() {}
void tearDown() {}

static void test_quiet_signal_gets_amplified() {
  for (size_t i = 0; i < 512; ++i) g_buffer[i] = (i % 2) ? 500 : -500;
  const tracker::AgcResult result = tracker::analyze(g_buffer, 512, 8000, 4096);
  TEST_ASSERT_EQUAL_INT(500, result.peak);
  TEST_ASSERT_EQUAL_INT32(4096, result.gain_q10);  // 4× – Maximum für so ein leises Signal

  tracker::apply(g_buffer, 512, result.gain_q10);
  int peak_after = 0;
  for (size_t i = 0; i < 512; ++i) {
    const int value = std::abs(static_cast<int>(g_buffer[i]));
    if (value > peak_after) peak_after = value;
  }
  TEST_ASSERT_EQUAL_INT(2000, peak_after);  // 500 × 4
}

static void test_loud_signal_not_amplified() {
  for (size_t i = 0; i < 512; ++i) g_buffer[i] = (i % 2) ? 20000 : -20000;
  const tracker::AgcResult result = tracker::analyze(g_buffer, 512, 8000, 4096);
  TEST_ASSERT_EQUAL_INT32(1024, result.gain_q10);  // 1.0 – nie abschwächen
}

static void test_silence_untouched() {
  for (size_t i = 0; i < 512; ++i) g_buffer[i] = 0;
  const tracker::AgcResult result = tracker::analyze(g_buffer, 512);
  TEST_ASSERT_EQUAL_INT32(1024, result.gain_q10);
}

static void test_apply_saturates_at_limits() {
  int16_t loud[2] = {30000, -30000};
  tracker::apply(loud, 2, 4096);  // 4× Verstärkung
  TEST_ASSERT_EQUAL_INT16(32767, loud[0]);
  TEST_ASSERT_EQUAL_INT16(-32768, loud[1]);
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_quiet_signal_gets_amplified);
  RUN_TEST(test_loud_signal_not_amplified);
  RUN_TEST(test_silence_untouched);
  RUN_TEST(test_apply_saturates_at_limits);
  return UNITY_END();
}
