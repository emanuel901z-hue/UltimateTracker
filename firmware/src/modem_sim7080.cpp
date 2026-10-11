#include "modem_sim7080.h"

#include <cstring>

#include "gnss.h"
#include "pins.h"

namespace tracker {
namespace {

constexpr uint32_t kDefaultBaud = 115200;

// AT+CGNSINF liefert mehrere Zeilen; wir lesen bis zu diesem Limit.
constexpr size_t kResponseBuffer = 512;

}  // namespace

Sim7080Modem::Sim7080Modem(Stream& serial) : serial_(serial) {
  error_[0] = '\0';
}

void Sim7080Modem::setError(const char* text) {
  std::strncpy(error_, text, sizeof(error_) - 1);
  error_[sizeof(error_) - 1] = '\0';
}

void Sim7080Modem::clearInput() {
  while (serial_.available()) serial_.read();
}

bool Sim7080Modem::waitFor(const char* expect, uint32_t timeout_ms) {
  char buffer[kResponseBuffer];
  size_t length = 0;
  const uint32_t start = millis();
  while (millis() - start < timeout_ms) {
    while (serial_.available()) {
      const int value = serial_.read();
      if (value < 0) break;
      if (length < sizeof(buffer) - 1) {
        buffer[length++] = static_cast<char>(value);
        buffer[length] = '\0';
      }
      if (std::strstr(buffer, expect) != nullptr) return true;
    }
    delay(5);
  }
  return false;
}

bool Sim7080Modem::sendAt(const char* command, const char* expect, uint32_t timeout_ms) {
  clearInput();
  serial_.print(command);
  serial_.print("\r\n");
  return waitFor(expect, timeout_ms);
}

bool Sim7080Modem::begin() {
  // 1) Modem einschalten: PWRKEY (GPIO 41) 128 ms pulsieren (LilyGO-Vorgabe),
  //    danach auf "SMS Ready"/AT-Bereitschaft warten.
  //    TODO(Hardware): Power-Zyklus + Rail-Handling mit M1/M3 messen (B1).
  pinMode(PIN_MODEM_PWRKEY, OUTPUT);
  digitalWrite(PIN_MODEM_PWRKEY, LOW);
  delay(128);
  digitalWrite(PIN_MODEM_PWRKEY, HIGH);

  const uint32_t start = millis();
  while (millis() - start < 20000) {
    if (sendAt("AT", "OK", 1000)) break;
    delay(500);
  }
  if (!sendAt("AT", "OK", 1000)) {
    setError("Modem antwortet nicht auf AT");
    return false;
  }

  // 2) Echo aus, Fehlerausgabe an
  sendAt("ATE0", "OK");
  sendAt("AT+CMEE=1", "OK");

  // 3) Netzmodus: LTE-M bevorzugen (kürzere Latenz als NB-IoT, docs/decisions.md)
  sendAt("AT+CNMP=38", "OK");   // LTE only
  sendAt("AT+CMNB=1", "OK");    // Cat-M1 (Fallback NB-IoT per Config möglich)

  // 4) Auf Netzregistrierung warten
  const uint32_t reg_start = millis();
  while (millis() - reg_start < 60000) {
    if (sendAt("AT+CEREG?", "0,1", 2000) || sendAt("AT+CEREG?", "0,5", 2000)) {
      return true;
    }
    delay(1000);
  }
  setError("keine Netzregistrierung");
  return false;
}

void Sim7080Modem::end(ModemPowerMode mode) {
  switch (mode) {
    case ModemPowerMode::Off:
      // Modem komplett ausschalten (B1, Variante 3) – spart auch PSM-Leckströme.
      sendAt("AT+CPOWD=1", "POWER DOWN", 5000);
      break;
    case ModemPowerMode::Psm:
      // PSM mit langem TAU; die Werte werden vom Netz ggf. angepasst.
      sendAt("AT+CPSMS=1,,,\"00101100\",\"00000010\"", "OK", 3000);
      break;
    case ModemPowerMode::Edrx:
      // eDRX: erreichbar bleiben (RI-Wake möglich), kostet Ruhestrom.
      sendAt("AT+CEDRXS=2,4,\"0100\"", "OK", 3000);
      break;
  }
}

bool Sim7080Modem::isRegistered() {
  return sendAt("AT+CEREG?", "0,1", 2000) || sendAt("AT+CEREG?", "0,5", 2000);
}

NetworkInfo Sim7080Modem::networkInfo() {
  NetworkInfo info;
  info.registered = isRegistered();
  if (sendAt("AT+CSQ", "+CSQ:", 2000)) {
    // Antwort steht im Puffer; der Mock/Testpfad nutzt diese Klasse nicht.
    info.signal_quality = -1;
  }
  return info;
}

bool Sim7080Modem::acquireFix(GnssFix& fix, uint32_t timeout_ms) {
  // Aktive GNSS-Antenne versorgen – ohne diesen Schritt gibt es keinen Fix
  // (LilyGO-Hinweis, docs/hardware-review.md Abschnitt 3).
  sendAt("AT+SGPIO=0,5,1,1", "OK", 3000);
  if (!sendAt("AT+CGNSPWR=1", "OK", 5000)) {
    setError("GNSS lässt sich nicht einschalten");
    sendAt("AT+SGPIO=0,5,1,0", "OK", 3000);
    return false;
  }

  const uint32_t start = millis();
  bool found = false;
  while (millis() - start < timeout_ms) {
    clearInput();
    serial_.print("AT+CGNSINF\r\n");
    if (waitFor("+CGNSINF:", 5000)) {
      // Die Zeile steht im seriellen Puffer; für die Auswertung erneut lesen.
      // TODO(Hardware): Antwortpuffer direkt aus waitFor() zurückgeben, statt
      // hier eine zweite Abfrage zu fahren (aktuell bewusst simpel gehalten).
      if (sendAt("AT+CGNSINF", "+CGNSINF:", 5000)) {
        // Platzhalter: echte Zeile über den Puffer-Parser (gnss.h) auswerten.
        // parse_cgnsinf(buffer, fix) – siehe test_gnss für das Format.
      }
    }
    delay(1000);
  }

  sendAt("AT+CGNSPWR=0", "OK", 3000);
  sendAt("AT+SGPIO=0,5,1,0", "OK", 3000);

  if (!found) {
    setError("kein GNSS-Fix innerhalb des Timeouts");
    return false;
  }
  fix.fix_time_ms = millis() - start;
  return true;
}

bool Sim7080Modem::httpRequest(const HttpRequest& request, HttpResponse& response) {
  // SIM7080G-eigene HTTP-Engine (spart RAM und einen eigenen TCP-Stack):
  //   AT+SHCONF="URL","<host>"
  //   AT+SHCONF="BODYLEN",<max>
  //   AT+SHCONF="HEADERLEN",<max>
  //   AT+SHBOD=<len>,<timeout>          (nur POST)
  //   AT+SHREQ="<url>",<method>         (1=GET, 3=POST)  → +SHREQ: "…",<status>,<len>
  //   AT+SHREAD=0,<len>                 → Body
  //   AT+SHDISC
  // TODO(Hardware): Sequenz implementieren und gegen die Bridge testen (M6).
  (void)request;
  response.status = 0;
  response.body.clear();
  setError("HTTP-Engine noch nicht implementiert (Hardware-Phase, M6)");
  return false;
}

}  // namespace tracker
