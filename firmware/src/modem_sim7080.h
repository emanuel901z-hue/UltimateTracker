// modem_sim7080.h – SIM7080G-Anbindung über den AT-Kanal (ESP32-Seite).
//
// Implementiert die IModem-Schnittstelle mit den AT-Befehlen des SIM7080G.
// Status: Skelett – die Sequenzen sind dokumentiert und vollständig angelegt,
// die Hardware-Validierung erfolgt in der Inbetriebnahme (M3/M4, docs/measurement-plan.md).

#pragma once

#include <Arduino.h>

#include "modem.h"

namespace tracker {

class Sim7080Modem : public IModem {
 public:
  explicit Sim7080Modem(Stream& serial);

  bool begin() override;
  void end(ModemPowerMode mode) override;

  bool isRegistered() override;
  NetworkInfo networkInfo() override;

  bool acquireFix(GnssFix& fix, uint32_t timeout_ms) override;
  bool httpRequest(const HttpRequest& request, HttpResponse& response) override;

  const char* lastError() const override { return error_; }

 private:
  bool sendAt(const char* command, const char* expect = "OK", uint32_t timeout_ms = 2000);
  bool waitFor(const char* expect, uint32_t timeout_ms);
  void clearInput();
  void setError(const char* text);

  Stream& serial_;
  char error_[64];
};

}  // namespace tracker
