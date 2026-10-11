// mock_modem.h – skriptbasierter Modem-Ersatz für die Host-Tests.
//
// Damit läuft der komplette Wake-Zyklus (GNSS → Sync → Download → Schlaf)
// ohne Hardware (docs/simulation.md).

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "modem.h"

namespace tracker {

struct ScriptedResponse {
  std::string url_contains;  // Antwort gilt für URLs, die das enthalten ("" = alle)
  int status;                // HTTP-Status (0 = Transportfehler)
  std::string body;

  ScriptedResponse() : status(200) {}
  ScriptedResponse(const std::string& match, int http_status, const std::string& payload)
      : url_contains(match), status(http_status), body(payload) {}
};

class MockModem : public IModem {
 public:
  // --- Steuerung durch den Test ---
  bool begin_ok;
  bool registered;
  bool fix_ok;
  GnssFix fix;                       // wird bei fix_ok=true zurückgegeben
  std::vector<ScriptedResponse> responses;

  // --- Aufzeichnung für Assertions ---
  int begin_calls;
  int end_calls;
  int fix_calls;
  std::vector<std::string> requests;       // alle angefragten URLs
  std::vector<std::string> posted_bodies;  // Bodies der POSTs
  ModemPowerMode last_power_mode;

  MockModem()
      : begin_ok(true), registered(true), fix_ok(true), begin_calls(0), end_calls(0),
        fix_calls(0), last_power_mode(ModemPowerMode::Off) {}

  bool begin() override {
    ++begin_calls;
    return begin_ok;
  }

  void end(ModemPowerMode mode) override {
    ++end_calls;
    last_power_mode = mode;
  }

  bool isRegistered() override { return registered; }

  NetworkInfo networkInfo() override {
    NetworkInfo info;
    info.registered = registered;
    info.signal_quality = registered ? 20 : 99;
    return info;
  }

  bool acquireFix(GnssFix& out, uint32_t /*timeout_ms*/) override {
    ++fix_calls;
    if (!fix_ok) return false;
    out = fix;
    out.valid = true;
    return true;
  }

  bool httpRequest(const HttpRequest& request, HttpResponse& response) override {
    requests.push_back(std::string(request.url ? request.url : ""));
    if (request.body && request.body_len > 0) {
      posted_bodies.push_back(std::string(request.body, request.body_len));
    }
    const std::string url = request.url ? request.url : "";
    for (size_t i = 0; i < responses.size(); ++i) {
      if (responses[i].url_contains.empty() || url.find(responses[i].url_contains) != std::string::npos) {
        response.status = responses[i].status;
        response.body = responses[i].body;
        return responses[i].status != 0;
      }
    }
    response.status = 404;
    response.body.clear();
    return false;
  }

  const char* lastError() const override { return "mock"; }
};

}  // namespace tracker
