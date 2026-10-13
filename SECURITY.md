# Sicherheit

## Worum es hier geht

Dieses Projekt verarbeitet **Standortdaten und Sprachaufnahmen von Kindern**.
Bitte melde Sicherheitsprobleme verantwortungsvoll – und gehe davon aus, dass
jede Lücke hier unmittelbar Privatsphäre von Kindern betrifft.

## Melden

Bitte **nicht** als öffentliches Issue, sondern per E-Mail an den Maintainer
(siehe Profil/Commit-Historie) mit:

- betroffener Komponente (Firmware / Audio-Bridge / Compose / Caddy / Provider-Schicht)
- Version oder Commit-Hash
- Reproduktion (Schritte, ggf. Requests/Logs – **ohne** Zugangsdaten)
- Einschätzung der Auswirkung

Antwort in der Regel innerhalb weniger Tage. Es gibt kein Bug-Bounty-Programm.

## Betriebs-Sicherheit (Kurzfassung)

Die vollständige Checkliste steht in [`docs/deployment.md`](docs/deployment.md)
(Abschnitt „Operationszentrale & Internet-Betrieb"):

| Punkt | Umsetzung |
|---|---|
| TLS | Caddy-Profil `tls`; Let's Encrypt bei echter Domain (`TLS_ARG=<E-Mail>`) |
| Anmeldung | Benutzerkonten mit PBKDF2-Hashes, Sitzungstoken mit Ablauf, Passwortregeln |
| Ports | nur 80/443 nach außen; Datenbank/Traccar-API/Find-My bleiben intern |
| Secrets | `.env` und Zugangsdateien sind gitignoriert; Pre-Commit-Hook blockt sie |
| Aufbewahrung | Audionachrichten werden nach `RETENTION_DAYS` gelöscht (Standard 30) |
| Updates | Images sind auf feste Versionen/Digests gepinnt – bewusst aktualisieren |
| Backups | UI-Knopf (Audio, Datenbank, Ereignislog) + `scripts/backup-volumes.sh` |
| Dienst-Anmeldung | SSO über Einmal-Ticket (120 s, einmalig, nur mit Sitzung) – siehe unten |
| Geräte-Tokens | werden bei fehlender `.env` automatisch erzeugt und liegen in der Datenbank (gitignoriert) |
| Alternative | Tailscale/WireGuard statt offener Ports (keine Exposition) |

## Zwei bewusst offene Endpunkte

- **`GET /ca.crt`** liefert das Root-Zertifikat der lokalen Caddy-CA – ohne
  Anmeldung und über HTTP. Das ist Absicht: Der Download ist genau dann nötig,
  wenn HTTPS noch eine Warnung zeigt. Zertifikate sind öffentlich; der private
  Schlüssel bleibt in Caddy.
- **`GET /api/v1/auth/state`** meldet nur, ob schon ein Konto existiert (steuert
  die Erstanmeldung) – es gibt keine Benutzerdaten preis.

Die **Apple-Zugangsdaten** liegen ausschließlich lokal in
`macless-data/config.ini` (Rechte 0600) und werden nur vom Dienst selbst genutzt.
Die **Traccar-Zugangsdaten** für den Auto-Login stehen in `server/.env` bzw. im
State-Store der Bridge (`ADMIN-ZUGANG.txt` ist gitignoriert).

## Bewusste Grenzen

- Der Tracker ist **kein zertifiziertes Sicherheits- oder Medizinprodukt** und
  ersetzt keine Aufsicht.
- Die Apple-/Google-Find-My-Anbindungen sind **experimentell**; sie nutzen
  inoffizielle Schnittstellen und geben Daten an fremde Netzwerke weiter
  (optional, standardmäßig aus – siehe [`docs/findmy.md`](docs/findmy.md)).
- SMS ist bei 1NCE nur zwischen Gerät und Plattform möglich, nicht zwischen
  Handy und Gerät ([`docs/sms.md`](docs/sms.md)).
