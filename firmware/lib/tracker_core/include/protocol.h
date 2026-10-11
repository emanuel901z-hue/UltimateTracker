// protocol.h – Bauen/Parsen der Sync-Nachrichten (A5/C1).
//
// Ein Roundtrip pro Wake: Position und Status hoch, Nachricht/Konfiguration/OTA
// runter. Nutzt ArduinoJson (läuft auch auf dem Host für die Tests).
// Endpunkt und Format: docs/architecture.md (Abschnitt 3.2).

#pragma once

#include <cstdint>
#include <string>

#include "ota.h"

namespace tracker {

struct Position {
  bool valid;
  double latitude;
  double longitude;
  float hdop;
  uint32_t epoch_s;

  // Explizite Konstruktoren: der Arduino-Build nutzt C++11, dort sind
  // Default-Member-Initialisierer kein Aggregat.
  Position() : valid(false), latitude(0.0), longitude(0.0), hdop(0.0f), epoch_s(0) {}
  Position(bool isValid, double lat, double lon, float hdopValue, uint32_t timestamp)
      : valid(isValid), latitude(lat), longitude(lon), hdop(hdopValue), epoch_s(timestamp) {}
};

struct SyncRequest {
  std::string device_id;
  float battery_percent;  // < 0 = unbekannt
  const char* wake_reason;
  const char* firmware;
  Position position;

  SyncRequest() : battery_percent(-1.0f), wake_reason("timer"), firmware("0.0.0") {}
};

struct PendingMessage {
  bool present;
  std::string id;
  std::string url;
  std::string format;
  uint32_t size;

  PendingMessage() : present(false), size(0) {}
};

struct SyncResponse {
  bool search_mode;
  uint32_t next_poll_s;
  PendingMessage message;
  FirmwareOffer ota;
  int audio_volume;      // -1 = nicht gesetzt
  std::string min_fw;    // minimale Firmware-Version, die der Server erwartet

  SyncResponse() : search_mode(false), next_poll_s(900), audio_volume(-1) {}
};

// Baut den JSON-Body für POST /api/v1/device/sync.
std::string build_sync_request(const SyncRequest& request);

// Parst die Antwort; false bei fehlerhaftem JSON.
bool parse_sync_response(const std::string& json, SyncResponse& out);

}  // namespace tracker
