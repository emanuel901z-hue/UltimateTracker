#include "agc.h"

#include <cstdlib>

namespace tracker {
namespace {

constexpr int32_t kUnityGainQ10 = 1024;

}  // namespace

AgcResult analyze(const int16_t* samples, size_t count, int target_peak,
                  int32_t max_gain_q10) {
  AgcResult result{};
  result.gain_q10 = kUnityGainQ10;
  if (count == 0) return result;

  int peak = 0;
  for (size_t i = 0; i < count; ++i) {
    const int value = std::abs(static_cast<int>(samples[i]));
    if (value > peak) peak = value;
  }
  result.peak = peak;
  if (peak <= 0) return result;  // Stille: nicht verstärken

  int32_t gain = static_cast<int32_t>((static_cast<int64_t>(target_peak) * kUnityGainQ10) / peak);
  if (gain < kUnityGainQ10) gain = kUnityGainQ10;          // nie abschwächen
  if (gain > max_gain_q10) gain = max_gain_q10;            // Begrenzung
  result.gain_q10 = gain;
  return result;
}

void apply(int16_t* samples, size_t count, int32_t gain_q10) {
  if (gain_q10 == kUnityGainQ10) return;
  for (size_t i = 0; i < count; ++i) {
    int32_t value = (static_cast<int32_t>(samples[i]) * gain_q10) / kUnityGainQ10;
    if (value > 32767) value = 32767;
    if (value < -32768) value = -32768;
    samples[i] = static_cast<int16_t>(value);
  }
}

}  // namespace tracker
