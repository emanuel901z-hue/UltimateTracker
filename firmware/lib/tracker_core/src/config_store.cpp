#include "config_store.h"

#include <ArduinoJson.h>

#include <cstring>

namespace tracker {
namespace {

void copy_bounded(char* target, size_t capacity, const std::string& value) {
  const size_t length = value.size() < (capacity - 1) ? value.size() : (capacity - 1);
  std::memcpy(target, value.c_str(), length);
  target[length] = '\0';
}

}  // namespace

bool config_is_valid(const DeviceConfig& config, std::string& error) {
  if (config.device_id[0] == '\0') {
    error = "device_id fehlt";
    return false;
  }
  if (std::strncmp(config.server_url, "http://", 7) != 0 &&
      std::strncmp(config.server_url, "https://", 8) != 0) {
    error = "server_url muss mit http:// oder https:// beginnen";
    return false;
  }
  if (config.device_token[0] == '\0') {
    error = "device_token fehlt";
    return false;
  }
  if (config.poll_interval_s < 30 || config.poll_interval_s > 86400) {
    error = "poll_interval_s außerhalb 30..86400";
    return false;
  }
  if (config.audio_volume > 100) {
    error = "audio_volume muss 0..100 sein";
    return false;
  }
  return true;
}

bool parse_provisioning_command(const std::string& json, DeviceConfig& config,
                                std::string& error) {
  JsonDocument doc;
  const DeserializationError parse_error = deserializeJson(doc, json);
  if (parse_error) {
    error = "JSON ungültig";
    return false;
  }
  if (!doc.is<JsonObject>()) {
    error = "JSON-Objekt erwartet";
    return false;
  }
  const char* cmd = doc["cmd"] | "";
  if (std::strcmp(cmd, "provision") != 0) {
    error = "cmd muss \"provision\" sein";
    return false;
  }

  if (doc["device_id"].is<const char*>()) copy_bounded(config.device_id, kDeviceIdMax, doc["device_id"].as<const char*>());
  if (doc["server"].is<const char*>()) copy_bounded(config.server_url, kServerUrlMax, doc["server"].as<const char*>());
  if (doc["token"].is<const char*>()) copy_bounded(config.device_token, kTokenMax, doc["token"].as<const char*>());
  if (doc["poll_s"].is<uint32_t>()) config.poll_interval_s = doc["poll_s"].as<uint32_t>();
  if (doc["search_poll_s"].is<uint32_t>()) config.search_poll_interval_s = doc["search_poll_s"].as<uint32_t>();
  if (doc["volume"].is<uint8_t>()) config.audio_volume = doc["volume"].as<uint8_t>();
  if (doc["modem_mode"].is<uint8_t>()) {
    const uint8_t mode = doc["modem_mode"].as<uint8_t>();
    if (mode <= 2) config.modem_power_mode = static_cast<ModemPowerMode>(mode);
  }

  if (!config_is_valid(config, error)) return false;
  config.valid = true;
  return true;
}

}  // namespace tracker
