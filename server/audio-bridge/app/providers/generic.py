"""Konfigurationsgetriebener Provider – Template für andere Anbieter.

Der Anbieter wird als JSON beschrieben (Pfad in SIM_PROVIDER_CONFIG), z. B.:

{
  "name": "mein-anbieter",
  "base_url": "https://api.example.com/v3",
  "auth": {"type": "basic", "username": "…", "password": "…"},
  "endpoints": {
    "list_sims":  {"method": "GET",  "path": "/sims", "items": "$"},
    "send_sms":   {"method": "POST", "path": "/sims/{iccid}/sms",
                   "body": {"payload": "{text}", "source": "{source}"}},
    "list_sms":   {"method": "GET",  "path": "/sims/{iccid}/sms", "items": "$"},
    "sms_quota":  {"method": "GET",  "path": "/sims/{iccid}/quota/sms"}
  },
  "fields": {
    "sim": {"iccid": "iccid", "msisdn": "msisdn", "status": "status",
            "label": "label", "imei": "imei", "quota_sms": "current_quota_SMS"},
    "sms": {"id": "id", "text": "payload", "direction": "sms_type",
            "state": "status", "source": "source_address",
            "submitted": "submit_date", "delivered": "delivery_date"},
    "quota": {"remaining": "volume", "total": "total_volume"}
  },
  "maps": {"direction": {"1": "MT", "2": "MO"},
           "state": {"2": "PENDING", "4": "DELIVERED", "5": "FAILED"}}
}

Unterstützte Auth-Typen: none, basic, bearer, header, oauth2
(client_credentials, optional per Basic-Auth).
"""

from __future__ import annotations

import os
import re
import time

from .base import ProviderError, SimInfo, SimProvider, SmsMessage

AUTH_TYPES = ("none", "basic", "bearer", "header", "oauth2")

# Erlaubt auch führende Ziffern: 1NCE nennt seine Variablen z. B. "1NCE_API_CLIENTID"
# (gültig in .env/Compose, nur nicht als Shell-Variable).
ENV_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}")


