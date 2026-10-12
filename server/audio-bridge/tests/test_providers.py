"""Unit-Tests der Provider-Schicht (ohne Netzwerk).

Aufruf:  cd server/audio-bridge && python -m unittest discover -s tests -v
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers import get_provider  # noqa: E402
from app.providers.base import ProviderError  # noqa: E402
from app.providers.generic import GenericProvider, dig, expand_env, fill_template  # noqa: E402

EXAMPLE_CONFIG = {
    "name": "beispiel",
    "base_url": "https://api.example.com/v3",
    "auth": {"type": "header", "header_name": "X-API-Key", "header_value": "secret"},
    "endpoints": {
        "list_sims": {"method": "GET", "path": "/sims", "items": "$"},
        "send_sms": {"method": "POST", "path": "/sims/{iccid}/sms",
                     "body": {"payload": "{text}", "source": "{source}"}},
        "list_sms": {"method": "GET", "path": "/sims/{iccid}/sms", "items": "data.messages"},
        "sms_quota": {"method": "GET", "path": "/sims/{iccid}/quota/sms"},
    },
    "fields": {
        "sim": {"iccid": "id.iccid", "msisdn": "id.msisdn", "status": "state",
                "quota_sms": "quota.sms"},
        "sms": {"id": "message_id", "text": "body", "direction": "type",
                "state": "status", "source": "from"},
        "quota": {"remaining": "left", "total": "all"},
    },
    "maps": {"direction": {"1": "MT", "2": "MO"}, "state": {"4": "DELIVERED"}},
}


class TestHelpers(unittest.TestCase):
    def test_dig_root(self):
        self.assertEqual(dig({"a": 1}, "$"), {"a": 1})
        self.assertEqual(dig([1, 2], ""), [1, 2])

    def test_dig_nested(self):
        data = {"id": {"iccid": "8988"}, "data": {"messages": [{"x": 1}]}}
        self.assertEqual(dig(data, "id.iccid"), "8988")
        self.assertEqual(dig(data, "data.messages.0.x"), 1)
        self.assertIsNone(dig(data, "fehlt.tief"))

    def test_fill_template_recursive(self):
        template = {"payload": "{text}", "nested": [{"icc": "{iccid}"}]}
        filled = fill_template(template, {"text": "hallo", "iccid": "123"})
        self.assertEqual(filled, {"payload": "hallo", "nested": [{"icc": "123"}]})

    def test_expand_env_with_default(self):
        os.environ["UT_TEST_VALUE"] = "geheim"
        try:
            expanded = expand_env({"a": "${UT_TEST_VALUE}", "b": "${UT_FEHLT:-ersatz}", "c": 5})
        finally:
            os.environ.pop("UT_TEST_VALUE", None)
        self.assertEqual(expanded, {"a": "geheim", "b": "ersatz", "c": 5})

    def test_expand_env_with_leading_digit(self):
        # Regression: 1NCE-Variablen heißen "1NCE_API_CLIENTID" (führende Ziffer)
        os.environ["1NCE_TEST_ID"] = "abc"
        try:
            expanded = expand_env({"client_id": "${1NCE_TEST_ID}", "secret": "${1NCE_FEHLT:-x}"})
        finally:
            os.environ.pop("1NCE_TEST_ID", None)
        self.assertEqual(expanded, {"client_id": "abc", "secret": "x"})


class TestGenericProvider(unittest.TestCase):
    def test_configured_requires_base_and_endpoints(self):
        self.assertFalse(GenericProvider({}).configured())
        self.assertFalse(GenericProvider({"base_url": "https://x"}).configured())
        self.assertTrue(GenericProvider(EXAMPLE_CONFIG).configured())

    def test_unknown_auth_type_is_rejected(self):
        config = dict(EXAMPLE_CONFIG, auth={"type": "zauber"})
        with self.assertRaises(ProviderError):
            GenericProvider(config).configured()

    def test_headers_per_auth_type(self):
        header = GenericProvider(EXAMPLE_CONFIG)._headers()
        self.assertEqual(header, {"X-API-Key": "secret"})
        bearer = GenericProvider(dict(EXAMPLE_CONFIG, auth={"type": "bearer", "token": "t"}))._headers()
        self.assertEqual(bearer, {"Authorization": "Bearer t"})
        none = GenericProvider(dict(EXAMPLE_CONFIG, auth={"type": "none"}))._headers()
        self.assertEqual(none, {})

    def test_missing_endpoint_raises(self):
        provider = GenericProvider({"name": "x", "base_url": "https://x", "endpoints": {}})
        with self.assertRaises(ProviderError):
            provider._call("send_sms", {})


class TestGraphQlProvider(unittest.TestCase):
    """WhereverSIM-Stil: eine POST-URL, GraphQL-Body, verschachtelte Antworten."""

    CONFIG = {
        "name": "whereversim",
        "base_url": "https://graphql.api.whereversim.com/graphql",
        "auth": {"type": "header", "header_name": "Authorization", "header_value": "token"},
        "endpoints": {
            "list_sims": {"method": "POST", "path": "", "items": "data.listSims.items",
                          "body": {"query": "…", "variables": {"limit": 100}}},
            "send_sms": {"method": "POST", "path": "",
                         "body": {"query": "…", "variables": {"iccid": "{iccid}", "text": "{text}"}},
                         "expect": {"path": "data.sendSms", "equals": True}},
            "list_sms": {"method": "POST", "path": "", "items": "data.listSms.items",
                         "body": {"query": "…", "variables": {"iccid": "{iccid}"}}},
        },
        "fields": {
            "sim": {"iccid": "iccid", "msisdn": "msisdn", "status": "statusid", "imei": "imei"},
            "sms": {"id": "id", "text": "text", "direction": "direction",
                    "source": "originator", "submitted": "unixTimestampMs"},
        },
    }

    class FakeProvider(GenericProvider):
        def __init__(self, config, responses):
            super().__init__(config)
            self.responses = responses
            self.calls = []

        def _call(self, key, values):
            self.calls.append((key, values))
            return 200, self.responses[key]

    def test_list_sims_from_graphql_response(self):
        provider = self.FakeProvider(self.CONFIG, {"list_sims": {"data": {"listSims": {"items": [
            {"iccid": "8988", "imei": "8698", "msisdn": "+4917", "statusid": 3},
        ]}}}})
        sims = provider.list_sims()
        self.assertEqual(len(sims), 1)
        self.assertEqual(sims[0].iccid, "8988")
        self.assertEqual(sims[0].msisdn, "+4917")
        self.assertEqual(sims[0].status, "3")

    def test_send_sms_success_and_rejection(self):
        ok = self.FakeProvider(self.CONFIG, {"send_sms": {"data": {"sendSms": True}}})
        self.assertEqual(ok.send_sms("8988", "hallo"), {"id": None})
        self.assertEqual(ok.calls[0][1]["iccid"], "8988")

        rejected = self.FakeProvider(self.CONFIG, {"send_sms": {"data": {"sendSms": False}}})
        with self.assertRaises(ProviderError):
            rejected.send_sms("8988", "hallo")

    def test_list_sms_mapping(self):
        provider = self.FakeProvider(self.CONFIG, {"list_sms": {"data": {"listSms": {"items": [
            {"id": 7, "direction": "MO", "originator": "+4917", "text": "SOS",
             "unixTimestampMs": 1767225600000},
        ]}}}})
        messages = provider.list_sms("8988")
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].direction, "MO")
        self.assertEqual(messages[0].text, "SOS")
        self.assertEqual(messages[0].source, "+4917")


class TestShippedConfigs(unittest.TestCase):
    """Die mitgelieferten Beispielkonfigurationen müssen gültig und vollständig sein."""

    CONFIG_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "sim-providers")

    def _load(self, name):
        with open(os.path.join(self.CONFIG_DIR, name), encoding="utf-8") as handle:
            return json.load(handle)

    def test_examples_are_valid(self):
        # Die Beispielkonfigurationen nutzen ${…}-Platzhalter; für den Test
        # setzen wir Dummy-Werte, damit auch die Auth-Prüfung greift.
        keys = ("1NCE_API_CLIENTID", "1NCE_API_CLIENTSECRET", "WHEREVERSIM_API_TOKEN")
        saved = {key: os.environ.get(key) for key in keys}
        for key in keys:
            os.environ[key] = "testwert"
        try:
            for name in ("example-1nce-generic.json", "example-whereversim-generic.json"):
                config = self._load(name)
                provider = GenericProvider(config)
                self.assertTrue(provider.configured(), f"{name} ist nicht lauffähig konfiguriert")
                for key in ("list_sims", "send_sms", "list_sms"):
                    self.assertIn(key, provider.endpoints, f"{name} fehlt Endpunkt {key}")
                self.assertIn("iccid", provider.fields.get("sim", {}))
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


class TestRegistry(unittest.TestCase):
    def test_none_when_disabled(self):
        self.assertIsNone(get_provider("none"))
        self.assertIsNone(get_provider("off"))

    def test_1nce_selected(self):
        provider = get_provider("nce")
        self.assertEqual(provider.name, "nce")

    def test_generic_selected_with_config(self):
        provider = get_provider("generic", EXAMPLE_CONFIG)
        self.assertEqual(provider.name, "beispiel")

    def test_unknown_provider_raises(self):
        with self.assertRaises(ProviderError):
            get_provider("gibtsnicht")

    def test_default_without_credentials_is_none(self):
        saved = {key: os.environ.pop(key, None) for key in
                 ("SIM_PROVIDER", "1NCE_API_CLIENTID", "NCE_API_CLIENTID")}
        try:
            self.assertIsNone(get_provider(None))
        finally:
            for key, value in saved.items():
                if value is not None:
                    os.environ[key] = value


class TestNceProvider(unittest.TestCase):
    def test_configured_flag(self):
        from app.providers.nce import NceProvider

        self.assertTrue(NceProvider(client_id="a", client_secret="b").configured())
        self.assertFalse(NceProvider(client_id="", client_secret="").configured())

    def test_api_version_is_configurable(self):
        from app.providers.nce import NceProvider

        saved = os.environ.get("NCE_API_VERSION")
        os.environ["NCE_API_VERSION"] = "v3"
        try:
            self.assertEqual(NceProvider(client_id="a", client_secret="b").api_version, "v3")
        finally:
            if saved is None:
                os.environ.pop("NCE_API_VERSION", None)
            else:
                os.environ["NCE_API_VERSION"] = saved


if __name__ == "__main__":
    unittest.main()
