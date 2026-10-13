#!/usr/bin/env bash
# Setzt das Ausführungsrecht für den von der Google-Find-Hub-WebUI
# heruntergeladenen Chrome ("Chrome for Testing").
#
# Hintergrund (Workaround für einen Fehler im Image): Die entpackten Dateien
# haben kein +x – u. a. `chrome_crashpad_handler`. Chrome bricht dann ab mit
#   FATAL: posix_spawn .../chrome_crashpad_handler: Permission denied (13)
# und die WebUI meldet „Browser provisioning failed"; im eingebetteten
# noVNC-Fenster erscheint „keine Verbindung".
#
# Aufruf in der WSL-Distro, während der Stack läuft:
#   bash scripts/fix-findmy-browser.sh
# Danach in der UI erneut „Sign in with Google" klicken.
#
# Der Container wird dynamisch gesucht (parallele Compose-Projekte/Testinstanz).
set -euo pipefail

CONTAINER=$(docker ps --filter 'name=google-findmy-webui' --format '{{.Names}}' | head -1)
if [ -z "$CONTAINER" ]; then
	echo "Kein WebUI-Container gefunden – läuft das Compose-Profil 'findmy'?" >&2
	exit 1
fi

if ! docker exec "$CONTAINER" sh -c 'test -d /run/gfmt-browser/chrome-linux64'; then
	echo "Chrome ist noch nicht heruntergeladen."
	echo 'Bitte zuerst in der UI (Tab Config) auf Sign in with Google klicken,'
	echo "kurz warten und dieses Skript dann erneut ausführen."
	exit 0
fi

docker exec "$CONTAINER" sh -c 'chmod -R a+x /run/gfmt-browser/chrome-linux64'
echo "Ausführungsrecht gesetzt in $CONTAINER (/run/gfmt-browser/chrome-linux64)."
echo 'Jetzt in der UI erneut "Sign in with Google" klicken.'
