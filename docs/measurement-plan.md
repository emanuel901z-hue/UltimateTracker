# Mess- und Testplan (Inbetriebnahme)

Reihenfolge einhalten – jede Messung kann die Architektur beeinflussen.
Alle Messungen mit Datum, Aufbau und Rohwerten in `docs/measurements/` ablegen
(Ordner wird beim ersten Messlauf angelegt).

## M1 – Ruhestrom & Sleep-Zustände

- **Ziel:** reale Ströme für Sleep, Modem-PSM, Modem aus.
- **Aufbau:** USB-Strommessgerät oder µCurrent/Shunt + Multimeter an BAT; Board im
  Deep Sleep (nur LIS3DH aktiv), Mikrofon aus.
- **Varianten:** (a) Modem per PWRKEY aus, (b) Modem in PSM, (c) Modem registriert.
- **Erwartung:** 0,36–1,1 mA (Board) + Modem-Anteil. **Abbruchkriterium:** > 2 mA
  ⇒ Ursache suchen (LEDs, PSRAM, PMU-Rails, LIS3DH-Konfiguration).
- **Ergebnis fließt in:** `docs/architecture.md` (Energiebudget).

## M2 – I2S-Pipeline (Loopback)

- **Ziel:** INMP441 → ADPCM → MAX98357A fehlerfrei.
- **Aufbau:** Breadboard; 1 kHz-Testton per Lautsprecher einsprechen, aufnehmen,
  ADPCM-kodieren, dekodieren, abspielen.
- **Prüfpunkte:** Full-Duplex mit geteilter BCLK/WS läuft stabil; keine „CONFLICT!“-
  Meldung; Klang verständlich; Bandpass 300–3400 Hz aktiv.
- **Abbruchkriterium:** Knacken/Aussetzer ⇒ DMA-Puffergrößen anpassen.

## M3 – GNSS/LTE-Umschaltung

- **Ziel:** Zeiten und Energie pro Ortungszyklus.
- **Aufbau:** Logging von `AT+CGNSINF` und Zeitstempeln; Strommessung.
- **Messen:** Warm-Fix (5–15 s erwartet), Kalt-Fix (30–60 s), LTE-Attach, Upload,
  Rückschalten. **Prüfen:** GNSS-Antenne an (`AT+SGPIO=0,5,1,1`).
- **Ergebnis:** Zyklusdauer + mAh pro Push.

## M4 – SMS-Test (Entscheidung für/gegen SMS-Pfad)

- **Ziel:** Klären, ob der SIM7080G auf diesem Board SMS senden/empfangen kann.
- **Aufbau:** 1NCE-SIM aktiv; `AT+CMGF=1`, `AT+CMGS="+49…"`, `AT+CNMI`,
  `AT+CMGL="REC UNREAD"`; Test-SMS von einem Handy.
- **Abbruchkriterium:** Fehler/keine Zustellung ⇒ SMS-Pfad endgültig streichen
  (Suchmodus bleibt der Weg).
- **Zusatz:** RI-Verhalten auf GPIO 3 beobachten (Puls bei SMS?).

## M5 – Laden & PMU

- **Ziel:** Laden funktioniert mit 103450-LiPo.
- **Schritte:** TS-Pin-Detection in Firmware deaktivieren; Ladestrom einstellen;
  Ladekurve (Spannung/Strom/Temperatur) über eine Stunde loggen.
- **Prüfpunkte:** Lade-LED korrekt, keine Übertemperatur, Abschaltung bei 4,2 V.
- **Sicherheit:** Polung des JST-Steckers **vor** dem Einstecken messen.

## M6 – End-to-End (Audio beide Richtungen)

- **Uplink:** PTT drücken → Quittungston → sprechen → loslassen → Datei erscheint in
  der Bridge-UI, im Browser abspielbar.
- **Downlink:** In der UI aufnehmen → Tracker pollt → Wiedergabe über 1510.
- **Messen:** Latenz bis zur Anzeige (Uplink) und bis zur Wiedergabe (Downlink,
  abhängig vom Poll-Intervall). Ziel: Uplink < 60 s nach Loslassen.

## M7 – Antennen & Reichweite

- **GNSS:** Fix-Zeit und `hdop` outdoor/in Gebäudenähe; Antenne im Gehäuse vs. frei.
- **LTE:** Feldstärke (`AT+CSQ`), Upload-Dauer an typischen Orten (Wohnung, Straße,
  Keller). Entscheidungshilfe für Antennenplatzierung im CAD.

## M8 – Laufzeittest

- **Ziel:** Reale Laufzeit über 48 h mit Standardkonfiguration (15-min-Poll).
- **Aufbau:** Voll geladener Akku, Logging von Spannung (PMU) und Wake-Gründen.
- **Erwartung:** < 25 % Verbrauch in 48 h (⇒ > 8 Tage Gesamtlaufzeit).
- **Ergebnis:** Kalibriert das Energiebudget und die Poll-Intervalle.

## Abschluss der Messphase

Nach M1–M8: Werte in `project.md` (Abschnitt 5) und `docs/architecture.md`
aktualisieren; Entscheidungen in `docs/decisions.md` ergänzen (z. B. „SMS nicht
verfügbar“, „Poll-Intervall 20 min“).
