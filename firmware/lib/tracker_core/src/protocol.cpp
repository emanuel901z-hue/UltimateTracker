#include "protocol.h"

#include <ArduinoJson.h>

namespace tracker {

std::string build_sync_request(const SyncRequest& request) {
  JsonDocument doc;
  doc["device_id"] = request.device_id;
  if (request.battery_percent >= 0.0f) {
    doc["battery"] = request.battery_percent;
  }
  doc["wake_reason"] = request.wake_reason;
  doc["fw"] = request.firmware;

  if (request.position.valid) {
    JsonObject position = doc["position"].to<JsonObject>();
    position["lat"] = request.position.latitude;
    position["lon"] = request.position.longitude;
    position["hdop"] = request.position.hdop;
    position["ts"] = request.position.epoch_s;
  }

  std::string out;
  serializeJson(doc, out);
  return out;
}

bool parse_sync_response(const std::string& json, SyncResponse& out) {
  JsonDocument doc;
  const DeserializationError error = deserializeJson(doc, json);
  if (error) return false;
  if (!doc.is<JsonObject>()) return false;

  out.search_mode = doc["search_mode"] | false;
  out.next_poll_s = doc["next_poll_s"] | 900u;

  out.message = PendingMessage{};
  JsonVariantConst message = doc["message"];
  if (message.is<JsonObjectConst>()) {
    out.message.present = true;
    out.message.id = std::string(message["id"] | "");
    out.message.url = std::string(message["url"] | "");
    out.message.format = std::string(message["format"] | "bin");
    out.message.size = message["size"] | 0u;
  }

  out.ota = FirmwareOffer{};
  JsonVariantConst ota = doc["ota"];
  if (ota.is<JsonObjectConst>()) {
    out.ota.present = true;
    out.ota.version = std::string(ota["version"] | "");
    out.ota.url = std::string(ota["url"] | "");
    out.ota.sha256 = std::string(ota["sha256"] | "");
    out.ota.size = ota["size"] | 0u;
  }

  out.audio_volume = -1;
  JsonVariantConst config = doc["config"];
  if (config.is<JsonObjectConst>() && config["audio_volume"].is<int>()) {
    out.audio_volume = config["audio_volume"].as<int>();
  }

  out.min_fw = std::string(doc["min_fw"] | "");
  return true;
}

}  // namespace tracker
