#include "bringup.h"

// Der Selbsttest wird nur in der Bring-up-Umgebung gebaut (platformio.ini).
#if UT_BRINGUP

#include <Wire.h>
#include <math.h>

#include <NimBLEDevice.h>
#include <WiFi.h>

#include "config.h"
#include "driver/i2s.h"
#include "esp_sleep.h"
#include "gnss.h"
#include "pins.h"

// Die PMU-Bibliothek (XPowersLib) ist nur in der Bring-up-Umgebung verlinkt
// (PlatformIO-Flag UT_HAS_PMU_LIB, siehe platformio.ini).
#ifndef UT_HAS_PMU_LIB
#define UT_HAS_PMU_LIB 0
#endif

#if UT_HAS_PMU_LIB
#include <XPowersLib.h>
#endif

namespace bringup {
namespace {

constexpr uint8_t kLis3dhAddress = 0x18;   // SA0 = GND
constexpr uint8_t kPmuAddress = 0x34;      // AXP2101

const char* yes_no(bool value) { return value ? "OK" : "FEHLER"; }

void line(Stream& console, const char* text) {
  console.println(text);
}

// --- I2C --------------------------------------------------------------------

bool i2c_present(TwoWire& bus, uint8_t address) {
  bus.beginTransmission(address);
  return bus.endTransmission() == 0;
}

uint8_t i2c_read8(TwoWire& bus, uint8_t address, uint8_t reg) {
  bus.beginTransmission(address);
  bus.write(reg);
  if (bus.endTransmission(false) != 0) return 0xFF;
  if (bus.requestFrom(address, static_cast<uint8_t>(1)) != 1) return 0xFF;
  return bus.read();
}

void i2c_scan_bus(Stream& console, TwoWire& bus, int sda, int scl, const char* label) {
  console.printf("[I2C] Bus %s (SDA=%d, SCL=%d):\n", label, sda, scl);
  bus.begin(sda, scl, 100000);
  delay(20);
  uint8_t found = 0;
  for (uint8_t address = 0x03; address < 0x78; ++address) {
    if (i2c_present(bus, address)) {
      console.printf("      0x%02X gefunden%s\n", address,
                     address == kLis3dhAddress ? " (LIS3DH)"
                                               : (address == kPmuAddress ? " (AXP2101)" : ""));
      ++found;
    }
  }
  console.printf("      %u Gerät(e)\n", found);
}

void i2c_scan(Stream& console) {
  // Zwei getrennte Busse auf diesem Board (Arduino Wire kann nur EINE
  // Pin-Belegung gleichzeitig, deshalb Wire = PMU und Wire1 = Sensoren):
  //   * PMU (AXP2101): SDA=15, SCL=7  – fest verdrahtet, nicht frei nutzbar
  //   * frei für unsere Sensoren: SDA=1, SCL=2 (Kamera-Pins)
  i2c_scan_bus(console, Wire, PIN_PMU_SDA, PIN_PMU_SCL, "PMU (belegt)");
  i2c_scan_bus(console, Wire1, PIN_I2C_SDA, PIN_I2C_SCL, "frei (Sensor)");
}

// --- PMU (AXP2101) ----------------------------------------------------------

void pmu_test(Stream& console) {
  line(console, "[PMU] AXP2101 (Wire, SDA=15, SCL=7):");
  Wire.begin(PIN_PMU_SDA, PIN_PMU_SCL, 100000);
  delay(20);
#if UT_HAS_PMU_LIB
  XPowersPMU pmu;
  if (!pmu.begin(Wire, kPmuAddress, PIN_PMU_SDA, PIN_PMU_SCL)) {
    line(console, "      begin() fehlgeschlagen – Adresse/Bus prüfen");
    return;
  }
  console.printf("      Akku angeschlossen: %s\n", yes_no(pmu.isBatteryConnect()));
  console.printf("      Akkuspannung: %u mV\n", pmu.getBattVoltage());
  console.printf("      lädt: %s\n", yes_no(pmu.isCharging()));
  // Wichtig für die Inbetriebnahme: TS-Pin-Detection deaktivieren, sonst lädt nichts.
  pmu.disableTSPinMeasure();
  line(console, "      TS-Pin-Detection deaktiviert (sonst kein Laden)");
#else
  // Ohne Bibliothek: nur Präsenz + Chip-ID-Register (0x03)
  const uint8_t chip_id = i2c_read8(Wire, kPmuAddress, 0x03);
  console.printf("      Chip-ID-Register 0x03 = 0x%02X (AXP2101 erwartet 0x4A)\n", chip_id);
  line(console, "      (XPowersLib nicht installiert – Spannungswerte erst mit Bibliothek)");
#endif
}

// --- LIS3DH -----------------------------------------------------------------

void lis3dh_test(Stream& console) {
  line(console, "[LIS3DH] Beschleunigungssensor (Wire1, SDA=1, SCL=2):");
  Wire1.begin(PIN_I2C_SDA, PIN_I2C_SCL, 100000);
  delay(20);
  const uint8_t who = i2c_read8(Wire1, kLis3dhAddress, 0x0F);
  console.printf("      WHO_AM_I = 0x%02X (erwartet 0x33) → %s\n", who,
                 who == 0x33 ? "OK" : "FEHLER");
  if (who != 0x33) return;

  // CTRL_REG1 (0x20): 100 Hz, alle Achsen an
  Wire1.beginTransmission(kLis3dhAddress);
  Wire1.write(0x20);
  Wire1.write(0x57);
  Wire1.endTransmission();
  delay(50);

  // Auslesen (OUT_X_L = 0x28, 6 Bytes)
  Wire1.beginTransmission(kLis3dhAddress);
  Wire1.write(0x28 | 0x80);  // Auto-Increment
  if (Wire1.endTransmission(false) != 0 ||
      Wire1.requestFrom(kLis3dhAddress, static_cast<uint8_t>(6)) != 6) {
    line(console, "      Auslesen fehlgeschlagen");
    return;
  }
  int16_t raw[3];
  for (int i = 0; i < 3; ++i) {
    const uint8_t low = Wire1.read();
    const uint8_t high = Wire1.read();
    raw[i] = static_cast<int16_t>((high << 8) | low) >> 4;  // 12 Bit, linksbündig
  }
  // ±2 g → 1 mg/LSB
  console.printf("      X=%d mg  Y=%d mg  Z=%d mg\n", raw[0], raw[1], raw[2]);
  line(console, "      Z sollte bei ruhigem Board ≈ +1000 mg sein (Schwerkraft)");
}

// --- Modem (rohe AT-Ausgaben sind hier gewollt) -----------------------------

String at_query(Stream& modem, const char* command, uint32_t timeout_ms) {
  while (modem.available()) modem.read();
  modem.print(command);
  modem.print("\r\n");
  String response;
  const uint32_t start = millis();
  while (millis() - start < timeout_ms) {
    while (modem.available()) response += static_cast<char>(modem.read());
    if (response.indexOf("OK") >= 0 || response.indexOf("ERROR") >= 0) break;
    delay(10);
  }
  response.replace("\r", "");
  response.trim();
  return response;
}

void modem_test(Stream& modem, Stream& console) {
  line(console, "[Modem] SIM7080G:");
  // Erst prüfen, ob das Modem schon läuft – ein zweiter PWRKEY-Puls bei
  // laufendem Modem verwirrt es (im Selbsttest aufgefallen). Nur einschalten,
  // wenn AT nicht antwortet.
  bool alive = at_query(modem, "AT", 2000).indexOf("OK") >= 0;
  if (!alive) {
    line(console, "      Modem aus → PWRKEY-Puls (128 ms) + warten");
    pinMode(PIN_MODEM_PWRKEY, OUTPUT);
    digitalWrite(PIN_MODEM_PWRKEY, LOW);
    delay(128);
    digitalWrite(PIN_MODEM_PWRKEY, HIGH);
    const uint32_t start = millis();
    while (millis() - start < 20000) {
      if (at_query(modem, "AT", 1500).indexOf("OK") >= 0) {
        alive = true;
        break;
      }
      delay(1000);
    }
  } else {
    line(console, "      Modem läuft bereits (kein PWRKEY-Puls nötig)");
  }

  if (!alive) {
    line(console, "      Modem antwortet nicht – PWRKEY/Rail/Stromversorgung prüfen");
    return;
  }
  at_query(modem, "ATE0", 1000);
  console.printf("      +CCID → %s\n", at_query(modem, "AT+CCID", 3000).c_str());
  console.printf("      +CPIN? → %s\n", at_query(modem, "AT+CPIN?", 3000).c_str());
  console.printf("      +CSQ → %s\n", at_query(modem, "AT+CSQ", 3000).c_str());
  console.printf("      +CEREG? → %s\n", at_query(modem, "AT+CEREG?", 3000).c_str());
  console.printf("      +CPSMS? → %s\n", at_query(modem, "AT+CPSMS?", 3000).c_str());
  console.printf("      +CPSMS=? → %s\n", at_query(modem, "AT+CPSMS=?", 3000).c_str());
  console.printf("      +CEDRXS? → %s\n", at_query(modem, "AT+CEDRXS?", 3000).c_str());
  console.printf("      +CEDRXS=? → %s\n", at_query(modem, "AT+CEDRXS=?", 3000).c_str());
}

void gnss_test(Stream& modem, Stream& console) {
  line(console, "[GNSS] Aktive Antenne + Fix (bis 60 s):");
  console.printf("      Antenne ein → %s\n", at_query(modem, "AT+SGPIO=0,5,1,1", 3000).c_str());
  console.printf("      GNSS an → %s\n", at_query(modem, "AT+CGNSPWR=1", 5000).c_str());

  const uint32_t start = millis();
  bool got_fix = false;
  while (millis() - start < 60000) {
    const String response = at_query(modem, "AT+CGNSINF", 5000);
    const int index = response.indexOf("+CGNSINF:");
    if (index >= 0) {
      const String payload = response.substring(index);
      tracker::GnssFix fix;
      if (tracker::parse_cgnsinf(payload.c_str(), fix)) {
        console.printf("      Fix nach %lu s: %.6f, %.6f (hdop %.1f, %lu sats)\n",
                       (millis() - start) / 1000, fix.latitude, fix.longitude, fix.hdop,
                       static_cast<unsigned long>(fix.epoch_s));
        got_fix = true;
        break;
      }
      console.printf("      %s\n", payload.c_str());  // Rohzeile zum Mitlesen
    }
    delay(2000);
  }
  if (!got_fix) line(console, "      kein Fix – Antenne/Stecker/Sichtverbindung prüfen");

  at_query(modem, "AT+CGNSPWR=0", 3000);
  at_query(modem, "AT+SGPIO=0,5,1,0", 3000);
}

// --- Audio ------------------------------------------------------------------

void tone_test(Stream& console) {
  line(console, "[I2S] 1 kHz-Ton über den MAX98357A (1 s):");
  const i2s_port_t port = I2S_NUM_0;
  i2s_config_t config = {};
  config.mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_TX);
  config.sample_rate = 16000;
  config.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  config.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
  config.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  config.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  config.dma_buf_count = 4;
  config.dma_buf_len = 256;
  config.use_apll = false;

