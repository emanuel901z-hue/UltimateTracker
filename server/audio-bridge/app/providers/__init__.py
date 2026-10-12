"""Anbieterneutrale SIM-/SMS-Verwaltung (docs/sim-providers.md).

Die Bridge spricht nur noch mit dieser Schnittstelle. Konkrete Anbieter
(1NCE, EMnify, Twilio Super SIM, Soracom, Hologram, …) implementieren sie –
entweder als Code (`nce.py`) oder rein konfigurationsgetrieben (`generic.py`).
"""

from .base import SimInfo, SmsMessage, SimProvider, ProviderError  # noqa: F401
from .generic import GenericProvider
from .nce import NceProvider
from .whereversim import WhereverSimProvider


def get_provider(name: str | None = None, config: dict | None = None) -> SimProvider | None:
    """Provider anhand des Namens erzeugen.

    `name` kommt aus SIM_PROVIDER (Default: "nce", wenn Zugangsdaten gesetzt sind).
    Rückgabe None, wenn kein Provider konfiguriert ist – die Endpunkte antworten
    dann mit {"configured": false}.
    """
    import os

    chosen = (name or os.environ.get("SIM_PROVIDER") or "").strip().lower()
    if not chosen:
        chosen = "nce" if os.environ.get("1NCE_API_CLIENTID") or os.environ.get("NCE_API_CLIENTID") else ""
    if not chosen or chosen in ("none", "off", "disabled"):
        return None
    if chosen in ("nce", "1nce"):
        return NceProvider()
    if chosen in ("whereversim", "wherever", "wvs"):
        return WhereverSimProvider()
    if chosen in ("generic", "custom", "template"):
        return GenericProvider(config)
    raise ProviderError(f"Unbekannter SIM-Provider: {chosen!r} (erwartet: nce, whereversim, generic, none)")
