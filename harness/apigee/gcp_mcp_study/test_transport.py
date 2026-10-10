"""Test real transport entry points with network and subprocess calls mocked."""
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import remote_call
from live import Adapter, Management
from runner import Journal, Stop, classify


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.log = Journal(self.root / "events.jsonl")
        self.addCleanup(self.log.close)

    def test_management_timeout_is_one_attempt(self):
        manager = Management(self.log)
        manager.token, manager.token_time = "test-token", time.time()
        with patch("live.urllib.request.urlopen", side_effect=TimeoutError()) as send:
            with self.assertRaises(TimeoutError):
                manager.request("POST", "organizations/your-gcp-project/apis?action=import&name=mcp-lab-refund", b"test")
            self.assertEqual(send.call_count, 1)
        rows = [json.loads(x) for x in (self.root / "events.jsonl").read_text().splitlines()]
        self.assertEqual(rows[0]["kind"], "management_reserved")
        self.assertNotIn("test-token", (self.root / "events.jsonl").read_text())

    def test_remote_subprocess_timeout_has_no_retry(self):
        adapter = Adapter({"ssh_key_file": "/tmp/example-key"}, self.log)
        with patch("live.subprocess.run", side_effect=TimeoutError()) as run:
            with self.assertRaises(TimeoutError):
                adapter.request("test", {"id": "a"})
            self.assertEqual(run.call_count, 1)

    def prepare_remote(self):
        (self.root / "remote_config.json").write_text(json.dumps({"deadline": time.time()+1000, "expiry": time.time()+1000,
            "url": "https://example.invalid/mcp", "host": "example.invalid", "connect_ip": "127.0.0.1"}))
        (self.root / "api.key").write_text("test-only")
        (self.root / "backend.jsonl").write_text("")
        return {"task": "test", "request": {"jsonrpc": "2.0", "id": "request1", "method": "tools/call", "params": {"name": "refund", "arguments": {"amount": 1}}}}

    def test_remote_timeout_reserves_and_duplicate_cannot_retry(self):
        envelope = self.prepare_remote()
        with patch.object(remote_call, "__file__", str(self.root / "remote_call.py")), \
             patch("remote_call.ssl.create_default_context"), \
             patch("remote_call.urllib.request.build_opener") as opener, \
             patch("remote_call.socket.getaddrinfo"), \
             patch("sys.stdout", new_callable=io.StringIO):
            opener.return_value.open.side_effect = TimeoutError()
            with patch("sys.stdin", io.StringIO(json.dumps(envelope))):
                remote_call.main()
            with patch("sys.stdin", io.StringIO(json.dumps(envelope))):
                with self.assertRaisesRegex(RuntimeError, "Duplicate"):
                    remote_call.main()
            self.assertEqual(opener.return_value.open.call_count, 1)
        row = json.loads((self.root / "remote_responses.jsonl").read_text())
        self.assertEqual(row["delivery"], "uncertain")
        self.assertEqual(len((self.root / "remote_attempts.jsonl").read_text().splitlines()), 1)

    def test_remote_budget_stops_before_network(self):
        envelope = self.prepare_remote()
        (self.root / "remote_attempts.jsonl").write_text("\n".join(json.dumps({"request": {"id": str(i), "method": "tools/call"}}) for i in range(500)) + "\n")
        with patch.object(remote_call, "__file__", str(self.root / "remote_call.py")), patch("sys.stdin", io.StringIO(json.dumps(envelope))), patch("remote_call.urllib.request.build_opener") as opener:
            with self.assertRaisesRegex(RuntimeError, "limit"):
                remote_call.main()
            opener.assert_not_called()

    def test_captured_smoke_headers_and_receipts_are_compatible(self):
        root = Path(__file__).parent.parent / "gcp_mcp_smoke"
        clients = [json.loads(x) for x in (root / "client.jsonl").read_text().splitlines()]
        backend = [json.loads(x) for x in (root / "backend.jsonl").read_text().splitlines()]
        checked = 0
        for row in clients:
            if row["request"]["method"] != "tools/call":
                continue
            row["backend_matches"] = [r for r in backend if r["request"]["id"] == row["request"]["id"]]
            headers = row["headers"]
            result = classify(row, row["request"], headers["x-smoke-revision"], int(headers["x-smoke-limit"]), int(headers["x-smoke-expiry"]))
            self.assertIn(result["outcome"], ("admit", "refuse"))
            checked += 1
        self.assertEqual(checked, 14)


if __name__ == "__main__":
    unittest.main()
