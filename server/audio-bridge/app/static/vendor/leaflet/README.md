# Leaflet (vendored)

Diese Dateien stammen unverändert aus dem npm-Paket **leaflet@1.9.4**
(Bezug: <https://unpkg.com/leaflet@1.9.4/dist/…> bzw. `cdn.jsdelivr.net/npm/leaflet@1.9.4`).
Sie werden mitgeliefert, damit die Karte in der Eltern-UI **ohne externe
Skript-Aufrufe** lädt.

Lizenz: BSD-2-Clause (© 2010-2023 Volodymyr Agafonkin, © 2010-2011 CloudMade).
Volltext: <https://github.com/Leaflet/Leaflet/blob/v1.9.4/LICENSE>

## Prüfsummen (SHA-256 der eingecheckten Bytes)

| Datei | SHA-256 (SRI-Form) |
|---|---|
| `dist/leaflet.js` | `sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=` |
| `dist/leaflet.css` | `sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=` |
| `dist/images/marker-icon.png` | `sha256-V0w6XMqF9BFAhbaEFZbWLwDXyJLHsD8oy/owHesdxDc=` |
| `dist/images/marker-icon-2x.png` | `sha256-ABecTB7oMNOhCEEq4NKU9Vd2z+sIXGASmjmqb8SuJSg=` |
| `dist/images/marker-shadow.png` | `sha256-Jk9cZAM58ELdcpBiz8BMF/jqDymIK1OOOEjtjxDttNo=` |

Für `dist/leaflet.js` und `dist/leaflet.css` stimmen die Werte mit den
offiziell veröffentlichten SRI-Angaben für Leaflet 1.9.4 überein; die Bilder
wurden zusätzlich gegen zwei unabhängige CDNs (unpkg, jsDelivr) geprüft.

Aktualisierung: neue Version herunterladen, `README.md` neu erzeugen
(`git cat-file`-Prüfsummen), Werte gegen die offizielle SRI-Angabe vergleichen.
Die Dateien sind in `.gitattributes` von der Zeilenenden-Normalisierung
ausgenommen (`-text`), damit die Prüfsummen beim Klonen erhalten bleiben.
