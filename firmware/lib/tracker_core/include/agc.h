// agc.h – einfache Pegel-Normalisierung für die Aufnahme.
//
// Der INMP441 liefert relativ leise Signale; ohne Verstärkung ist die
// ADPCM-kodierte Sprache schwer verständlich (docs/optimizations.md B5).
// Reine Logik → host-testbar.

#pragma once

#include <cstddef>
#include <cstdint>

namespace tracker {

struct AgcResult {
  int32_t gain_q10;  // Verstärkung in Q10 (1024 = 1.0)
  int peak;          // gemessener Spitzenwert vor der Verstärkung
};

// Ermittelt eine Verstärkung, die den Peak Richtung `target_peak` hebt.
// Die Verstärkung wird auf [1.0 .. max_gain_q10] begrenzt (nie abschwächen).
AgcResult analyze(const int16_t* samples, size_t count, int target_peak = 8000,
                  int32_t max_gain_q10 = 4096);

// Wendet die Verstärkung an (sättigt bei int16-Grenzen).
void apply(int16_t* samples, size_t count, int32_t gain_q10);

}  // namespace tracker
