// bringup.h – Selbsttest-Firmware für die Inbetriebnahme (docs/bring-up.md).
//
// Läuft nur in der Umgebung tsim7080g-s3-bringup (UT_BRINGUP=1):
//   * prüft I2C-Bus, PMU, LIS3DH, Modem, GNSS, I2S (Ton + Mikrofon), Piezo, Taster
//   * bietet danach eine kleine Kommando-Konsole über den USB-Serial-Kanal
//
// Bewusst ohne Zusatz-Bibliotheken für I2C-Geräte (Register direkt), damit der
// Test auch dann etwas aussagt, wenn eine Bibliothek nicht passt.

#pragma once

#include <Arduino.h>

namespace bringup {

// Führt alle Tests aus und gibt sie auf `console` aus.
void run_all(Stream& modem, Stream& console);

// Kommando-Konsole: s = Deep Sleep, m = Modem, g = GNSS, t = Ton,
// p = Piezo, l = LIS3DH, i = I2C-Scan, r = alles erneut, h = Hilfe.
void loop(Stream& modem, Stream& console);

}  // namespace bringup