  if (i2s_driver_install(port, &config, 0, nullptr) != ESP_OK) {
    line(console, "      i2s_driver_install fehlgeschlagen");
    return;
  }
  i2s_pin_config_t pins = {};
  pins.bck_io_num = PIN_I2S_BCLK;
  pins.ws_io_num = PIN_I2S_WS;
  pins.data_out_num = PIN_I2S_DOUT;
  pins.data_in_num = I2S_PIN_NO_CHANGE;
  i2s_set_pin(port, &pins);

  digitalWrite(PIN_AMP_SD, HIGH);  // Verstärker aktiv (Left-Channel)
  int16_t buffer[128];
  const size_t total = config.sample_rate;  // 1 s
  size_t written = 0;
  for (size_t offset = 0; offset < total; offset += 128) {
    for (int i = 0; i < 128; ++i) {
      buffer[i] = static_cast<int16_t>(8000.0f * sinf(2.0f * PI * 1000.0f *
                                                     static_cast<float>(offset + i) /
                                                     static_cast<float>(config.sample_rate)));
    }
    i2s_write(port, buffer, sizeof(buffer), &written, portMAX_DELAY);
  }
  digitalWrite(PIN_AMP_SD, LOW);
  i2s_driver_uninstall(port);
  line(console, "      fertig – Ton gehört?");
}

void mic_test(Stream& console) {
  line(console, "[I2S] Mikrofon-Pegel (2 s, bitte sprechen):");
  digitalWrite(PIN_MIC_POWER, HIGH);  // Load-Switch an
  delay(20);

  const i2s_port_t port = I2S_NUM_0;
  i2s_config_t config = {};
  config.mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_RX);
  config.sample_rate = 16000;
  config.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  config.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
  config.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  config.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  config.dma_buf_count = 4;
  config.dma_buf_len = 256;
  config.use_apll = false;

