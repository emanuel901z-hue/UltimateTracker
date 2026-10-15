# Zertifizierte Find-My-Tracker (MiLi MiTag Duo) als Zusatzortung

Statt selbstgebauter OpenHaystack-Beacons kommen **zertifizierte** Tracker zum
Einsatz (Apple + Google lizenziert). Sie werden aus dem Gehäuse genommen, aus der
Hauptbatterie versorgt und mit ins Tracker-Gehäuse gelegt. Dieses Dokument hält
die Gerätedaten, die Netzwerk-Realität, die Einbau-Ideen und die Grenzen fest.

> **Stand:** 2026-10-15. Ergänzt `docs/findmy.md` (das die Server-Gegenstücke
> beschreibt) um die **Hardware-/Integrationsseite**.

## 1. Gerätedaten (MiLi MiTag Duo)

| Punkt | Wert |
|---|---|
| Netz | Apple Find My **oder** Google Find Hub – **nur eines gleichzeitig** (Reset: 6× drücken + halten) |
| Spannung | **2,6–3,6 V** (CR2032, lithium-manganese-dioxide) |
| Strom | 9,5 mA max @ Advertising, **22 µA Ø im gepaarten Zustand** |
| Akku-Laufzeit | 8–12 Monate, **nicht ladbar** |
| Maße / Funk | 37 × 37 × 5 mm, IP67, ABS/PC, BLE 5.2, +4 dBm, 80–100 m |

## 2. Netzwerk-Realität: nur ein Weg führt in unseren Stack

| Netz | Kommt in unsere UI? | Warum |
|---|---|---|
| **Google Find Hub** | **Ja** | `GoogleFindMyTools` (unser `google-findmy-webui`) liest die **E2EE-Keys** der im Konto registrierten Find-Hub-Tracker aus und entschlüsselt deren Positionen. Der Tracker läuft damit wie ein Beacon durch Ingest → Sensor-Fusion → Traccar. |
| **Apple Find My** | **Nein** (nur App) | Bei zertifizierten Accessoires steckt der Schlüssel im Gerät bzw. im iCloud-Schlüsselbund. Unser Apple-Weg (`findmy-bridge`/`macless-haystack`) funktioniert nur mit **DIY-Beacons**, deren Keys *du* erzeugst. Die Position ist nur in „Wo ist?" sichtbar. |

**Konsequenz:** Den **Google-Tag** für die Integration einbauen, den **Apple-Tag**
als reine Handy-Zusatzortung betrachten (dichteres Netz, aber Handarbeit beim
Nachsehen). Alternativ beide auf Google – dann sind beide in der UI, dafür ohne
Apples Netz.

### So kommt der Google-Tag in die UI (einmalig)

