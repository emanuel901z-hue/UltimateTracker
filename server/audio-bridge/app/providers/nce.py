"""1NCE-Provider (Management API v2, docs/1NCE)."""

from __future__ import annotations

import os
import time

from .base import ProviderError, SimInfo, SimProvider, SmsMessage

DIRECTIONS = {1: "MT", 2: "MO"}
STATES = {2: "PENDING", 4: "DELIVERED", 5: "FAILED", 6: "EXPIRED"}


class NceProvider(SimProvider):
    name = "nce"

    def __init__(self, base: str | None = None, client_id: str | None = None,
                 client_secret: str | None = None, source_address: str | None = None):
        # Version steckt in den Pfaden (v2); ein Sprung auf v3 wäre hier zentral.
        self.api_version = os.environ.get("NCE_API_VERSION", "v2")
        self.base = (base or os.environ.get("NCE_API_BASE")
                     or "https://api.1nce.com/management-api").rstrip("/")
        # Das Portal nennt die Zugangsdaten "1NCE_API_*"; beide Schreibweisen ok.
        self.client_id = client_id or os.environ.get("1NCE_API_CLIENTID") \
            or os.environ.get("NCE_API_CLIENTID", "")
        self.client_secret = client_secret or os.environ.get("1NCE_API_CLIENTSECRET") \
            or os.environ.get("NCE_API_CLIENTSECRET", "")
        self.source_address = source_address or os.environ.get("NCE_SMS_SOURCE", "12345")
        self._token = {"value": "", "expires_at": 0.0}

    # --- Auth ---------------------------------------------------------------
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _access_token(self) -> str:
        if not self.configured():
            raise ProviderError("1NCE-Zugangsdaten fehlen (1NCE_API_CLIENTID/…SECRET)")
        now = time.time()
        if self._token["value"] and self._token["expires_at"] > now + 30:
            return self._token["value"]

        import requests

        response = requests.post(
            f"{self.base}/oauth/token",
            auth=(self.client_id, self.client_secret),
            json={"grant_type": "client_credentials"},
            timeout=20,
        )
        if response.status_code != 200:
            raise ProviderError(
                f"1NCE-Token fehlgeschlagen (HTTP {response.status_code}): {response.text[:160]}"
            )
        data = response.json()
        token = str(data.get("access_token") or "")
        if not token:
            raise ProviderError("1NCE-Antwort ohne access_token")
        self._token["value"] = token
        self._token["expires_at"] = now + float(data.get("expires_in") or 3600)
        return token

    def _request(self, method: str, path: str, **kwargs):
        import requests

        response = requests.request(
            method,
            f"{self.base}{path}",
            headers={"Authorization": f"Bearer {self._access_token()}", "Accept": "application/json"},
            timeout=30,
            **kwargs,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        return response.status_code, payload

    # --- Schnittstelle ------------------------------------------------------
    def list_sims(self) -> list[SimInfo]:
        status, sims = self._request("GET", f"/{self.api_version}/sims")
        if status != 200 or not isinstance(sims, list):
            raise ProviderError(f"1NCE SIM-Liste: HTTP {status} {str(sims)[:160]}")
        return [
            SimInfo(
                iccid=str(sim.get("iccid") or ""),
                msisdn=str(sim.get("msisdn") or ""),
                status=str(sim.get("status") or ""),
                label=str(sim.get("label") or ""),
                imei=str(sim.get("imei") or ""),
                quota_sms=sim.get("current_quota_SMS"),
                raw=sim,
            )
            for sim in sims
        ]

    def sms_quota(self, iccid: str) -> dict | None:
        status, quota = self._request("GET", f"/{self.api_version}/sims/{iccid}/quota/sms")
        if status != 200 or not isinstance(quota, dict):
            return None
        return {
            "remaining": quota.get("volume"),
            "total": quota.get("total_volume"),
            "expires": quota.get("expiry_date"),
        }

    def send_sms(self, iccid: str, text: str) -> dict:
        status, payload = self._request(
            "POST",
            f"/{self.api_version}/sims/{iccid}/sms",
            json={"source_address": self.source_address, "payload": text},
        )
        if status not in (200, 201):
            raise ProviderError(f"1NCE SMS-Versand: HTTP {status} {str(payload)[:160]}")
        return {"id": payload.get("id") if isinstance(payload, dict) else None}

    def list_sms(self, iccid: str, limit: int = 20) -> list[SmsMessage]:
        status, messages = self._request("GET", f"/{self.api_version}/sims/{iccid}/sms")
        if status != 200 or not isinstance(messages, list):
            raise ProviderError(f"1NCE SMS-Liste: HTTP {status} {str(messages)[:160]}")
        return [
            SmsMessage(
                sms_id=msg.get("id"),
                direction=DIRECTIONS.get(msg.get("sms_type"), msg.get("sms_type")),
                state=STATES.get(msg.get("status"), msg.get("status")),
                text=msg.get("payload") or "",
                source=msg.get("source_address") or "",
                submitted=msg.get("submit_date") or "",
                delivered=msg.get("delivery_date") or "",
                raw=msg,
            )
            for msg in messages[: max(1, min(limit, 100))]
        ]