  if (i2s_driver_install(port, &config, 0, nullptr) != ESP_OK) {
    line(console, "      i2s_driver_install fehlgeschlagen");
    digitalWrite(PIN_MIC_POWER, LOW);
    return;
  }
  i2s_pin_config_t pins = {};
  pins.bck_io_num = PIN_I2S_BCLK;
  pins.ws_io_num = PIN_I2S_WS;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = PIN_I2S_DIN;
  i2s_set_pin(port, &pins);

  int peak = 0;
  int16_t buffer[256];
  size_t read_bytes = 0;
  const uint32_t start = millis();
  while (millis() - start < 2000) {
    if (i2s_read(port, buffer, sizeof(buffer), &read_bytes, 200) != ESP_OK) continue;
    for (size_t i = 0; i < read_bytes / 2; ++i) {
      const int value = buffer[i] < 0 ? -buffer[i] : buffer[i];
      if (value > peak) peak = value;
    }
  }
  i2s_driver_uninstall(port);
  digitalWrite(PIN_MIC_POWER, LOW);
  console.printf("      Spitzenpegel: %d (0 = kein Signal, > 500 = Sprache erkannt)\n", peak);
}

// --- Piezo und Taster -------------------------------------------------------

void piezo_test(Stream& console) {
  line(console, "[Piezo] 4 kHz im BTL-Gegentakt (1 s):");
  // Hinweis: Software-Toggle nur für den Bring-up-Test. In der Produktion
  // laufen zwei LEDC-Kanäle gegenphasig (docs/optimizations.md B5/B8).
  pinMode(PIN_PIEZO_A, OUTPUT);
  pinMode(PIN_PIEZO_B, OUTPUT);
  const uint32_t half_us = 125;  // 4 kHz → 125 µs pro Halbwelle
  const uint32_t cycles = 4000;
  for (uint32_t i = 0; i < cycles; ++i) {
    digitalWrite(PIN_PIEZO_A, HIGH);
    digitalWrite(PIN_PIEZO_B, LOW);
    delayMicroseconds(half_us);
    digitalWrite(PIN_PIEZO_A, LOW);
    digitalWrite(PIN_PIEZO_B, HIGH);
    delayMicroseconds(half_us);
  }
  digitalWrite(PIN_PIEZO_A, LOW);
  digitalWrite(PIN_PIEZO_B, LOW);
  line(console, "      fertig – Ton gehört?");
}

