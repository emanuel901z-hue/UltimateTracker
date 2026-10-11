#include "ring_log.h"

namespace tracker {

void RingLog::add(uint32_t uptime_s, LogEvent event, int16_t value) {
  entries_[head_] = LogEntry{uptime_s, event, value};
  head_ = (head_ + 1) % kCapacity;
  if (count_ < kCapacity) ++count_;
}

const LogEntry& RingLog::at(size_t index) const {
  static const LogEntry empty{};
  if (index >= count_) return empty;
  const size_t start = (count_ == kCapacity) ? head_ : 0;
  return entries_[(start + index) % kCapacity];
}

void RingLog::clear() {
  head_ = 0;
  count_ = 0;
}

}  // namespace tracker
