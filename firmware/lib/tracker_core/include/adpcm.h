// adpcm.h – IMA-ADPCM (DVI4) für die Sprachkompression.
//
// 4 bit pro Sample ⇒ 4:1. Bei 8 kHz mono ergibt das 4 kB/s
// (siehe docs/decisions.md D-002, docs/hardware-review.md Abschnitt 6).
// Reine Logik ohne Arduino-Abhängigkeit → auf dem Host testbar.

#pragma once

#include <cstddef>
#include <cstdint>

namespace tracker {

class AdpcmEncoder {
 public:
  void reset();
  // Encodiert `count` PCM-Samples; schreibt (count + 1) / 2 Bytes nach `out`.
  // Rückgabe: Anzahl geschriebener Bytes.
  size_t encode(const int16_t* samples, size_t count, uint8_t* out);

 private:
  int32_t predictor_ = 0;
  int index_ = 0;
};

class AdpcmDecoder {
 public:
  void reset();
  // Dekodiert `bytes` ADPCM-Bytes nach `out` (2 Samples pro Byte).
  // Rückgabe: Anzahl geschriebener Samples.
  size_t decode(const uint8_t* data, size_t bytes, int16_t* out);

 private:
  int32_t predictor_ = 0;
  int index_ = 0;
};

}  // namespace tracker