void button_test(Stream& console) {
  line(console, "[Taster] PTT (GPIO 9) – 3 s beobachten:");
  pinMode(PIN_PTT_BUTTON, INPUT_PULLUP);
  const uint32_t start = millis();
  bool seen_low = false;
  while (millis() - start < 3000) {
    if (digitalRead(PIN_PTT_BUTTON) == LOW) {
      seen_low = true;
      break;
    }
    delay(10);
  }
  console.printf("      Taster gedrückt erkannt: %s\n", yes_no(seen_low));
  line(console, "      (ohne Druck ist das normal: dann beim nächsten Durchlauf drücken)");
}

// --- Funk (integrierte PCB-Antenne am Modul) --------------------------------

void wifi_test(Stream& console) {
  line(console, "[WLAN] Scan 2,4 GHz (integrierte PCB-Antenne des WROOM-1):");
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);
  const int count = WiFi.scanNetworks(false, true);
  console.printf("      %d Netz(e) gefunden\n", count);
  for (int i = 0; i < count && i < 8; ++i) {
    console.printf("      %-28s %4d dBm  Kanal %d\n", WiFi.SSID(i).c_str(), WiFi.RSSI(i),
                   WiFi.channel(i));
  }
  if (count == 0) {
    line(console, "      keine Netze – Antennenbereich des Moduls freihalten (kein Metall darüber)");
  }
  WiFi.scanDelete();
  WiFi.mode(WIFI_OFF);
}

