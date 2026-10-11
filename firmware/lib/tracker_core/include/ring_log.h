// ring_log.h – kleiner Ereignis-Ringpuffer für die Felddiagnose.
//
// Die letzten N Ereignisse (Wake-Grund, Upload-Ergebnis, Fehler, Resets)
// überleben im RTC-RAM/NVS und können mit dem nächsten Sync hochgeladen
// oder per Serial gelesen werden (docs/optimizations.md B8).
// Reine Logik → host-testbar.

#pragma once

#include <cstddef>
#include <cstdint>

namespace tracker {

enum class LogEvent : uint8_t {
  Boot = 0,
  Motion = 1,
  Ptt = 2,
  Upload = 3,
  Download = 4,
  Error = 5,
  LowBattery = 6,
  ModemReset = 7,
  SearchMode = 8,
};

struct LogEntry {
  uint32_t uptime_s;
  LogEvent event;
  int16_t value;  // z. B. Akkustand, Dauer, Fehlercode

  // Explizite Konstruktoren: der Arduino-Build nutzt C++11, dort sind
  // Default-Member-Initialisierer kein Aggregat (kein LogEntry{a,b,c}).
  LogEntry() : uptime_s(0), event(LogEvent::Boot), value(0) {}
  LogEntry(uint32_t uptime, LogEvent ev, int16_t val) : uptime_s(uptime), event(ev), value(val) {}
};

class RingLog {
 public:
  static constexpr size_t kCapacity = 24;

  void add(uint32_t uptime_s, LogEvent event, int16_t value = 0);
  size_t size() const { return count_; }
  // index 0 = ältester Eintrag
  const LogEntry& at(size_t index) const;
  void clear();

 private:
  LogEntry entries_[kCapacity]{};
  size_t head_ = 0;  // nächster Schreibplatz
  size_t count_ = 0;
};

}  // namespace tracker