1. MiTag in der **Google-Find-Hub-App** einem Google-Konto zuordnen.
2. In der WebUI mit **demselben** Konto anmelden
   (<https://findmy.localhost> → „Config" → „Sign in with Google").
3. `bash scripts/setup-google-forwarding.sh` – setzt die Weiterleitung an den
   Bridge-Ingest (idempotent).
4. Eltern-UI → **Geräte → „Find-My-Beacons zuordnen"** – `google / <Gerätename>`
   einem Kind zuweisen. Danach fließt die Position in die Sensor-Fusion.

Die Verdrahtung existiert bereits vollständig (kein Code nötig) – Details:
[`findmy.md`](findmy.md) §3d.

### Anti-Stalking – der wichtigste Vorbehalt

Beide Netze lassen einen Tracker **piepen**, wenn er eine Weile (**8–24 h**) vom
Besitzer-Handy getrennt **und bewegt** wird; zusätzlich bekommen fremde Handys in
der Nähe eine „Tracker reist mit dir"-Warnung. Beim Kind ist das Eltern-Handy
meist **nicht** dabei → der Tag piept potenziell unterwegs/im Unterricht.

- Entspannt sich, wenn das Eltern-Handy **regelmäßig in Reichweite** ist (zu Hause
  morgens/abends setzt der Trenntimer zurück).
- **Lautsprecher nicht dämpfen**: iOS weist ausdrücklich auf manipulierte Speaker
  hin – und die Funktion ist Teil der Zulassung.

## 3. Stromversorgung

Der MiTag braucht **2,6–3,6 V** und darf **nicht** direkt an die LiPo
(3,5–4,2 V). Drei Wege, vom einfachsten zum saubersten.

### 3a. Schon an Bord: die AXP2101-Rails (kein Extra-LDO nötig)

Der PMU bringt mehrere Rail-Typen mit (AXP2101-Datenblatt):

| Rail | Bereich | Strom | Anmerkung |
|---|---|---|---|
| DCDC1 / DCDC5 | 1,5–3,4 V / 1,4–3,7 V | 2 A / 1 A | DC1 = **3,3 V** (ESP), DC5 = 3,3 V |
| DCDC3 | 1,6–3,4 V | 2 A | DC3 = **3,0 V – Modem/GPS**, per PMU schaltbar |
| ALDO1–4 | 0,5–3,5 V, 100-mV-Stufen | 300 mA | ALDO3/4 sind **low-noise**; ALDO2/ALDO4 sind im Projekt für den Mikrofon-Load-Switch vorgemerkt |
| BLDO1/2 | 0,5–3,5 V, 100-mV-Stufen | 300 mA | BLDO1 = 1,8 V (Level-Shifter, **muss anbleiben**), BLDO2 = 3,3 V |

Auf dem Board verifiziert (2026-10-12): DC1 3,3 V, DC3 3,0 V, DC5 3,3 V,
BLDO1 1,8 V, BLDO2 3,3 V aktiv (`docs/hardware-review.md`).

**Empfehlung:**

1. **3V3 (DC1/DC5) vom Header anzapfen** – null Bauteile. 3,3 V liegt im Bereich
   des Tags. Nur entkoppeln (100 nF + 10 µF, optional Ferrit in Reihe). Die Sorge
   „die ESP-Rail schroten" ist unbegründet: 22 µA sind bei einer Rail, die
   hunderte mA kann, nichts.
2. **ALDO2 oder ALDO4** auf 3,0 V – frei, schaltbar, low-noise. Braucht eine
   Firmware-Zeile (I2C: Register `0x90`, Bit `1<<n` = Enable; Register `0x92+n` =
   Spannung in 100-mV-Stufen ab 500 mV) und einen Lötpunkt am PMU-Ausgang. Dafür
   kann der ESP den Tag **stromlos schalten**.
3. **Nicht DC3** – das ist die Modem/GPS-Rail und wird laut Plan (B1, Variante 3)
   bei jedem Wake **zyklisch abgeschaltet**; der Tag würde mit dem Modem neu
   starten.
4. BLDO1 (1,8 V) ist zu niedrig und muss anbleiben; BLDO2 (3,3 V) ist belegt.

**Zu prüfen:** ob ALDO2/ALDO4 auf dem Board herausgeführt sind (sonst am
Ausgangs-Kondensator/Testpad abgreifen) – und den **Ruhestrom messen**. Das
Datenblatt nennt für den PMU im Leerlauf ~40 µA, die Ground-Ströme der LDOs stehen
dort nicht. Bei 22 µA Tag-Strom ist genau das die entscheidende Zahl.

### 3b. Eigener 3,0-V-LDO (wenn du volle Trennung willst)

- **Low-Iq-LDO statt Schaltregler.** Begründung: 22 µA Last – ein Buck bringt hier
  keinen Wirkungsgradvorteil, kostet aber Induktor und **EMV-Streuung** direkt
  neben BLE- und GNSS-Antenne.
  Geeignet: `MCP1700-3002` (TO-92, ≈ 1,6 µA), `HT7330-3.0` (TO-92, ≈ 4 µA),
  `TPS7A02` (SOT-23, ≈ 25 nA). **Nicht** `AMS1117` (≈ 5 mA Iq).
- **Warum das aufgeht:** das Board schaltet bei ~3,5 V ab → der LiPo liefert
  3,5–4,2 V, der LDO bleibt bis zum Ende in Regulation (untere Grenze des Tags ist
  2,6 V).
- **Eigener Zweig** an der LiPo: kleine Sicherung (z. B. 100 mA) + **100 nF und
  10 µF** direkt an den MiTag-Pads (BLE-Sendespitzen).
- **Optional**: P-Kanal-MOSFET als Lastschalter an einem freien GPIO – damit kann
  der ESP den Tag **stromlos schalten** (falls er sich aufhängt). Standard = an.
  Ein **BJT** taugt dafür nicht: bei 9,5 mA Spitzen bräuchte ein BC327 ~100 µA
  Basisstrom – mehr als die durchschnittliche Last des Tags.
- Nebeneffekt: der Tag meldet dauerhaft „voll" (konstante Spannung). Für uns egal –
  wir sehen die Batterie des Trackers, nicht die des Tags.

## 4. Einbau

- **Antenne frei halten**: den MiTag ans **gegenüberliegende Ende** vom
  ESP-Antennenbereich setzen, hinter TPU-Wand, weg von LiPo, Schrauben und
  Schirmblechen – 2,4 GHz wird von Metall und Akku geschluckt.
- **Taster erhalten**: für Power-On unnötig (Dauerstrom), aber für den
  **Reset (6× drücken)** zum Umschalten Apple ↔ Google. Ausführen oder als
  Pogo-Pad zugänglich machen.
- **Bare PCB schützen**: kleine Druck-Halterung oder Kapton auf der Unterseite,
  damit nichts gegen das ESP-Board scheuert. Nur die Antennenzone **nicht** vergießen.
- **Zwei Tags im Gehäuse** piepen und warnen unabhängig voneinander – akustisch
  und in der Ortung. Wenn nur einer integriert wird, den anderen außen am Riemen
  tragen (besserer Funkweg, leichter zu servicen).

## 5. Prüfpunkte beim Einbau

| # | Prüfung | Erwartung |
|---|---|---|
| 1 | Spannung an den MiTag-Pads | **3,0 V**, belastbar bis 9,5 mA |
| 2 | Ruhestrom des Zweigs | **< 30 µA** (Tag + LDO) |
| 3 | Polung | vor dem Einstecken messen |
| 4 | Kopplung | Tag wird in „Wo ist?" bzw. „Google Find Hub" gefunden |
| 5 | Reset erreichbar | 6× drücken + halten funktioniert noch eingebaut |
| 6 | Funkreichweite | 80–100 m Freifeld; im Gehäuse messen (M7 analog) |
| 7 | GNSS-Störung | GNSS-Fix-Zeit mit/ohne eingebauten Tag vergleichen |

## 6. Rechtliches (kurz)

- Ausbauen und Umversorgen entwertet die **CE-/FCC-Zertifizierung** des Moduls *als
  Produkt*.
- Apple/Google erwarten die Nutzung wie vorgesehen (Accessoire, nicht Personen-
  tracker). Für ein Familienprojekt ist das Grauzone – bewusst entschieden, nicht
  versehentlich.
- Die Anti-Stalking-Funktionen lassen sich **nicht** abschalten und sind Teil der
  Zulassung.