def expand_env(value):
    """"${VAR}" bzw. "${VAR:-default}" aus der Umgebung ersetzen (rekursiv).

    Damit stehen Zugangsdaten in der .env und nicht in der Provider-Datei.
    """
    if isinstance(value, str):
        return ENV_PATTERN.sub(lambda match: os.environ.get(match.group(1), match.group(2) or ""), value)
    if isinstance(value, dict):
        return {key: expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    return value


def dig(data, path: str):
    """Feld aus verschachtelten Daten holen: "$" = Wurzel, sonst "a.b.c"."""
    if path in ("", "$", None):
        return data
    current = data
    for part in str(path).split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
    return current


def fill_template(template, values: dict):
    """Platzhalter in Strings ersetzen ({iccid}, {text}, {source}) – rekursiv."""
    if isinstance(template, str):
        result = template
        for key, value in values.items():
            result = result.replace("{" + key + "}", str(value))
        return result
    if isinstance(template, dict):
        return {key: fill_template(value, values) for key, value in template.items()}
    if isinstance(template, list):
        return [fill_template(item, values) for item in template]
    return template


class GenericProvider(SimProvider):
    name = "generic"

    def __init__(self, config: dict | None = None):
        self.config = expand_env(config or {})
        self.name = str(self.config.get("name") or "generic")
        self.base_url = str(self.config.get("base_url") or "").rstrip("/")
        self.auth = self.config.get("auth") or {"type": "none"}
        self.endpoints = self.config.get("endpoints") or {}
        self.fields = self.config.get("fields") or {}
        self.maps = self.config.get("maps") or {}
        self._token = {"value": "", "expires_at": 0.0}

    # --- Auth ---------------------------------------------------------------
    def configured(self) -> bool:
        if not self.base_url or not self.endpoints:
            return False
        auth_type = str(self.auth.get("type") or "none").lower()
        if auth_type not in AUTH_TYPES:
            raise ProviderError(f"Unbekannter Auth-Typ: {auth_type!r} (erlaubt: {', '.join(AUTH_TYPES)})")
        if auth_type == "basic":
            return bool(self.auth.get("username"))
        if auth_type == "bearer":
            return bool(self.auth.get("token"))
        if auth_type == "header":
            return bool(self.auth.get("header_name"))
        if auth_type == "oauth2":
            return bool(self.auth.get("token_url") and self.auth.get("client_id"))
        return True

    def _headers(self) -> dict:
        auth_type = str(self.auth.get("type") or "none").lower()
        if auth_type == "bearer":
            return {"Authorization": f"Bearer {self.auth.get('token')}"}
        if auth_type == "header":
            return {str(self.auth.get("header_name")): str(self.auth.get("header_value") or "")}
        if auth_type == "oauth2":
            return {"Authorization": f"Bearer {self._oauth_token()}"}
        return {}

    def _oauth_token(self) -> str:
        now = time.time()
        if self._token["value"] and self._token["expires_at"] > now + 30:
            return self._token["value"]

        import requests

        body = {"grant_type": str(self.auth.get("grant_type") or "client_credentials")}
        kwargs = {"json": body, "timeout": 20}
        if self.auth.get("basic_auth", True):
            kwargs["auth"] = (self.auth.get("client_id"), self.auth.get("client_secret"))
        else:
            body["client_id"] = self.auth.get("client_id")
            body["client_secret"] = self.auth.get("client_secret")

        response = requests.post(str(self.auth.get("token_url")), **kwargs)
        if response.status_code != 200:
            raise ProviderError(f"Token-Anfrage fehlgeschlagen (HTTP {response.status_code})")
        data = response.json()
        token = str(dig(data, str(self.auth.get("token_field") or "access_token")) or "")
        if not token:
            raise ProviderError("Token-Antwort ohne access_token")
        self._token["value"] = token
        self._token["expires_at"] = now + float(dig(data, "expires_in") or 3600)
        return token

    # --- HTTP ---------------------------------------------------------------
    def _call(self, key: str, values: dict) -> tuple[int, object]:
        import requests

        spec = self.endpoints.get(key)
        if not spec:
            raise ProviderError(f"Endpunkt '{key}' ist in der Provider-Konfiguration nicht definiert")
        url = self.base_url + str(fill_template(spec.get("path", ""), values))
        method = str(spec.get("method") or "GET").upper()
        kwargs = {"headers": self._headers(), "timeout": 30}
        if spec.get("body"):
            kwargs["json"] = fill_template(spec["body"], values)
        auth_type = str(self.auth.get("type") or "none").lower()
        if auth_type == "basic":
            kwargs["auth"] = (self.auth.get("username"), self.auth.get("password"))

        response = requests.request(method, url, **kwargs)
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        return response.status_code, payload

    def _items(self, spec: dict, payload) -> list:
        items = dig(payload, str(spec.get("items") or "$"))
        if isinstance(items, list):
            return items
        if isinstance(items, dict):
            return [items]
        return []

    def _mapped(self, kind: str, value):
        mapping = self.maps.get(kind) or {}
        return mapping.get(str(value), value)

    # --- Schnittstelle ------------------------------------------------------
    def list_sims(self) -> list[SimInfo]:
        spec = self.endpoints.get("list_sims") or {}
        status, payload = self._call("list_sims", {})
        if status != 200:
            raise ProviderError(f"{self.name} SIM-Liste: HTTP {status} {str(payload)[:160]}")
        fields = self.fields.get("sim") or {}
        result = []
        for item in self._items(spec, payload):
            result.append(
                SimInfo(
                    iccid=str(dig(item, fields.get("iccid", "iccid")) or ""),
                    msisdn=str(dig(item, fields.get("msisdn", "msisdn")) or ""),
                    status=str(dig(item, fields.get("status", "status")) or ""),
                    label=str(dig(item, fields.get("label", "label")) or ""),
                    imei=str(dig(item, fields.get("imei", "imei")) or ""),
                    quota_sms=dig(item, fields.get("quota_sms")) if fields.get("quota_sms") else None,
                    raw=item if isinstance(item, dict) else {},
                )
            )
        return result

    def sms_quota(self, iccid: str) -> dict | None:
        if "sms_quota" not in self.endpoints:
            return None
        status, payload = self._call("sms_quota", {"iccid": iccid})
        if status != 200 or not isinstance(payload, dict):
            return None
        fields = self.fields.get("quota") or {}
        return {
            "remaining": dig(payload, fields.get("remaining", "volume")),
            "total": dig(payload, fields.get("total", "total_volume")),
        }

    def send_sms(self, iccid: str, text: str) -> dict:
        status, payload = self._call("send_sms", {"iccid": iccid, "text": text, "source": "12345"})
        if status not in (200, 201, 202):
            raise ProviderError(f"{self.name} SMS-Versand: HTTP {status} {str(payload)[:160]}")

        # Manche Anbieter melden den Erfolg nur als Wert im Body (z. B. GraphQL:
        # {"data": {"sendSms": false}}) – optional prüfbar über "expect".
        expect = (self.endpoints.get("send_sms") or {}).get("expect")
        if isinstance(expect, dict):
            value = dig(payload, str(expect.get("path") or "$"))
            wanted = expect.get("equals", True)
            if value != wanted:
                raise ProviderError(
                    f"{self.name}: Versand abgelehnt (erwartet {wanted!r}, Antwort {value!r})"
                )

        fields = self.fields.get("sms") or {}
        sms_id = dig(payload, fields.get("id", "id")) if isinstance(payload, dict) else None
        return {"id": sms_id}

    def list_sms(self, iccid: str, limit: int = 20) -> list[SmsMessage]:
        spec = self.endpoints.get("list_sms") or {}
        status, payload = self._call("list_sms", {"iccid": iccid})
        if status != 200:
            raise ProviderError(f"{self.name} SMS-Liste: HTTP {status} {str(payload)[:160]}")
        fields = self.fields.get("sms") or {}
        messages = []
        for item in self._items(spec, payload)[: max(1, min(limit, 100))]:
            messages.append(
                SmsMessage(
                    sms_id=dig(item, fields.get("id", "id")),
                    direction=str(self._mapped("direction", dig(item, fields.get("direction", "direction"))) or ""),
                    state=str(self._mapped("state", dig(item, fields.get("state", "state"))) or ""),
                    text=str(dig(item, fields.get("text", "payload")) or ""),
                    source=str(dig(item, fields.get("source", "source")) or ""),
                    submitted=str(dig(item, fields.get("submitted", "submitted")) or ""),
                    delivered=str(dig(item, fields.get("delivered", "delivered")) or ""),
                    raw=item if isinstance(item, dict) else {},
                )
            )
        return messages
