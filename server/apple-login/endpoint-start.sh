#!/bin/sh
# Startskript für macless-haystack: wartet auf die Apple-Anmeldung.
#
# Das Image versucht bei JEDEM Start einen frischen Apple-Login. Solange keine
# Anmeldung vorliegt, läuft das in eine Neustart-Schleife und hämmert Apples
# GSA-Endpunkt – der antwortet dann mit HTTP 503 bzw. ec -80045 (This action
# cannot be completed at this time) und die Sperre bleibt bestehen.
#
# Deshalb hier: erst warten, bis der Helfer apple-login (gesteuert über die
# Eltern-UI) auth.json geschrieben hat, dann starten.
set -u

DATA=/app/endpoint/data

if [ ! -f "$DATA/auth.json" ]; then
	echo '[macless-haystack] Keine Apple-Anmeldung vorhanden (auth.json fehlt).'
	echo '[macless-haystack] Bitte in der Eltern-UI anmelden: Geräte -> Apple Find My einrichten -> Apple-Anmeldung (2FA).'
	echo '[macless-haystack] Warte - ohne wiederholte Apple-Login-Versuche (schont das Konto) ...'
	while [ ! -f "$DATA/auth.json" ]; do
		sleep 30
	done
	echo '[macless-haystack] auth.json gefunden - starte.'
fi

./endpoint/updateRepo || true
exec python -u endpoint/mh_endpoint.py
