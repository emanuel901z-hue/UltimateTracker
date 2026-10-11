// nvs_config_store.h – Gerätekonfiguration im NVS (ESP32-Seite).
//
// Gegenstück zu MemoryConfigStorage (Host-Tests). Speichert die POD-Struktur
// als Blob; Provisioning erfolgt über den Serial-Kanal (siehe src/main.cpp).

#pragma once

#include <Preferences.h>

#include "config_store.h"

namespace tracker {

class NvsConfigStorage : public IConfigStorage {
 public:
  bool load(DeviceConfig& out) override;
  bool save(const DeviceConfig& config) override;
  void clear() override;
};

}  // namespace tracker
