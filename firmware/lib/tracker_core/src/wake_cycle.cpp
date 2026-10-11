#include "wake_cycle.h"

namespace tracker {
namespace {

void apply_server_config(const SyncResponse& sync, WakeCycleDeps& deps) {
  if (!deps.config) return;
  // Poll-Intervall nur übernehmen, wenn es nicht der Suchmodus ist – sonst
  // würde der kurze Suchmodus-Wert als Normalintervall gespeichert.
  if (!sync.search_mode && sync.next_poll_s >= deps.settings.min_poll_s) {
    deps.config->poll_interval_s = sanitize_poll_interval(sync.next_poll_s, deps.settings);
  }
  if (sync.audio_volume >= 0) {
    const int volume = sync.audio_volume > 100 ? 100 : sync.audio_volume;
    deps.config->audio_volume = static_cast<uint8_t>(volume);
  }
}

}  // namespace

WakeCycleResult run_wake_cycle(WakeReason reason, float battery_percent, WakeCycleDeps& deps) {
  WakeCycleResult result;
  result.next_sleep_s = deps.settings.poll_interval_s;

  if (deps.modem == nullptr || deps.config == nullptr || !deps.config->valid) {
    result.outcome = WakeOutcome::ConfigInvalid;
    result.error = "Konfiguration ungültig (Provisioning fehlt)";
    return result;
  }

  if (!deps.modem->begin()) {
    result.outcome = WakeOutcome::NoNetwork;
    result.error = "Modem nicht bereit";
    return result;
  }

  // 1) GNSS-Fix (nur wenn gewünscht). LTE und GNSS sind beim SIM7080G exklusiv,
  //    acquireFix() schaltet die Antenne/GNSS selbst wieder ab.
  Position position;
  if (deps.want_fix) {
    GnssFix fix;
    if (deps.modem->acquireFix(fix, 60000)) {
      position = Position(true, fix.latitude, fix.longitude, fix.hdop, fix.epoch_s);
      result.position_valid = true;
      result.fix_time_ms = fix.fix_time_ms;
    } else {
      result.outcome = WakeOutcome::NoFix;  // Sync läuft trotzdem (ohne Position)
      result.error = "kein GNSS-Fix";
    }
  }

  // 2) Sync: ein Roundtrip pro Wake (A5/C1)
  SyncRequest request;
  request.device_id = deps.config->device_id;
  request.battery_percent = battery_percent;
  request.wake_reason = wake_reason_name(reason);
  request.firmware = deps.firmware_version ? deps.firmware_version : "0.0.0";
  request.position = position;

  const std::string body = build_sync_request(request);
  const std::string sync_url = std::string(deps.config->server_url) + "/api/v1/device/sync";

  HttpRequest http;
  http.method = "POST";
  http.url = sync_url.c_str();
  http.body = body.c_str();
  http.body_len = body.size();
  http.content_type = "application/json";

  HttpResponse response;
  if (!deps.modem->httpRequest(http, response) || response.status != 200) {
    result.outcome = WakeOutcome::SyncFailed;
    result.http_status = response.status;
    result.error = "Sync fehlgeschlagen";
    // Kein Serverwert verfügbar → lokale Policy (batterieabhängig) verwenden.
    result.next_sleep_s =
        next_sleep_seconds(reason, battery_percent, false, deps.settings);
    deps.modem->end(deps.config->modem_power_mode);
    return result;
  }
  result.http_status = response.status;

  SyncResponse sync;
  if (!parse_sync_response(response.body, sync)) {
    result.outcome = WakeOutcome::SyncFailed;
    result.error = "Antwort nicht lesbar";
    deps.modem->end(deps.config->modem_power_mode);
    return result;
  }

  result.search_mode = sync.search_mode;
  result.next_sleep_s = sanitize_poll_interval(sync.next_poll_s, deps.settings);
  result.have_ota = sync.ota.present;
  apply_server_config(sync, deps);

  // 3) Audio-Downlink laden (Wiedergabe folgt mit der Hardware)
  if (sync.message.present) {
    const std::string download_url = std::string(deps.config->server_url) + sync.message.url;
    HttpRequest download;
    download.method = "GET";
    download.url = download_url.c_str();

    HttpResponse download_response;
    if (deps.modem->httpRequest(download, download_response) && download_response.status == 200) {
      result.have_message = true;
    } else {
      result.error = "Audio-Download fehlgeschlagen";
    }
  }

  // 4) Modem in den konfigurierten Schlafmodus (B1)
  deps.modem->end(deps.config->modem_power_mode);

  if (result.outcome == WakeOutcome::NoFix) {
    // Sync war erfolgreich, nur ohne Position – Ergebnis bleibt NoFix.
    result.next_sleep_s =
        next_sleep_seconds(reason, battery_percent, result.search_mode, deps.settings);
  }
  return result;
}

}  // namespace tracker
