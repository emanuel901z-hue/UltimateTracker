#!/usr/bin/env bash
# Erzeugt eine vorstrukturierte Messdatei für die Inbetriebnahme (M1–M8).
# Aufruf (in der WSL oder auf jedem Linux):  bash scripts/new-measurement-session.sh [Datum]
#
# Die Datei landet in docs/measurements/ und wird während des Messens ausgefüllt.
# Referenz (Ablauf, Abbruchkriterien): docs/measurement-plan.md

set -euo pipefail

STAMP="${1:-$(date +%Y-%m-%d)}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT/docs/measurements"
OUT="$OUT_DIR/inbetriebnahme-$STAMP.md"

mkdir -p "$OUT_DIR"
if [[ -e "$OUT" ]]; then
  echo "Datei existiert bereits: $OUT" >&2
  exit 1
fi

cat > "$OUT" <<'HEADER'
# Inbetriebnahme-Messprotokoll

- **Datum:**
- **Board / Seriennummer:**
- **Firmware-Stand (Commit):**
- **Messmittel:** (USB-Strommessgerät / µCurrent / Multimeter / Oszilloskop)
- **Umgebung:** (Temperatur, Netz, SIM-Karte)

> Ablauf und Abbruchkriterien: `../measurement-plan.md`. Werte hier eintragen,
> Auffälligkeiten sofort notieren („Beobachtung“).

HEADER

# Datum in den Kopf schreiben
sed -i "s/- \*\*Datum:\*\*/- **Datum:** $STAMP/" "$OUT"

cat >> "$OUT" <<'BODY'
## Vorbereitung (vor M1)

| Prüfung | Ergebnis | Anmerkung |
|---|---|---|
| Akku-Polung am JST gemessen (Rot = +) | | **vor** dem Einstecken! |
| SIM-Karte eingelegt (vor dem Einschalten!) | | LilyGO-Vorgabe |
| Antennen vorhanden (LTE + **aktive** GNSS) | | |
| IO2 am Header erreichbar? (Durchgangsprüfung) | | Fallback IO10/IO11 |
| Board-Maße gemessen (L × B × H) | | CAD-Grundlage |
| Gewicht | | |

## M1 – Ruhestrom

| Zustand | Strom | Anmerkung |
|---|---|---|
| Deep Sleep, Modem aus | | Ziel: < 0,5 mA (Board) |
| Deep Sleep, Modem PSM | | |
| Deep Sleep, Modem eDRX registriert | | |
| Sleep, Mikrofon zusätzlich an | | zeigt den Nutzen des Load-Switches |

- Beobachtung:
- Bewertung gegen Erwartung (0,36–1,1 mA laut LilyGO):

## M2 – I2S-Pipeline

| Prüfung | Ergebnis |
|---|---|
| Aufnahme 8 kHz/16 Bit funktioniert | |
| ADPCM-Kodierung/Dekodierung hörbar korrekt | |
| Bandpass 300–3400 Hz aktiv | |
| Kein „CONFLICT!“ (Treiber-Mischung) im Log | |

- Beobachtung (Knacken, Rauschen, Pegel):

## M3 – GNSS/LTE-Umschaltung

| Messung | Wert |
|---|---|
| Kalt-Fix (erster Fix nach Boot) | |
| Warm-Fix | |
| LTE-Attach | |
| Upload (Sync) | |
| Gesamtenergie pro Zyklus | |

- `AT+CPSMS?` / `AT+CEDRXS?`-Antwort (TAU/eDRX):

## M4 – SMS-Test (entscheidet über den SMS-Pfad)

| Test | Ergebnis |
|---|---|
| `AT+CMGF=1` + `AT+CMGS="…"` (Senden) | |
| SMS empfangen (`AT+CMGL="REC UNREAD"`) | |
| RI-Puls auf GPIO 3 beobachtet | |

- Fazit: SMS-Pfad nutzbar? ja / nein

## M5 – Laden & PMU

| Prüfung | Ergebnis |
|---|---|
| TS-Pin-Detection deaktiviert (sonst lädt nichts) | |
| Ladestrom eingestellt | |
| Ladekurve (1 h): Spannung/Strom/Temperatur | |
| Abschaltung bei 4,2 V | |

## M6 – Ende-zu-Ende (Audio)

| Prüfung | Wert |
|---|---|
| Uplink: PTT → Nachricht in der UI | |
| Latenz bis zur Anzeige | |
| Downlink: Aufnahme → Wiedergabe am Tracker | |
| Latenz bis zur Wiedergabe (Poll-Intervall!) | |

## M7 – Antennen & Reichweite

| Ort | GNSS-Fixzeit | hdop | CSQ (LTE) |
|---|---|---|---|
| Outdoor, Antenne frei | | | |
| Outdoor, Antenne im Gehäuse | | | |
| Innen | | | |

## M8 – Laufzeittest (48 h)

| Messung | Wert |
|---|---|
| Startspannung / Startkapazität | |
| Verbrauch nach 48 h | |
| Anzahl Wake-Zyklen | |
| Hochrechnung Laufzeit | |

- Ziel: < 25 % Verbrauch in 48 h (⇒ > 8 Tage)

## Auswertung / Folgeaufgaben

- Werte in `project.md` (Abschnitt 5) und `docs/architecture.md` nachziehen:
- Entscheidungen ergänzen (`docs/decisions.md`, z. B. Modem-Power-Modus):
- Offene Punkte:
BODY

echo "Erzeugt: $OUT"
echo "Während des Messens ausfüllen; danach Werte in project.md/architecture.md nachziehen."
