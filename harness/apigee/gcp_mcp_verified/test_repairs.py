"""Offline regression tests. All network and cloud clients are mocked."""
import importlib.util
import io
import json
import socket
import ssl
import sys
import tempfile
import types
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

import remote_call
from operation_url import operation_poll_url

ROOT = Path(__file__).resolve().parent


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "remote_config.json").write_text(json.dumps({
            "deadline": 200, "expiry": 300, "url": "https://example.invalid/mcp",
            "host": "example.invalid", "connect_ip": "127.0.0.1"}))
        (self.root / "api.key").write_text("test-secret")
        self.envelope = {"task": "test", "request": {"id": "r1", "method": "tools/call"}}
        self.opener = Mock()
        for p in (patch.object(remote_call.time, "time", return_value=100),
                  patch.object(remote_call.ssl, "create_default_context", return_value=Mock()),
                  patch.object(remote_call.urllib.request, "build_opener", return_value=self.opener)):
            p.start()
            self.addCleanup(p.stop)

    def execute(self):
        return remote_call.execute(self.root, self.envelope)

    def response(self, code=200):
        response = Mock(code=code, headers={"Content-Type": "application/json"})
        response.read.return_value = b'{"ok": true}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        self.opener.open.return_value = response

    def test_first_transport_failures_survive_missing_backend(self):
        failures = [TimeoutError("test-secret"), ConnectionRefusedError("test-secret"),
                    urllib.error.URLError(ssl.SSLCertVerificationError("test-secret"))]
        resolver = socket.getaddrinfo
        for i, error in enumerate(failures):
            self.envelope["request"]["id"] = str(i)
            self.opener.open.side_effect = error
            row = self.execute()
            self.assertEqual(row["delivery"], "uncertain")
            self.assertEqual(row["backend_log_status"], "missing")
            self.assertNotIn("test-secret", json.dumps(row))
            self.assertIs(socket.getaddrinfo, resolver)
        rows = (self.root / "remote_responses.jsonl").read_text().splitlines()
        self.assertEqual(len(rows), 3)
        self.assertEqual(json.loads(rows[-1])["cause_type"], "SSLCertVerificationError")
        self.assertEqual(self.opener.open.call_count, 3)  # one dispatch per request

    def test_local_tls_setup_failure_is_recorded_without_dispatch(self):
        with patch.object(remote_call.ssl, "create_default_context", side_effect=FileNotFoundError()):
            row = self.execute()
        self.assertEqual(row["error"], "FileNotFoundError")
        self.opener.open.assert_not_called()
        self.assertTrue((self.root / "remote_transport.jsonl").exists())

    def test_first_http_refusal_is_not_lost_or_called_verified(self):
        self.opener.open.side_effect = urllib.error.HTTPError(
            "https://example.invalid", 429, "quota", {}, io.BytesIO(b"refused"))
        row = self.execute()
        self.assertEqual(row["status"], 429)
        self.assertEqual(row["delivery"], "response_received")
        self.assertEqual(row["backend_log_status"], "missing")
        self.assertEqual(row["backend_matches"], [])

    def test_corrupt_backend_preserves_transport_result(self):
        self.response()
        (self.root / "backend.jsonl").write_text("broken json")
        row = self.execute()
        self.assertEqual(row["status"], 200)
        self.assertEqual(row["backend_log_status"], "unreadable")
        saved = json.loads((self.root / "remote_transport.jsonl").read_text())
        self.assertEqual(saved["status"], 200)

    def test_success_retains_matching_backend_evidence(self):
        self.response()
        match = {"request": {"id": "r1"}}
        (self.root / "backend.jsonl").write_text(json.dumps(match) + "\n")
        self.assertEqual(self.execute()["backend_matches"], [match])

    def test_duplicate_and_expired_calls_never_dispatch(self):
        self.response()
        self.execute()
        with self.assertRaisesRegex(RuntimeError, "Duplicate"):
            self.execute()
        self.envelope["request"]["id"] = "r2"
        with patch.object(remote_call.time, "time", return_value=201):
            with self.assertRaisesRegex(RuntimeError, "deadline"):
                self.execute()
        self.assertEqual(self.opener.open.call_count, 1)

    def test_frozen_client_reproduces_missing_log_failure(self):
        path = ROOT.parent / "gcp_mcp_study/remote_call.py"
        spec = importlib.util.spec_from_file_location("old_remote", path)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        old.__file__ = str(self.root / "remote_call.py")
        self.opener.open.side_effect = ConnectionRefusedError()
        with patch.object(old.sys, "stdin", io.StringIO(json.dumps(self.envelope))), \
                patch.object(old.os, "umask"), patch.object(old.socket, "getaddrinfo"):
            with self.assertRaises(FileNotFoundError):
                old.main()
        self.assertFalse((self.root / "remote_responses.jsonl").exists())


class CleanupTests(unittest.TestCase):
    def test_operation_url_alias_and_scope(self):
        suffix = "/compute/v1/projects/your-gcp-project/global/operations/op-123"
        expected = "https://compute.googleapis.com" + suffix
        for host in ("www.googleapis.com", "compute.googleapis.com"):
            self.assertEqual(operation_poll_url("https://" + host + suffix), expected)
        for url in ("http://www.googleapis.com" + suffix,
                    "https://www.googleapis.com.attacker.invalid" + suffix,
                    "https://user@www.googleapis.com" + suffix,
                    "https://www.googleapis.com:443" + suffix,
                    "https://www.googleapis.com" + suffix + "?alt=json",
                    expected.replace("your-gcp-project", "another-project"),
                    expected + "/../instances", expected + "%2fsecret"):
            with self.assertRaises(ValueError):
                operation_poll_url(url)

    def test_key_removal_polls_alias_and_preserves_other_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ssh_key.pub").write_text("ssh-rsa STUDY test")
            initial = {"commonInstanceMetadata": {"fingerprint": "fp", "items": [
                {"key": "ssh-keys", "value": "user:ssh-rsa STUDY\nuser:ssh-rsa OTHER"},
                {"key": "unrelated", "value": "retain"}]}}
            final = {"commonInstanceMetadata": {"items": [
                {"key": "ssh-keys", "value": "user:ssh-rsa OTHER"}]}}
            resources = types.ModuleType("resources")
            resources.ROOT = root
            resources.cli = Mock(side_effect=[initial, final])
            resources.api = Mock(side_effect=[(200, {"status": "RUNNING", "selfLink":
                "https://www.googleapis.com/compute/v1/projects/your-gcp-project/global/operations/op-1"}),
                (200, {"status": "DONE"})])
            with patch.dict(sys.modules, {"resources": resources}):
                spec = importlib.util.spec_from_file_location("candidate_cleanup", ROOT / "cleanup.py")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            with patch.object(module.time, "sleep"):
                module.remove_study_key()
            body = resources.api.call_args_list[0].args[2]
            self.assertEqual(body["items"][0]["value"], "user:ssh-rsa OTHER")
            self.assertEqual(body["items"][1], {"key": "unrelated", "value": "retain"})
            self.assertEqual(resources.api.call_args_list[1].args[1],
                "https://compute.googleapis.com/compute/v1/projects/your-gcp-project/global/operations/op-1")
            self.assertTrue(json.loads((root / "ssh_key_removed.json").read_text())["verified_absent"])


if __name__ == "__main__":
    unittest.main()
