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

Der MiTag wird aus der Tracker-LiPo versorgt, **nicht** über die 3V3-Rail des
ESP-Boards.

- **3,0-V-LDO mit winzigem Ruhestrom** statt Schaltregler. Begründung: 22 µA Last –
  ein Buck bringt hier keinen Wirkungsgradvorteil, kostet aber Induktor und
  **EMV-Streuung** direkt neben BLE- und GNSS-Antenne.
  Geeignet: `TPS7A02` (≈ 25 nA Iq), `HT7330` (≈ 4 µA), `XC6206` (≈ 1 µA).
- **Warum das aufgeht:** das Board schaltet bei ~3,5 V ab → der LiPo liefert
  3,5–4,2 V, der LDO bleibt bis zum Ende in Regulation (untere Grenze des Tags ist
  2,6 V).
- **Eigener Zweig** an der LiPo: kleine Sicherung (z. B. 100 mA) + **100 nF und
  10 µF** direkt an den MiTag-Pads (BLE-Sendespitzen).
- **Lötpunkt**: der CR2032-Halter (Zelle raus, dünne Litze an die Pads).
  **Polung vorher messen** (siehe `project.md` 2.3).
- **Optional**: P-Kanal-MOSFET als Lastschalter an einem freien GPIO – damit kann
  der ESP den Tag **stromlos schalten** (falls er sich aufhängt). Standard = an.
- **Alternative ohne Extra-Bauteil**: eine freie AXP2101-Rail (ALDO2/ALDO4) auf
  3,0–3,3 V. Achtung: dieselben Rails sind im Projekt als Kandidat für den
  **Mikrofon-Load-Switch** notiert – nicht doppelt belegen.
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
