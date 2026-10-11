// config_store.h – Gerätekonfiguration (Provisioning, docs/optimizations.md B6).
//
// Persistenz abstrahiert: NVS auf dem ESP32 (src/nvs_config_store.cpp),
// Speicher-im-RAM für die Host-Tests (MemoryConfigStorage hier).
// Provisioning per USB-Serial mit einem JSON-Kommando.

#pragma once

#include <cstdint>
#include <string>

#include "modem.h"

namespace tracker {

constexpr size_t kDeviceIdMax = 32;
constexpr size_t kServerUrlMax = 96;
constexpr size_t kTokenMax = 64;

struct DeviceConfig {
  char device_id[kDeviceIdMax];   // IMEI
  char server_url[kServerUrlMax]; // z. B. http://192.168.1.10:8085
  char device_token[kTokenMax];
  uint32_t poll_interval_s;
  uint32_t search_poll_interval_s;
  uint8_t audio_volume;           // Prozent (Lautstärkegrenze)
  ModemPowerMode modem_power_mode;
  bool valid;

  DeviceConfig()
      : poll_interval_s(900), search_poll_interval_s(60), audio_volume(80),
        modem_power_mode(ModemPowerMode::Off), valid(false) {
    device_id[0] = '\0';
    server_url[0] = '\0';
    device_token[0] = '\0';
  }
};

class IConfigStorage {
 public:
  virtual ~IConfigStorage() {}
  virtual bool load(DeviceConfig& out) = 0;
  virtual bool save(const DeviceConfig& config) = 0;
  virtual void clear() = 0;
};

// Prüft Pflichtfelder/Längen. Bei false steht in `error` der Grund.
bool config_is_valid(const DeviceConfig& config, std::string& error);

// Parst ein Provisioning-Kommando:
//   {"cmd":"provision","device_id":"86…","server":"http://host:8085","token":"…",
//    "poll_s":900,"search_poll_s":60,"volume":80,"modem_mode":0}
// Fehlende Felder behalten den Wert aus `config`. Bei false steht in `error` der Grund.
bool parse_provisioning_command(const std::string& json, DeviceConfig& config, std::string& error);

// Einfache Speicher-Implementierung (Host-Tests).
class MemoryConfigStorage : public IConfigStorage {
 public:
  MemoryConfigStorage() : has_value_(false) {}

  bool load(DeviceConfig& out) override {
    if (!has_value_) return false;
    out = stored_;
    return true;
  }

  bool save(const DeviceConfig& config) override {
    stored_ = config;
    has_value_ = true;
    return true;
  }

  void clear() override { has_value_ = false; }

 private:
  DeviceConfig stored_;
  bool has_value_;
};

}  // namespace tracker
