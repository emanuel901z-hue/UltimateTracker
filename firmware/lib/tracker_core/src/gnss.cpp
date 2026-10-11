#include "gnss.h"

#include <cstdlib>
#include <cstring>

namespace tracker {
namespace {

// Tage seit 1970-01-01 (proleptisch gregorianisch, ohne Zeitzonen).
int32_t days_from_civil(int year, int month, int day) {
  year -= month <= 2;
  const int era = (year >= 0 ? year : year - 399) / 400;
  const int yoe = year - era * 400;
  const int doy = (153 * (month + (month > 2 ? -3 : 9)) + 2) / 5 + day - 1;
  const int doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return static_cast<int32_t>(era) * 146097 + doe - 719468;
}

// Liest das n-te Komma-Feld (0-basiert) in einen Puffer. Leere Felder ⇒ "".
bool field_at(const char* line, int index, char* out, size_t capacity) {
  const char* start = line;
  for (int i = 0; i < index; ++i) {
    const char* comma = std::strchr(start, ',');
    if (comma == nullptr) return false;
    start = comma + 1;
  }
  const char* end = std::strchr(start, ',');
  const size_t length = end ? static_cast<size_t>(end - start) : std::strlen(start);
  if (length >= capacity) return false;
  std::memcpy(out, start, length);
  out[length] = '\0';
  return true;
}

bool parse_utc(const char* text, uint32_t& epoch_out) {
  // Format: YYYYMMDDhhmmss(.sss)
  if (std::strlen(text) < 14) return false;
  for (int i = 0; i < 14; ++i) {
    if (text[i] < '0' || text[i] > '9') return false;
  }
  char buffer[5];
  std::memcpy(buffer, text, 4);
  buffer[4] = '\0';
  const int year = std::atoi(buffer);
  std::memcpy(buffer, text + 4, 2);
  buffer[2] = '\0';
  const int month = std::atoi(buffer);
  const int day = std::atoi(text + 6) / 1000000;         // DDhhmmss → DD
  const int hour = (std::atoi(text + 6) / 10000) % 100;  // DDhhmmss → hh
  const int minute = (std::atoi(text + 6) / 100) % 100;
  const int second = std::atoi(text + 6) % 100;
  if (month < 1 || month > 12 || day < 1 || day > 31) return false;
  if (hour > 23 || minute > 59 || second > 60) return false;
  epoch_out = utc_to_epoch(year, month, day, hour, minute, second);
  return true;
}

}  // namespace

uint32_t utc_to_epoch(int year, int month, int day, int hour, int minute, int second) {
  const int32_t days = days_from_civil(year, month, day);
  return static_cast<uint32_t>(days) * 86400u +
         static_cast<uint32_t>(hour) * 3600u +
         static_cast<uint32_t>(minute) * 60u +
         static_cast<uint32_t>(second);
}

bool parse_cgnsinf(const char* line, GnssFix& fix) {
  if (line == nullptr) return false;
  const char* payload = std::strstr(line, "+CGNSINF:");
  if (payload != nullptr) {
    payload += std::strlen("+CGNSINF:");
  } else {
    payload = line;  // auch nackte Feldlisten akzeptieren (Tests)
  }
  while (*payload == ' ') ++payload;

  char field[32];

  if (!field_at(payload, 0, field, sizeof(field)) || field[0] != '1') return false;  // run
  if (!field_at(payload, 1, field, sizeof(field)) || field[0] != '1') return false;  // fix

  double latitude = 0.0;
  double longitude = 0.0;
  if (!field_at(payload, 3, field, sizeof(field)) || field[0] == '\0') return false;
  latitude = std::atof(field);
  if (!field_at(payload, 4, field, sizeof(field)) || field[0] == '\0') return false;
  longitude = std::atof(field);
  if (latitude == 0.0 && longitude == 0.0) return false;  // 0/0 = kein Fix

  float hdop = 0.0f;
  if (field_at(payload, 10, field, sizeof(field)) && field[0] != '\0') {
    hdop = static_cast<float>(std::atof(field));
  }

  uint32_t epoch = 0;
  if (field_at(payload, 2, field, sizeof(field)) && field[0] != '\0') {
    parse_utc(field, epoch);  // Zeit ist optional
  }

  fix.valid = true;
  fix.latitude = latitude;
  fix.longitude = longitude;
  fix.hdop = hdop;
  fix.epoch_s = epoch;
  return true;
}

}  // namespace tracker
