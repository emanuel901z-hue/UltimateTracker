#include "nvs_config_store.h"

namespace tracker {
namespace {

constexpr const char* kNamespace = "utracker";
constexpr const char* kKey = "config";

}  // namespace

bool NvsConfigStorage::load(DeviceConfig& out) {
  Preferences prefs;
  if (!prefs.begin(kNamespace, true)) return false;
  bool ok = false;
  if (prefs.getBytesLength(kKey) == sizeof(DeviceConfig)) {
    DeviceConfig stored;
    if (prefs.getBytes(kKey, &stored, sizeof(stored)) == sizeof(stored)) {
      out = stored;
      ok = out.valid;
    }
  }
  prefs.end();
  return ok;
}

bool NvsConfigStorage::save(const DeviceConfig& config) {
  Preferences prefs;
  if (!prefs.begin(kNamespace, false)) return false;
  const size_t written = prefs.putBytes(kKey, &config, sizeof(config));
  prefs.end();
  return written == sizeof(config);
}

void NvsConfigStorage::clear() {
  Preferences prefs;
  if (prefs.begin(kNamespace, false)) {
    prefs.remove(kKey);
    prefs.end();
  }
}

}  // namespace tracker
