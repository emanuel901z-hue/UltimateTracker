"""wherever SIM Provider (GraphQL / AWS AppSync).

Referenz: https://docs.whereversim.com/ (Stand 2026-10). Besonderheiten
gegenüber REST-Anbietern:

* **eine** POST-URL, Abfragen/Mutationen stecken im Body (GraphQL)
* Auth per statischem Header `Authorization: <Token>`
* Fehler kommen als `{"errors": [...]}` mit HTTP 200 → muss ausgewertet werden
* Paginierung über `nextToken`
* Echtzeit über **WebSocket-Subscriptions** (AppSync-Protokoll mit
  `connection_init`/`connection_ack`/`start`/`data`) – siehe `watch_sms()`

Das kann der Generic-Template-Provider nicht (Subscriptions, GraphQL-Fehler),
deshalb hier eine eigene Klasse – Muster für weitere Sonderfälle.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import uuid

from .base import ProviderError, SimInfo, SimProvider, SmsMessage

QUERY_LIST_SIMS = """
query ListSims($limit: Int!, $nextToken: String) {
  listSims(limit: $limit, nextToken: $nextToken) {
    items { iccid imei msisdn statusid }
    nextToken
  }
}
"""

QUERY_LIST_SMS = """
query ListSms($iccid: ID!, $limit: Int!, $nextToken: String) {
  listSms(iccid: $iccid, limit: $limit, nextToken: $nextToken) {
    items { id iccid direction originator destination text unixTimestampMs }
    nextToken
  }
}
"""

MUTATION_SEND_SMS = """
mutation SendSms($iccid: ID!, $text: String!) {
  sendSms(iccid: $iccid, text: $text)
}
"""

QUERY_CUSTOMER = """
query GetCustomerData { getCustomerData { customerid current_name geolocation_status } }
"""

QUERY_LOCATION = """
query GetLocationData($iccid: String!) {
  getLocationData(iccid: $iccid) { iccid longitude latitude receivedAtMs }
}
"""

SUBSCRIPTION_ON_SMS = """
subscription OnSms($iccid: ID!) {
  onSms(iccid: $iccid) { id iccid direction originator destination text unixTimestampMs }
}
"""


def sms_from_item(item: dict) -> SmsMessage:
    """GraphQL-SMS-Objekt → SmsMessage (reine Funktion, testbar)."""
    return SmsMessage(
        sms_id=item.get("id"),
        direction=str(item.get("direction") or ""),
        state="",
        text=str(item.get("text") or ""),
        source=str(item.get("originator") or ""),
        submitted=str(item.get("unixTimestampMs") or ""),
        raw=item,
    )


def parse_subscription_message(message: dict) -> SmsMessage | None:
    """AppSync-`data`-Rahmen → SmsMessage (None, wenn keine SMS enthalten).

    AWS AppSync liefert `payload.data` als **JSON-String**:
      {"type": "data", "payload": {"data": "{\\"onSms\\": {…}}"}}
    """
    if not isinstance(message, dict):
        return None
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            return None
    if not isinstance(data, dict):
        return None
    sms = data.get("onSms")
    return sms_from_item(sms) if isinstance(sms, dict) else None


class WhereverSimProvider(SimProvider):
    name = "whereversim"

    def __init__(self, base: str | None = None, token: str | None = None, ws_url: str | None = None):
        self.base = (base or os.environ.get("WHEREVERSIM_API_URL")
                     or "https://graphql.api.whereversim.com/graphql").rstrip("/")
        self.token = token if token is not None else os.environ.get("WHEREVERSIM_API_TOKEN", "")
        self.ws_url = ws_url or os.environ.get("WHEREVERSIM_WS_URL") or self._default_ws_url()
        self._customer_id: int | None = None

    def _default_ws_url(self) -> str:
        base = self.base[: -len("/graphql")] if self.base.endswith("/graphql") else self.base
        return base.replace("https://", "wss://").replace("http://", "ws://") + "/graphql/realtime"

    def _host(self) -> str:
        host = self.ws_url.split("://", 1)[-1].split("/", 1)[0]
        return host

    def configured(self) -> bool:
        return bool(self.token)

    # --- GraphQL ------------------------------------------------------------
    def _graphql(self, query: str, variables: dict | None = None) -> dict:
        if not self.configured():
            raise ProviderError("WHEREVERSIM_API_TOKEN fehlt")
        import requests

        response = requests.post(
            self.base,
            headers={"Authorization": self.token, "Content-Type": "application/json"},
            json={"query": query, "variables": variables or {}},
            timeout=30,
        )
        if response.status_code != 200:
            raise ProviderError(f"wherever SIM: HTTP {response.status_code} {response.text[:160]}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("wherever SIM: Antwort ist kein JSON") from exc
        if payload.get("errors"):
            messages = "; ".join(str(err.get("message", err)) for err in payload["errors"][:3])
            raise ProviderError(f"wherever SIM GraphQL-Fehler: {messages}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ProviderError("wherever SIM: Antwort ohne data")
        return data

    # --- Schnittstelle ------------------------------------------------------
    def list_sims(self) -> list[SimInfo]:
        sims: list[SimInfo] = []
        next_token = None
        for _ in range(20):  # Notbremse gegen Endlosschleifen
            data = self._graphql(QUERY_LIST_SIMS, {"limit": 100, "nextToken": next_token})
            block = data.get("listSims") or {}
            for item in block.get("items") or []:
                status = item.get("statusid")
                sims.append(SimInfo(
                    iccid=str(item.get("iccid") or ""),
                    msisdn=str(item.get("msisdn") or ""),
                    status="" if status is None else str(status),
                    imei=str(item.get("imei") or ""),
                    raw=item,
                ))
            next_token = block.get("nextToken")
            if not next_token:
                break
        return sims

    def sms_quota(self, iccid: str) -> dict | None:
        # Die API bietet kein SMS-Kontingent pro SIM (nur Gesamtstatistiken).
        return None

    def send_sms(self, iccid: str, text: str) -> dict:
        data = self._graphql(MUTATION_SEND_SMS, {"iccid": iccid, "text": text})
        if data.get("sendSms") is not True:
            raise ProviderError(f"wherever SIM: Versand abgelehnt (Antwort {data.get('sendSms')!r})")
        return {"id": None}

    def list_sms(self, iccid: str, limit: int = 20) -> list[SmsMessage]:
        data = self._graphql(
            QUERY_LIST_SMS,
            {"iccid": iccid, "limit": max(1, min(limit, 100)), "nextToken": None},
        )
        block = data.get("listSms") or {}
        return [sms_from_item(item) for item in (block.get("items") or [])]

    # --- Zusatzfunktionen ---------------------------------------------------
    def customer_id(self) -> int | None:
        """Kundennummer (wird für Abos gebraucht)."""
        if self._customer_id is None:
            data = self._graphql(QUERY_CUSTOMER)
            customer = data.get("getCustomerData") or {}
            value = customer.get("customerid")
            self._customer_id = int(value) if isinstance(value, (int, str)) and str(value).isdigit() else None
        return self._customer_id

    def network_location(self, iccid: str) -> dict | None:
        """Netzbasierte Position (muss vom Anbieter für die SIM freigeschaltet sein)."""
        data = self._graphql(QUERY_LOCATION, {"iccid": iccid})
        location = data.get("getLocationData")
        if not isinstance(location, dict) or location.get("latitude") is None:
            return None
        return {
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "received_at_ms": location.get("receivedAtMs"),
            "source": "network",
        }

    # --- Echtzeit (AppSync-WebSocket) ---------------------------------------
    def supports_watch(self) -> bool:
        return True

    async def watch_sms(self, iccid: str, callback) -> None:
        """SMS in Echtzeit abonnieren (AppSync `onSms`), mit Wiederverbindung."""
        try:
            import websockets
        except ImportError as exc:  # uvicorn[standard] bringt websockets mit
            raise ProviderError("Paket 'websockets' ist nicht installiert") from exc
        if not self.configured():
            raise ProviderError("WHEREVERSIM_API_TOKEN fehlt")

        header = base64.b64encode(
            json.dumps({"host": self._host(), "Authorization": self.token},
                       separators=(",", ":")).encode()
        ).decode()
        url = f"{self.ws_url}?header={header}&payload=e30="

        backoff = 2
        while True:
            try:
                async with websockets.connect(url, subprotocols=["graphql-ws"], ping_interval=30) as socket:
                    await socket.send(json.dumps({"type": "connection_init"}))
                    ack = json.loads(await asyncio.wait_for(socket.recv(), timeout=15))
                    if ack.get("type") != "connection_ack":
                        raise ProviderError(f"kein connection_ack (erhalten: {ack.get('type')!r})")

                    start_payload = {
                        "data": json.dumps({"query": SUBSCRIPTION_ON_SMS,
                                            "variables": {"iccid": iccid}}),
                        "extensions": {"authorization": {"host": self._host(),
                                                         "Authorization": self.token}},
                    }
                    await socket.send(json.dumps({"id": str(uuid.uuid4()), "type": "start",
                                                  "payload": start_payload}))
                    print(f"[whereversim] Subscription aktiv für ICCID {iccid}", flush=True)
                    backoff = 2

                    async for raw in socket:
                        try:
                            message = json.loads(raw)
                        except ValueError:
                            continue
                        if message.get("type") == "error":
                            print(f"[whereversim] Subscription-Fehler: {message.get('payload')!r}",
                                  flush=True)
                            break
                        if message.get("type") != "data":
                            continue
                        sms = parse_subscription_message(message)
                        if sms is None:
                            continue
                        result = callback(sms)
                        if asyncio.iscoroutine(result):
                            await result
                    # Verbindung wurde regulär beendet (z. B. durch den Server)
                    print("[whereversim] Subscription beendet – neuer Versuch in 2s", flush=True)
                    await asyncio.sleep(2)
                    backoff = 2
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - jede Ursache → neuer Versuch
                print(f"[whereversim] Verbindung verloren ({exc!r}) – neuer Versuch in {backoff}s",
                      flush=True)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
