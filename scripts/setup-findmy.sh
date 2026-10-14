#!/usr/bin/env bash
# Find My in einem Schritt einrichten und den Zustand melden.
#
#   * Google Find Hub: Weiterleitungs-Endpunkt auf unseren Ingest setzen
#     (ruft scripts/setup-google-forwarding.sh auf – idempotent).
#   * Apple Find My: Zustand melden (Zugangsdaten? Anmeldung/auth.json?).
#
# Aufruf in der WSL-Distro (Stack läuft, Profil `findmy`):
#   bash scripts/setup-findmy.sh
#
# Danach in der Eltern-UI: Geräte → „Find-My-Beacons zuordnen" (Einträge
# „apple / …" bzw. „google / <Gerätename>"). Nur zugeordnete Beacons fließen in
# die fusionierte Position und nach Traccar (docs/fusion.md).
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
SERVER_DIR="${SERVER_DIR:-$HOME/UltimateTracker/server}"
cd "$SERVER_DIR"

echo "=== Google Find Hub: Weiterleitung an die Bridge ==="
if bash "$HERE/setup-google-forwarding.sh"; then
	echo "  ok"
else
	echo "  nicht eingerichtet (noch nicht bei Google angemeldet? siehe unten)" >&2
fi

echo
echo "=== Apple Find My: Zustand ==="
docker compose exec -T audio-bridge python - <<'PY'
import app.main as m

status = m.apple_config_status()
print("  Zugangsdaten (config.ini):", "hinterlegt" if status["configured"] else "fehlen")
print("  Apple-Anmeldung (auth.json):",
      "vorhanden" if (m.APPLE_CONFIG_DIR / "auth.json").exists() else "fehlt")
print("  Dienst erreichbar:", m.probe_http("macless-haystack", 6176, "/"))
PY

cat <<'TEXT'
  Falls etwas fehlt (in der Eltern-UI, Tab „Geräte" → „Apple Find My einrichten"):
    1. Apple-ID + Passwort speichern
    2. „Anmeldung starten" → Code aus der SMS eintragen (2FA)
  Der Dienst startet danach von selbst (docs/findmy.md).

=== Beacons zuordnen ===
  Eltern-UI → Tab „Geräte" → „Find-My-Beacons zuordnen".
  Nur zugeordnete Beacons fließen in die Fusion/Traccar (docs/fusion.md).
TEXT
