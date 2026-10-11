// ota.h – OTA-Update-Logik (docs/optimizations.md B7).
//
// Der Server liefert im Sync ein Firmware-Angebot (Version, URL, SHA256, Größe);
// hier steckt die Entscheidung und die Vorprüfung – host-testbar. Das eigentliche
// Schreiben in den Flash-Slot (`Update`/esp_ota) macht die ESP32-Glue in src/.

#pragma once

#include <cstdint>
#include <string>

namespace tracker {

struct FirmwareOffer {
  bool present;
  std::string version;
  std::string url;
  std::string sha256;  // 64 Hex-Zeichen
  uint32_t size;

  FirmwareOffer() : present(false), size(0) {}
};

// Segmentweiser, numerischer Vergleich ("1.2.3"). true, wenn available > current.
bool version_is_newer(const std::string& available, const std::string& current);

// Vorprüfung des Angebots (Größe, Hash-Format, Pflichtfelder).
bool ota_offer_is_sane(const FirmwareOffer& offer, uint32_t max_size_bytes, std::string& error);

}  // namespace tracker
