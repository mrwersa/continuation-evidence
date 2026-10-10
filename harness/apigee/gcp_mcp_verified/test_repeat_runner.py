"""Offline full-schedule and transport checks for the separate execution."""
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

from credentials import Credentials
from repeat_runner import Adapter, Guard, Journal, Management, Runner, Stop
from test_credentials import response
from test_runner import Clock, Fake


class HTTPResponse(io.BytesIO):
    def __init__(self, body=b"{}", status=200):
        super().__init__(body)
        self.status = status


class RepeatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "events.jsonl"
        self.log = Journal(self.path)
        self.addCleanup(self.log.close)
        self.clock = Clock()
        self.clock.now = 1000

    def auth(self):
        run = Mock(side_effect=lambda *a, **k: response(self.clock.now + 3600))
        return Credentials("researcher@example.invalid", self.clock, run)

    def test_full_schedule_with_refresh_and_long_deployments(self):
        auth = self.auth()
        manager = Management(self.log, auth, self.clock,
            send=lambda *a, **k: HTTPResponse())
        api = Fake(87400000)
        original_import = api.import_bundle
        keys = []
        attempts, remote_responses, backend = [], [], []
        original_request = api.request
        key_file = Path(self.tmp.name) / "api.key"
        key_file.write_text("offline-secret")
        adapter = object.__new__(Adapter)
        adapter.config = {"account": "test@example.invalid", "ssh_key_file": "unused",
                          "api_key_file": str(key_file)}
        adapter.log = self.log

        def import_bundle(variant):
            manager.request("POST", "organizations/your-gcp-project/apis", b"bundle")
            self.clock.sleep(100)
            return original_import(variant)

        def request(key, req):
            keys.append(key)
            row = original_request(key, req)
            row["request_id"] = req["id"]
            row["backend_log_status"] = "read"
            attempts.append({"task": key, "request": req})
            remote_responses.append(row)
            backend.extend(row["backend_matches"])
            with patch("repeat_runner.subprocess.run", return_value=Mock(
                    returncode=0, stdout=json.dumps(row))) as remote:
                result = adapter.request(key, req)
                remote.assert_called_once()
                return result

        api.import_bundle, api.request = import_bundle, request
        guard = Guard(1000, 87400, 3.2, .1, 1, self.clock)
        runner = Runner(api, self.log, guard, "repeat-20261010-abc12345", self.clock.sleep)
        self.assertTrue(runner.collect())
        rows = [json.loads(line) for line in self.path.read_text().splitlines()]
        statuses = [r for r in rows if r["kind"] == "sequence_status"]
        self.assertEqual(len(statuses), 90)
        self.assertTrue(all(r["status"] == "complete" for r in statuses))
        self.assertEqual(api.promotions, 110)
        self.assertEqual(guard.calls, 365)
        self.assertGreaterEqual(auth.refreshes, 4)
        self.assertTrue(all(k.startswith("repeat-20261010-abc12345-") for k in keys))
        self.assertLess(self.clock.now - 1000, 7 * 3600)
        self.assertNotIn("fabricated-token", self.path.read_text())
        from audit_repeat import audit_repeat
        summary = audit_repeat(rows, backend, attempts, remote_responses,
                               "repeat-20261010-abc12345")
        self.assertEqual(len(summary["sequences"]), 90)
        from integration import audit_transport
        transport = [{k: v for k, v in r.items() if k not in
                      ("backend_matches", "backend_log_status")} for r in remote_responses]
        audit_transport(remote_responses, transport)
        attempts[0]["task"] = "old-calibration"
        with self.assertRaisesRegex(AssertionError, "Remote task"):
            audit_repeat(rows, backend, attempts, remote_responses,
                         "repeat-20261010-abc12345")

    def test_separate_new_and_cumulative_cost_guards(self):
        Guard(1000, 87400, 10, .1, 1, self.clock)
        for prior, hourly, fixed in [(18, .1, 1), (0, .4, 1), (float("nan"), .1, 1)]:
            with self.subTest(prior=prior), self.assertRaises(Stop):
                Guard(1000, 87400, prior, hourly, fixed, self.clock)

    def test_management_401_and_timeout_never_replay(self):
        for method in ("GET", "POST"):
            for failure in (TimeoutError(), urllib.error.HTTPError(
                    "https://example.invalid", 401, "Unauthorised", {}, io.BytesIO(b"{}"))):
                with self.subTest(method=method, failure=type(failure).__name__):
                    send = Mock(side_effect=failure)
                    manager = Management(self.log, self.auth(), self.clock, send)
                    with self.assertRaises(Stop):
                        manager.request(method, "organizations/your-gcp-project/apis")
                    self.assertEqual(send.call_count, 1)

    def test_bad_credential_stops_before_management_dispatch(self):
        auth = Credentials("researcher@example.invalid", self.clock,
                           Mock(return_value=response(1100)))
        send = Mock()
        with self.assertRaises(RuntimeError):
            Management(self.log, auth, self.clock, send).request(
                "POST", "organizations/your-gcp-project/apis")
        send.assert_not_called()

    def test_wrong_project_is_rejected_before_credentials(self):
        auth, send = Mock(), Mock()
        with self.assertRaises(Stop):
            Management(self.log, auth, self.clock, send).request(
                "POST", "organizations/another-project/apis")
        auth.token.assert_not_called()
        send.assert_not_called()

    def test_unfrozen_entrypoint_cannot_reach_live_adapter(self):
        from unittest.mock import patch
        import live_repeat
        with patch.object(live_repeat, "ROOT", Path(self.tmp.name)):
            with self.assertRaisesRegex(Stop, "not frozen"):
                live_repeat.validate({}, self.clock.now)


if __name__ == "__main__":
    unittest.main()
