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
  return true;
}

}  // namespace tracker
