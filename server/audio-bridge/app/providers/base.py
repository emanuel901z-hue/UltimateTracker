"""Gemeinsame Typen und Schnittstelle der SIM-Provider."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ProviderError(RuntimeError):
    """Fehler des Anbieters (Auth, HTTP, unerwartete Antwort)."""


class SimInfo:
    def __init__(self, iccid: str, msisdn: str = "", status: str = "", label: str = "",
                 imei: str = "", quota_sms=None, raw: dict | None = None):
        self.iccid = iccid
        self.msisdn = msisdn
        self.status = status
        self.label = label
        self.imei = imei
        self.quota_sms = quota_sms
        self.raw = raw or {}

    def as_dict(self) -> dict:
        return {
            "iccid": self.iccid,
            "msisdn": self.msisdn,
            "status": self.status,
            "label": self.label,
            "imei": self.imei,
            "sms_quota": self.quota_sms,
        }


class SmsMessage:
    def __init__(self, sms_id="", direction: str = "", state: str = "", text: str = "",
                 source: str = "", submitted: str = "", delivered: str = "", raw: dict | None = None):
        self.id = sms_id
        self.direction = direction
        self.state = state
        self.text = text
        self.source = source
        self.submitted = submitted
        self.delivered = delivered
        self.raw = raw or {}

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "direction": self.direction,
            "state": self.state,
            "payload": self.text,
            "source": self.source,
            "submit_date": self.submitted,
            "delivery_date": self.delivered,
        }


class SimProvider(ABC):
    """Schnittstelle, die jeder Anbieter erfüllen muss.

    Alle Methoden werfen ProviderError bei Fehlern; die API-Schicht übersetzt
    das in HTTP 502 mit lesbarer Meldung.
    """

    name: str = "abstract"

    @abstractmethod
    def configured(self) -> bool:
        """Sind die nötigen Zugangsdaten vorhanden?"""

    @abstractmethod
    def list_sims(self) -> list[SimInfo]:
        """Alle SIMs des Kontos (für die Zuordnung Gerät ↔ SIM)."""

    @abstractmethod
    def sms_quota(self, iccid: str) -> dict | None:
        """SMS-Kontingent einer SIM (None, wenn der Anbieter das nicht kann)."""

    @abstractmethod
    def send_sms(self, iccid: str, text: str) -> dict:
        """MT-SMS an eine SIM senden. Rückgabe: {"id": …} o. Ä."""

    @abstractmethod
    def list_sms(self, iccid: str, limit: int = 20) -> list[SmsMessage]:
        """MT-/MO-Verlauf einer SIM."""
