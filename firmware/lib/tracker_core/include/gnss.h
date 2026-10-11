// gnss.h – Auswertung der SIM7080G-GNSS-Antworten (AT+CGNSINF).
//
// Reine Logik → host-testbar mit echten Antwortzeilen aus dem SIMCom-Handbuch.
// Die AT-Sequenz selbst (Antenne an, CGNSPWR, Polling) macht die ESP32-Glue.

#pragma once

#include <cstdint>

#include "modem.h"

namespace tracker {

// Konvertiert ein UTC-Datum in einen Unix-Zeitstempel (ohne Zeitzonen/DST).
uint32_t utc_to_epoch(int year, int month, int day, int hour, int minute, int second);

// Parst eine Zeile der Form
//   +CGNSINF: <run>,<fix>,<utc>,<lat>,<lon>,<alt>,<speed>,<course>,<mode>,
//             <reserved>,<hdop>,<pdop>,<vdop>,<sats>,...
// Beispiel (SIMCom): +CGNSINF: 1,1,20191024051848.000,31.221946,121.355565,3.417,0.00,,0,,1.4,1.7,0.9,,6,,12.4,12.0
// Rückgabe: true, wenn ein gültiger Fix (run=1, fix=1) enthalten ist.
bool parse_cgnsinf(const char* line, GnssFix& fix);

}  // namespace tracker
