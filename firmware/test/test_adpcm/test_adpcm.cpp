// Host-Tests für den ADPCM-Codec (pio test -e native).

#include <unity.h>

#include <cmath>
#include <cstdint>

#include "adpcm.h"

namespace {

constexpr size_t kSamples = 8000;  // 1 s @ 8 kHz
int16_t g_input[kSamples];
int16_t g_output[kSamples];
uint8_t g_encoded[kSamples / 2];

double snr_db(const int16_t* reference, const int16_t* decoded, size_t count) {
  double signal = 0.0;
  double noise = 0.0;
  for (size_t i = 0; i < count; ++i) {
    const double s = reference[i];
    const double e = static_cast<double>(decoded[i]) - s;
    signal += s * s;
    noise += e * e;
  }
  if (noise <= 0.0) return 200.0;
  return 10.0 * std::log10(signal / noise);
}

}  // namespace

void setUp() {}
void tearDown() {}

static void test_size_and_roundtrip_sine() {
  for (size_t i = 0; i < kSamples; ++i) {
    g_input[i] = static_cast<int16_t>(10000.0 * std::sin(2.0 * M_PI * 440.0 * i / 8000.0));
  }

  tracker::AdpcmEncoder encoder;
  encoder.reset();
  const size_t bytes = encoder.encode(g_input, kSamples, g_encoded);
  TEST_ASSERT_EQUAL_UINT32(kSamples / 2, bytes);

  tracker::AdpcmDecoder decoder;
  decoder.reset();
  const size_t samples = decoder.decode(g_encoded, bytes, g_output);
  TEST_ASSERT_EQUAL_UINT32(kSamples, samples);

  const double snr = snr_db(g_input, g_output, kSamples);
  TEST_ASSERT_TRUE_MESSAGE(snr > 15.0, "SNR unter 15 dB – Codec fehlerhaft?");
}

static void test_silence_stays_quiet() {
  for (size_t i = 0; i < kSamples; ++i) g_input[i] = 0;

  tracker::AdpcmEncoder encoder;
  encoder.reset();
  const size_t bytes = encoder.encode(g_input, kSamples, g_encoded);

  tracker::AdpcmDecoder decoder;
  decoder.reset();
  decoder.decode(g_encoded, bytes, g_output);

  for (size_t i = 0; i < kSamples; ++i) {
    TEST_ASSERT_INT_WITHIN(64, 0, g_output[i]);
  }
}

static void test_odd_sample_count() {
  const int16_t samples[3] = {1000, -1000, 500};
  uint8_t encoded[2] = {0, 0};
  tracker::AdpcmEncoder encoder;
  encoder.reset();
  TEST_ASSERT_EQUAL_UINT32(2, encoder.encode(samples, 3, encoded));
}

static void test_loud_signal_does_not_overflow() {
  for (size_t i = 0; i < kSamples; ++i) {
    g_input[i] = (i % 2 == 0) ? 32767 : -32768;
  }
  tracker::AdpcmEncoder encoder;
  encoder.reset();
  const size_t bytes = encoder.encode(g_input, kSamples, g_encoded);
  tracker::AdpcmDecoder decoder;
  decoder.reset();
  decoder.decode(g_encoded, bytes, g_output);
  for (size_t i = 0; i < kSamples; ++i) {
    TEST_ASSERT_TRUE(g_output[i] >= -32768 && g_output[i] <= 32767);
  }
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_size_and_roundtrip_sine);
  RUN_TEST(test_silence_stays_quiet);
  RUN_TEST(test_odd_sample_count);
  RUN_TEST(test_loud_signal_does_not_overflow);
  return UNITY_END();
}
