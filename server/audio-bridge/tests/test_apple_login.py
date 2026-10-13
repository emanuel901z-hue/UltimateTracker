"""Unit-Tests des Apple-Anmelde-Helfers (`server/apple-login/watch.py`).

Der Helfer führt die Apple-Anmeldung aus und reicht den SMS-2FA-Code aus einer
Datei nach (Eltern-UI). Getestet wird die Zustandsmaschine mit einem
Ersatz-Login – der echte Login braucht Apple + 2FA.

Aufruf:  cd server/audio-bridge && python -m unittest discover -s tests -v
"""

import importlib
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
WATCH_DIR = HERE.parents[2] / "apple-login"  # server/apple-login
sys.path.insert(0, str(WATCH_DIR))


class AppleLoginHelperTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.login_dir = tmp / "apple-login"
        self.auth_file = tmp / "auth.json"
        os.environ.update({
            "APPLE_LOGIN_DIR": str(self.login_dir),
            "APPLE_AUTH_FILE": str(self.auth_file),
            "APPLE_LOGIN_CWD": str(tmp),
            "APPLE_LOGIN_POLL_S": "0.05",
        })
        self.watch = importlib.reload(importlib.import_module("watch"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _set_login_cmd(self, body: list[str]) -> None:
        """Ersatz-Login aus Python-Zeilen bauen und als Kommando setzen."""
        script = Path(self._tmp.name) / "fake_login.py"
        script.write_text("\n".join(body) + "\n", encoding="utf-8")
        os.environ["APPLE_LOGIN_CMD"] = f'"{sys.executable}" "{script}"'
        self.watch = importlib.reload(self.watch)

    def _prompt_login(self, write_auth: bool = True) -> None:
        """Ersatz-Login: fragt einen Code ab und schreibt (optional) auth.json."""
        body = [
            "import os, pathlib, sys",
            "sys.stdout.write('Enter SMS 2FA code: ')",
            "sys.stdout.flush()",
            "code = input()",
            "print('received=' + code)",
        ]
        if write_auth:
            body.append("pathlib.Path(os.environ['APPLE_AUTH_FILE']).write_text('{}')")
        self._set_login_cmd(body)

    def _state(self) -> str:
        import json
        status = self.watch.DIR / "status"
        if not status.exists():
            return ""
        return json.loads(status.read_text(encoding="utf-8"))["state"]

    def _wait_for(self, state: str, timeout: float = 15.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._state() == state:
                return True
            time.sleep(0.05)
        return False

    def test_code_is_delivered_and_auth_written(self) -> None:
        self._prompt_login()
        worker = threading.Thread(target=self.watch.run_login, daemon=True)
        worker.start()
        self.assertTrue(self._wait_for("waiting"), f"Zustand nicht 'waiting': {self._state()!r}")
        (self.watch.DIR / "code").write_text("123456\n", encoding="utf-8")
        worker.join(timeout=15)
        self.assertFalse(worker.is_alive(), "run_login kehrt nicht zurück")
        self.assertEqual(self._state(), "done")
        log = (self.watch.DIR / "log").read_text(encoding="utf-8")
        self.assertIn("received=123456", log)

    def test_code_written_before_prompt_is_used(self) -> None:
        self._prompt_login()
        self.watch.DIR.mkdir(parents=True, exist_ok=True)
        (self.watch.DIR / "code").write_text("654321\n", encoding="utf-8")
        self.watch.run_login()
        self.assertEqual(self._state(), "done")
        self.assertIn("received=654321",
                      (self.watch.DIR / "log").read_text(encoding="utf-8"))

    def test_missing_auth_reports_error(self) -> None:
        self._set_login_cmd(["print('kein Login moeglich')"])
        self.watch.run_login()
        self.assertEqual(self._state(), "error")
        self.assertIn("kein Login moeglich",
                      (self.watch.DIR / "log").read_text(encoding="utf-8"))

    def test_status_file_is_written(self) -> None:
        self.watch.DIR.mkdir(parents=True, exist_ok=True)
        self.watch.write_status("waiting")
        self.assertEqual(self._state(), "waiting")


if __name__ == "__main__":
    unittest.main()
