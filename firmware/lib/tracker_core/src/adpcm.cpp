#include "adpcm.h"

namespace tracker {
namespace {

constexpr int16_t kStepTable[89] = {
    7,     8,     9,     10,    11,    12,    13,    14,    16,    17,    19,
    21,    23,    25,    28,    31,    34,    37,    41,    45,    50,    55,
    60,    66,    73,    80,    88,    97,    107,   118,   130,   143,   157,
    173,   190,   209,   230,   253,   279,   307,   337,   371,   408,   449,
    494,   544,   598,   658,   724,   796,   876,   963,   1060,  1166,  1282,
    1411,  1552,  1707,  1878,  2066,  2272,  2499,  2749,  3024,  3327,  3660,
    4026,  4428,  4871,  5358,  5894,  6484,  7132,  7845,  8630,  9493,  10442,
    11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794,
    32767};

constexpr int8_t kIndexTable[16] = {-1, -1, -1, -1, 2, 4, 6, 8,
                                    -1, -1, -1, -1, 2, 4, 6, 8};

int clampIndex(int index) {
  if (index < 0) return 0;
  if (index > 88) return 88;
  return index;
}

int32_t clamp16(int32_t value) {
  if (value > 32767) return 32767;
  if (value < -32768) return -32768;
  return value;
}

uint8_t encodeSample(int32_t& predictor, int& index, int16_t sample) {
  const int32_t step = kStepTable[index];
  int32_t diff = static_cast<int32_t>(sample) - predictor;
  uint8_t code = 0;
  if (diff < 0) {
    code = 8;
    diff = -diff;
  }
  int32_t threshold = step;
  if (diff >= threshold) {
    code |= 4;
    diff -= threshold;
  }
  threshold >>= 1;
  if (diff >= threshold) {
    code |= 2;
    diff -= threshold;
  }
  threshold >>= 1;
  if (diff >= threshold) {
    code |= 1;
  }

  int32_t delta = step >> 3;
  if (code & 4) delta += step;
  if (code & 2) delta += step >> 1;
  if (code & 1) delta += step >> 2;
  predictor = clamp16((code & 8) ? predictor - delta : predictor + delta);
  index = clampIndex(index + kIndexTable[code]);
  return code;
}

int16_t decodeSample(int32_t& predictor, int& index, uint8_t code) {
  const int32_t step = kStepTable[index];
  int32_t delta = step >> 3;
  if (code & 4) delta += step;
  if (code & 2) delta += step >> 1;
  if (code & 1) delta += step >> 2;
  predictor = clamp16((code & 8) ? predictor - delta : predictor + delta);
  index = clampIndex(index + kIndexTable[code & 0x0F]);
  return static_cast<int16_t>(predictor);
}

}  // namespace

void AdpcmEncoder::reset() {
  predictor_ = 0;
  index_ = 0;
}

size_t AdpcmEncoder::encode(const int16_t* samples, size_t count, uint8_t* out) {
  size_t written = 0;
  for (size_t i = 0; i < count; i += 2) {
    const uint8_t low = encodeSample(predictor_, index_, samples[i]);
    const uint8_t high =
        (i + 1 < count) ? encodeSample(predictor_, index_, samples[i + 1]) : 0;
    out[written++] = static_cast<uint8_t>(low | (high << 4));
  }
  return written;
}

void AdpcmDecoder::reset() {
  predictor_ = 0;
  index_ = 0;
}

size_t AdpcmDecoder::decode(const uint8_t* data, size_t bytes, int16_t* out) {
  size_t written = 0;
  for (size_t i = 0; i < bytes; ++i) {
    out[written++] = decodeSample(predictor_, index_, data[i] & 0x0F);
    out[written++] = decodeSample(predictor_, index_, (data[i] >> 4) & 0x0F);
  }
  return written;
}

}  // namespace tracker
