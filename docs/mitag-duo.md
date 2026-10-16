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

### 3a. Schon an Bord: `DC5` vom Header (kein Extra-Bauteil nötig)

LilyGO dokumentiert die **Power-Domains** im Hersteller-Repo
(`Xinyuan-LilyGO/LilyGo-T-SIM7080G`, README Abschnitt „Power domain"):

| Rail | versorgt | für uns |
|---|---|---|
| **DC5** | **kein Bordperipherie** – als **Header-Pin** herausgeführt, 1,4–3,7 V, max. 1 A, per Software einstellbar | **die Lösung** |
| DC3 / BLDO2 | Modem + GPS | nicht anfassen – wird laut Plan (B1, Variante 3) bei jedem Wake zyklisch abgeschaltet |
| DC1 | ESP32-S3-Kern, fest 3,3 V | Herstellerwarnung: **nicht** per Software verstellen |
| ALDO1 / ALDO2 / ALDO4 | Kamera | frei, wenn keine Kamera – aber **nicht** am Header |
| ALDO3 | SD-Karte | frei, wenn keine SD – aber **nicht** am Header |
| BLDO1 | Level-Shifter (1,8 V) | **muss anbleiben**, sonst reden ESP32-S3 und SIM7080G nicht mehr |

**Empfehlung: den `DC5`-Header-Pin nehmen.**

- Er ist bereits herausgeführt und im Auslieferungszustand aktiv (Messung
  2026-10-12: **DC5 = 3,3 V**) – und er versorgt **kein** Bordperipherie.
- 3,3 V liegen im Bereich des Tags (2,6–3,6 V) → **nichts einzustellen**.
  Wer exakt 3,0 V will, kann DC5 per Software verstellen (max. 1 A).
- Nur entkoppeln: 100 nF + 10 µF direkt an den MiTag-Pads, optional ein Ferrit in
  Reihe (die 9,5-mA-Advertising-Spitzen sollen nicht in GNSS/BLE streuen).

Damit brauchst du **weder LDO noch Lastschalter**, und der Tag hängt **nicht** an
der 3V3-/DC1-Rail des ESP. Auch der Ruhestrom kostet nichts extra: die Rail ist
ohnehin an.

**Gegenprobe im Schaltplan** (`schematic/T-SIM7080G_Schematic.pdf` im
Hersteller-Repo, Blätter „PMU" und „SOC"): Die Cross-Reference-Tabelle auf dem
PMU-Blatt führt `PMU_DCDC5` **nur** auf die SOC-/Header-Seite; am PMU hängen daran
lediglich Entkopplungskondensatoren (C31 100 nF, C46 10 µF). Auf dem SOC-Blatt
steht `PMU_DCDC5` ausschließlich im Block **„External Pin"** – also an der
Stiftleiste. Kein weiterer Verbraucher auf dem Board.

Falls du ihn doch **schaltbar** willst: die Kamera-Rails (ALDO1/ALDO2/ALDO4) sind
ohne Kamera frei, aber nicht am Header – dann müsstest du am PMU-Ausgang löten.
Firmware: I2C-Register `0x90`, Bit `1<<n` = Enable (n: 0=ALDO1 … 3=ALDO4),
`0x92+n` = Spannung in 100-mV-Stufen ab 500 mV. Achtung: dieselben Rails sind im
Projekt als Kandidat für den **Mikrofon-Load-Switch** notiert – nicht doppelt
belegen.

> **Warum nicht die 3V3-Rail des ESP?** Technisch ginge es (3,3 V, 22 µA sind
> nichts), aber DC1 ist laut Hersteller die Kernversorgung, die man nicht
> verstellen soll – und DC5 ist ohnehin da und frei.

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
- **Zwei Tags (Apple + Google)**: Bauform, Entkopplung und Zuordnung in der UI –
  siehe **§5**.

## 5. Zwei Tags (1× Apple, 1× Google)

**Elektrisch ändert sich fast nichts:** DC5 kann 1 A, zwei Tags ziehen zusammen
≈ 44 µA (Spitzen ~19 mA). Jeder Tag bekommt seine eigene Entkopplung, dazu ein
gemeinsamer Bulk-Kondensator:

```
DC5 ──[Ferrit]──┬── 47 µF ──────────── GND
                ├── 100 nF + 10 µF ─── MiTag 1 (Apple)
                └── 100 nF + 10 µF ─── MiTag 2 (Google)
```

(Eine eigene Ferritperle je Tag ist genauso gut – dann koppeln sich die
Advertising-Spitzen der beiden nicht.)

**In der UI taucht nur der Google-Tag auf** (§2). Deshalb:

- Tags **sprechend benennen** – der Beacon-Schlüssel ist `google / <Gerätename>`,
  also z. B. „Mia-Google". Sonst ist die Zuordnung in der Eltern-UI nicht eindeutig.
- Der Apple-Tag bleibt reine Handy-Sicht („Wo ist?").

**Mechanik – hier wird es eng.** Ein Tag misst **37 × 37 × 5 mm**, das Board ist
**32 mm breit**. Zwei davon unterzubringen heißt:

- **Breite:** das Gehäuse muss auf **≥ ~41 mm** wachsen (oder der Tag liegt schräg
  bzw. außen).
- **Höhe:** Board (~10 mm) + LiPo (10 mm) + 2 × 5 mm = **~30 mm** – das Ziel von
  20–22 mm (`project.md` §1.3) ist damit nicht mehr zu halten.

Drei Auswege:

1. **Gehäuse größer** (Breite +5 mm, Höhe +10 mm) – einfachste Lösung, wenn die
   Trageform mitspielt.
2. **Ein Tag innen, einer außen**: innen den **Google**-Tag (der in der UI
   sichtbar ist), den Apple-Tag in einer kleinen Tasche am Riemen – besserer
   Funkweg, keine Bauformänderung.
3. **Beide außen** in einer separaten Tasche – dann bleibt der Tracker selbst schlank.

**Beide Taster erreichbar lassen** (§4): Der Reset (6× drücken) ist der einzige Weg,
ein Tag später auf das andere Netz umzustellen.

**Anti-Stalking ×2:** beide Tags piepen unabhängig und lösen fremde
„Tracker reist mit dir"-Warnungen aus – doppelt so oft wie mit einem.

## 6. Bauteile (Beschaffung)

Stand 2026-10-16 – die konkreten Teile für den MiTag-Zweig und die BAT-Pads,
inklusive der Fallstricke, die wir dabei geprüft haben.

**Keramik (Entkopplung).** HUAREW-Keramik-Set, 10 Werte × 30 Stück (300 St.),
bedrahtet, **50 V, ±10 %** (X7R-Klasse), enthält 0,1 µF = 100 nF … 10 µF.

- Deckt ab: MiTag-Entkopplung (2× 100 nF), Taster-Entprellung, BAT-Pads,
  Decoupling um MAX98357A/INMP441.
- **50 V statt 6,3 V ist hier ein Vorteil**: weniger **DC-Bias**-Verlust, die
  Kapazität bleibt näher am Nennwert.
- **±10 % schließt Y5V aus** (das wäre −20 %/+80 %) → X7R, temperaturstabil.
- Die 4,7-/10-µF-Scheiben sind die größten im Set – im engen Gehäuse lieber den
  kleinen Elko für den MiTag-Bulk nehmen.

**Elektrolyt (Stütze an den BAT-Pads).** CD11GT(G)-Serie, **1000 µF/25 V
(10×17 mm, 0,065 Ω)** oder **1000 µF/35 V (10×20 mm, 0,032 Ω)**, Ripple
1380–1800 mA @ 105 °C, 3000 h. **Liegend** einbauen (stehend ist der 20-mm-Körper
zu hoch).

- **Nicht** das 20-%-Verlustfaktor-Sortiment: daraus folgt ESR ≈ 0,56 Ω beim
  470 µF → bei 2 A Sendespitze ~1 V Einbruch.
- Bei gleicher Baugröße ist ein 35-V-Typ dem 16-V-Typ hier überlegen (Tabelle der
  Serie) – deshalb 25/35 V, nicht 16 V.

**Elko-Sortiment (Bulk).** Vorhanden: 0,1 µF–470 µF, 16/50 V, 4×7…8×12 mm.

- Brauchbar für: Bulk am MiTag (10 µF), Puffer rund um Audio.
- **Nicht** für die BAT-Pads (ESR) und **nicht** als 100-nF-Entkopplung.

**Bewusst nicht verwendet:**

| Teil | Warum nicht |
|---|---|
| LIR2032 im MiTag-Schacht | mechanisch passend, aber **4,2 V geladen** → über der Grenze des Tags (3,6 V) |
| ML2032 / VL2032 | 3 V, aber Memory-Backup-Zellen mit zu hohem Innenwiderstand für die 9,5-mA-Spitzen |
| Superkondensator statt Stützkondensator | ~30 Ω ESR → für 2 A unbrauchbar |
| Akku parallel zur Hauptbatterie | Ausgleichsströme ohne Balancing/Schutz |

### Beschafft (2026-10-16)

| Teil | Bezug | Werte |
|---|---|---|
| Keramik-Set | HUAREW, Amazon `B087785H1J` | 10 Werte × 30 St., **50 V, ±10 %** |
| Elko für die BAT-Pads | HUABAN, Amazon `B0CFXJK7LB` | **35 V / 1000 µF**, 10×17 mm |
| Widerstände | BOJACK, Amazon `B08FD1XVL6` | 25 Werte, 1000 St., 1/4 W, 5 % |
| Transistoren | CYTGOUPER, Amazon `B0FGQ1515F` | 200 St., 10 BC-Typen (NPN/PNP) |

> Das Angebot nennt für 35 V/1000 µF **10×17 mm**, das Datenblatt der CD11GT-Reihe
> nennt dort **10×20 mm** (10×17 gehört in der Tabelle zum 25-V-Typ). Funktional
> egal – beide liegen bei 0,03–0,07 Ω –, aber beim Auspacken einmal nachmessen:
> die Bauhöhe hängt davon ab.

## 7. Prüfpunkte beim Einbau

| # | Prüfung | Erwartung |
|---|---|---|
| 1 | Spannung an den MiTag-Pads | **DC5 = 3,3 V** (im Bereich 2,6–3,6 V), belastbar bis 9,5 mA |
| 2 | Ruhestrom des Zweigs | Tag ≈ 22 µA – die Rail ist ohnehin an, es kommt nichts dazu |
| 3 | Polung | vor dem Einstecken messen |
| 4 | Kopplung | Tag wird in „Wo ist?" bzw. „Google Find Hub" gefunden |
| 5 | Reset erreichbar | 6× drücken + halten funktioniert noch eingebaut |
| 6 | Funkreichweite | 80–100 m Freifeld; im Gehäuse messen (M7 analog) |
| 7 | GNSS-Störung | GNSS-Fix-Zeit mit/ohne eingebauten Tag vergleichen |
| 8 | Zwei Tags | beide gleichzeitig gekoppelt und in ihrer App sichtbar |

## 8. Rechtliches (kurz)

- Ausbauen und Umversorgen entwertet die **CE-/FCC-Zertifizierung** des Moduls *als
  Produkt*.
- Apple/Google erwarten die Nutzung wie vorgesehen (Accessoire, nicht Personen-
  tracker). Für ein Familienprojekt ist das Grauzone – bewusst entschieden, nicht
  versehentlich.
- Die Anti-Stalking-Funktionen lassen sich **nicht** abschalten und sind Teil der
  Zulassung.
