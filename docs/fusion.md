# Sensor-Fusion: mehrere Quellen → eine Position je Kind

Ein Kind, mehrere Positionsquellen. Ziel: **eine** belastbare Position je Kind –
für die Karte, für Traccar und für Benachrichtigungen.

## 1. Die Quellen

| Quelle | Typische Genauigkeit | Verzögerung | Vertrauensstufe | Gültigkeit |
|---|---|---|---|---|
| `tracker` (GNSS im Gerät) | 3–10 m | sofort | **100** | 30 min |
| `apple` (Find My) | ~50–100 m (Crowd-Netz) | 5–15 min | 60 | 90 min |
| `google` (Find Hub) | ~50–100 m (Crowd-Netz) | 5–15 min | 60 | 90 min |
| `network` (Funkzelle, Anbieter-API) | 300–3000 m | sofort | 30 | 15 min |

## 2. Die Regel: **auswählen statt mitteln**

GNSS (3–10 m) und Find My (~50–100 m) zu **mitteln** würde die gute Quelle
**verschlechtern** ✗ – der Fehler wäre danach größer als vorher. Deshalb gilt:

1. Nur **gültige** Quellen betrachten (Alter ≤ Gültigkeit der Quelle).
2. Aus diesen die **höchste Vertrauensstufe** wählen.
3. Bei Gleichstand: **frischer**, dann **genauer**.
4. Ist **keine** Quelle frisch: die vertrauenswürdigste alte nehmen und als
   **veraltet** kennzeichnen (`stale: true`) – nie „nichts" anzeigen, wenn wir
   einen letzten Stand haben.

Beispiel: Das Gerät hat vor 20 Minuten GNSS gemeldet, Apple vor 3 Minuten.
→ GNSS gewinnt (Vertrauensstufe 100 > 60, noch gültig), die Apple-Position wird
als Zusatzquelle mitgeführt. Ist die GNSS-Position älter als 30 Minuten, gewinnt
Apple.

## 3. Umsetzung

- **Beacon-Zuordnung** (`beacons`-Tabelle): Ein Find-My-Beacon gehört zu einem
  Kind (Geräte-Registry, ID = IMEI). Pflege in der UI: *Geräte → Find-My-Beacons
  zuordnen*. Ohne Zuordnung erscheint ein Beacon **nur** in der Bridge – nicht in
  Traccar (sonst stünden dort Fremdgeräte).
- **Fusion** (`best_position()` in der Bridge): liefert Position, Quelle,
  Genauigkeit, Alter, Begründung und **alle** Quellen zur Kontrolle.
- **Traccar bekommt genau eine Position je Kind** – nicht jede Quelle als eigenes
  Gerät. Damit zeigt Traccar **ein** Gerät pro Kind (der Wunsch „das gehört
  zusammen").
- **API:** `GET /api/v1/parent/fused?device_id=…` (fusionierte Position),
  `GET /api/v1/parent/map` (Karte: fusioniert + Quellen),
  `GET/PUT /api/v1/parent/beacons` (Zuordnung).

## 4. Was die Karte zeigt

- **Marker** = fusionierte Position; im Popup stehen **Quelle**, Genauigkeit,
  Alter und Akkustand – plus ein Hinweis, wenn keine frische Quelle vorliegt.
- **Kreise** = die einzelnen Find-My-Positionen (ungefiltert), damit man sieht,
  woher die Fusion stammt.

## 5. Nächste Optimierungsstufen

| Stufe | Nutzen | Aufwand |
|---|---|---|
| **Glättung/Dwell-Time** (Position erst übernehmen, wenn sie sich bestätigt) | weniger Springen in der Anzeige | klein |
| **Genauigkeitsgewichtete Anzeige** (Unsicherheitsradius statt Punkt) | ehrliche Darstellung der Find-My-Unschärfe | klein |
| **Kalman-Filter** über GNSS-Punkte | ruhigere Spur, bessere Geschwindigkeit | mittel |
| **Funkzellen-/WLAN-Quelle** über die Anbieter-API | Position ohne Fix (Indoor, Keller) | mittel |
| **Zustandserkennung** (steht / bewegt / zuletzt gesehen) | bessere Benachrichtigungen | klein |
| **Mehrere Beacons je Kind** (Schulranzen + Jacke) | Redundanz | klein (bereits möglich) |

## 6. Grenzen (ehrlich)

- Crowd-Netz-Positionen (Apple/Google) sind **grob und verzögert** ✗ – sie
  ersetzen kein GNSS, sie überbrücken Lücken ✓.
- „Triangulation" im strengen Sinn passiert **im Fremdnetz** (Apple/Google) ✗ –
  wir bekommen nur das Ergebnis, nicht die Rohdaten ✗.
- Ein echter Mehrquellen-Filter (Kalman) braucht **regelmäßige** Messungen; bei
  stündlichen Find-My-Berichten bringt er wenig ✗ – sinnvoll ist er für die
  GNSS-Spur ✓.
