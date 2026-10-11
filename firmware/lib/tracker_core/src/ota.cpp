#include "ota.h"

#include <cstdlib>

namespace tracker {
namespace {

constexpr int kMaxVersionPart = 9999;

bool parse_version(const std::string& text, int parts[3]) {
  parts[0] = 0;
  parts[1] = 0;
  parts[2] = 0;
  if (text.empty()) return false;

  size_t pos = 0;
  for (int index = 0; index < 3; ++index) {
    const size_t dot = text.find('.', pos);
    const std::string segment =
        (dot == std::string::npos) ? text.substr(pos) : text.substr(pos, dot - pos);
    if (segment.empty() || segment.size() > 4) return false;
    for (size_t i = 0; i < segment.size(); ++i) {
      if (segment[i] < '0' || segment[i] > '9') return false;
    }
    const long value = std::strtol(segment.c_str(), nullptr, 10);
    if (value < 0 || value > kMaxVersionPart) return false;
    parts[index] = static_cast<int>(value);
    if (dot == std::string::npos) return true;  // Rest bleibt 0
    pos = dot + 1;
  }
  return true;
}

}  // namespace

bool version_is_newer(const std::string& available, const std::string& current) {
  int a[3];
  int c[3];
  if (!parse_version(available, a) || !parse_version(current, c)) return false;
  for (int i = 0; i < 3; ++i) {
    if (a[i] != c[i]) return a[i] > c[i];
  }
  return false;
}

bool ota_offer_is_sane(const FirmwareOffer& offer, uint32_t max_size_bytes, std::string& error) {
  if (!offer.present) {
    error = "kein Angebot";
    return false;
  }
  if (offer.version.empty()) {
    error = "Version fehlt";
    return false;
  }
  if (offer.url.empty()) {
    error = "URL fehlt";
    return false;
  }
  if (offer.size == 0) {
    error = "Größe ist 0";
    return false;
  }
  if (offer.size > max_size_bytes) {
    error = "Firmware größer als erlaubt";
    return false;
  }
  if (offer.sha256.size() != 64) {
    error = "sha256 muss 64 Hex-Zeichen haben";
    return false;
  }
  for (size_t i = 0; i < offer.sha256.size(); ++i) {
    const char c = offer.sha256[i];
    const bool is_hex = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
    if (!is_hex) {
      error = "sha256 enthält Nicht-Hex-Zeichen";
      return false;
    }
  }
  return true;
}

}  // namespace tracker