void ble_test(Stream& console) {
  line(console, "[BLE] Scan 5 s (integrierte Antenne):");
  NimBLEDevice::init("UT-bringup");
  NimBLEScan* scan = NimBLEDevice::getScan();
  scan->setActiveScan(true);
  scan->setInterval(100);
  scan->setWindow(99);
  const NimBLEScanResults results = scan->getResults(5000, false);
  console.printf("      %d Gerät(e) gefunden\n", results.getCount());
  for (int i = 0; i < results.getCount() && i < 8; ++i) {
    const NimBLEAdvertisedDevice* device = results.getDevice(i);
    if (device == nullptr) continue;
    console.printf("      %-28s %4d dBm\n", device->getName().c_str(), device->getRSSI());
  }
  scan->clearResults();
  NimBLEDevice::deinit(true);
}

}  // namespace

void run_all(Stream& modem, Stream& console) {
  console.println();
  line(console, "================ UltimateTracker Bring-up ================");
  console.printf("Firmware: %s   Reset-Grund: %d\n", FIRMWARE_VERSION,
                 static_cast<int>(esp_sleep_get_wakeup_cause()));
  console.printf("Chip: %s, %d Kerne, Flash %lu MB, PSRAM %lu kB\n", ESP.getChipModel(),
                 ESP.getChipCores(), static_cast<unsigned long>(ESP.getFlashChipSize() / 1048576),
                 static_cast<unsigned long>(ESP.getPsramSize() / 1024));
  line(console, "PSRAM erwartet: ~8192 kB (N16R8, qio_opi)");
  line(console, "---------------------------------------------------------");

  i2c_scan(console);
  pmu_test(console);
  lis3dh_test(console);
  modem_test(modem, console);
  gnss_test(modem, console);
  tone_test(console);
  mic_test(console);
  piezo_test(console);
  button_test(console);
  wifi_test(console);
  ble_test(console);

  line(console, "---------------------------------------------------------");
  line(console, "Kommandos: [r] alles erneut  [m] Modem  [g] GNSS  [t] Ton");
  line(console, "           [i] I2S/Mikrofon  [p] Piezo  [l] LIS3DH  [b] Taster");
  line(console, "           [w] WLAN-Scan  [n] BLE-Scan");
  line(console, "           [s] Deep Sleep 60 s (für die Strommessung M1)  [h] Hilfe");
  line(console, "=========================================================");
}

void loop(Stream& modem, Stream& console) {
  if (!console.available()) return;
  const int value = console.read();
  switch (value) {
    case 'r': run_all(modem, console); break;
    case 'm': modem_test(modem, console); break;
    case 'g': gnss_test(modem, console); break;
    case 't': tone_test(console); break;
    case 'i': mic_test(console); break;
    case 'p': piezo_test(console); break;
    case 'l': lis3dh_test(console); break;
    case 'b': button_test(console); break;
    case 'w': wifi_test(console); break;
    case 'n': ble_test(console); break;
    case 's':
      line(console, "Deep Sleep für 60 s – jetzt Strom messen (M1) ...");
      delay(500);
      esp_sleep_enable_timer_wakeup(60ULL * 1000000ULL);
      esp_deep_sleep_start();
      break;
    case 'h':
      line(console, "r=alles m=Modem g=GNSS t=Ton i=Mikrofon p=Piezo l=LIS3DH b=Taster w=WLAN n=BLE s=Sleep h=Hilfe");
      break;
    default:
      break;
  }
}

}  // namespace bringup

#endif  // UT_BRINGUP
