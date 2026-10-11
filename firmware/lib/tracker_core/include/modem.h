// modem.h – Abstraktion des SIM7080G (Transport + GNSS).
//
// Zweck: Der Wake-Zyklus (wake_cycle.h) soll ohne Hardware testbar sein.
// Zwei Implementierungen:
//   * Sim7080Modem  – ESP32/TinyGSM (src/modem_sim7080.cpp), braucht Hardware
//   * MockModem     – skriptbasierte Antworten für die Host-Tests (mock_modem.h)
//
// Reine Schnittstelle → C++11-kompatibel, keine Arduino-Abhängigkeit.

#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

namespace tracker {

// Modem-Power-Strategie (docs/optimizations.md B1)
enum class ModemPowerMode : uint8_t { Off = 0, Psm = 1, Edrx = 2 };

struct GnssFix {
  bool valid;
  double latitude;
  double longitude;
  float hdop;
  uint32_t epoch_s;     // Zeit aus dem Netz (oder 0 = unbekannt)
  uint32_t fix_time_ms; // Dauer bis zum Fix (für die Messung M3)

  GnssFix() : valid(false), latitude(0.0), longitude(0.0), hdop(0.0f), epoch_s(0), fix_time_ms(0) {}
};

struct NetworkInfo {
  bool registered;
  int8_t signal_quality; // CSQ 0..31, 99 = unbekannt

  NetworkInfo() : registered(false), signal_quality(99) {}
};

struct HttpRequest {
  const char* method;      // "GET" oder "POST"
  const char* url;         // vollständige URL
  const char* body;        // nullptr bei GET
  size_t body_len;
  const char* content_type;

  HttpRequest() : method("GET"), url(""), body(nullptr), body_len(0), content_type(nullptr) {}
};

struct HttpResponse {
  int status;       // 0 = Transportfehler
  std::string body;

  HttpResponse() : status(0) {}
};

class IModem {
 public:
  virtual ~IModem() {}

  // Modem einschalten und AT-Bereitschaft herstellen.
  virtual bool begin() = 0;
  // Modem ausschalten bzw. in den konfigurierten Schlafmodus versetzen.
  virtual void end(ModemPowerMode mode) = 0;

  virtual bool isRegistered() = 0;
  virtual NetworkInfo networkInfo() = 0;

  // GNSS: aktive Antenne ein (AT+SGPIO=0,5,1,1), GNSS an (AT+CGNSPWR=1),
  // Fix lesen (AT+CGNSINF), danach wieder aus (LTE/GNSS sind exklusiv).
  virtual bool acquireFix(GnssFix& fix, uint32_t timeout_ms) = 0;

  // HTTP über die Modem-eigene HTTP-Engine (spart RAM und einen TCP-Stack).
  virtual bool httpRequest(const HttpRequest& request, HttpResponse& response) = 0;

  virtual const char* lastError() const = 0;
};

}  // namespace tracker
