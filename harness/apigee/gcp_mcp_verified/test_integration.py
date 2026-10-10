import hashlib
import json
import ssl
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import integration
import readiness


class IntegrationTests(unittest.TestCase):
    def test_readiness_checks_tls_without_http(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "remote_config.json").write_text(json.dumps({
                "expiry": 200, "deadline": 200, "url": "https://runtime.invalid/mcp",
                "connect_ip": "10.1.2.3"}))
            context = MagicMock()
            context.wrap_socket.return_value.__enter__.return_value.version.return_value = "TLSv1.3"
            with patch.object(readiness.time, "time", return_value=100), \
                    patch.object(readiness.socket, "create_connection", return_value=MagicMock()) as connect, \
                    patch.object(readiness.ssl, "create_default_context", return_value=context) as tls:
                row = readiness.check(root)
                self.assertTrue(row["ready"])
                self.assertEqual(row["tool_calls"], 0)
                self.assertEqual(connect.call_count, 2)
                self.assertEqual(connect.call_args_list[0].args[0], ("127.0.0.1", 8080))
                tls.assert_called_once_with(cafile=str(root / "ca.pem"))
                self.assertEqual(context.wrap_socket.call_args.kwargs["server_hostname"], "runtime.invalid")
                context.wrap_socket.side_effect = ssl.SSLCertVerificationError("secret")
                self.assertFalse(readiness.check(root)["ready"])
            saved = (root / "readiness.jsonl").read_text()
            self.assertNotIn("secret", saved)
            self.assertEqual(len(saved.splitlines()), 2)

    def test_deadline_prevents_readiness_connections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "remote_config.json").write_text('{"expiry": 0, "deadline": 0}')
            with patch.object(readiness.socket, "create_connection") as connect:
                self.assertFalse(readiness.check(root)["ready"])
                connect.assert_not_called()

    def test_dispatch_failure_redacts_and_never_retries(self):
        run = Mock(return_value=Mock(returncode=1,
            stderr='traceback secret-value Bearer token-abc access_token="token-def"', stdout=""))
        log = Mock()
        with self.assertRaisesRegex(RuntimeError, "no replay"):
            integration.dispatch(["mock"], {"request": {"id": "r"}}, log, ["secret-value"], run)
        run.assert_called_once()
        data = json.dumps(log.call_args.args[0])
        for secret in ("secret-value", "token-abc", "token-def"):
            self.assertNotIn(secret, data)
        self.assertIn("traceback", data)

    def test_timeout_retains_diagnostics_without_retry(self):
        run = Mock(side_effect=subprocess.TimeoutExpired("mock", 90, stderr=b"Bearer sensitive"))
        log = Mock()
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            integration.dispatch(["mock"], {}, log, [], run)
        run.assert_called_once()
        self.assertNotIn("sensitive", json.dumps(log.call_args.args[0]))

    def test_missing_backend_and_uncertain_delivery_cannot_pass(self):
        row = {"request_id": "r", "delivery": "response_received", "backend_log_status": "missing",
               "backend_matches": [], "status": 429}
        run = Mock(return_value=Mock(returncode=0, stdout=json.dumps(row)))
        with self.assertRaisesRegex(RuntimeError, "Backend evidence"):
            integration.dispatch(["mock"], {"request": {"id": "r"}}, Mock(), [], run)
        row.update(backend_log_status="read", delivery="uncertain")
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            integration.validate_response(row, "r")

    def test_export_failures_do_not_skip_transport_or_cleanup(self):
        order = []
        def export(name):
            order.append(name)
            if name == "backend.jsonl":
                raise FileNotFoundError()
        result = integration.export_then_cleanup(export, lambda: order.append("cleanup"), Mock())
        self.assertEqual(order, [*integration.EXPORTS, "cleanup"])
        self.assertEqual(result["backend.jsonl"], "missing_or_failed")
        self.assertEqual(result["remote_transport.jsonl"], "exported")

    def test_installs_repaired_files_and_verifies_before_readiness(self):
        hashes = "\n".join(hashlib.sha256((integration.HERE / n).read_bytes()).hexdigest() + "  " + n
                           for n in ("remote_call.py", "readiness.py"))
        cli = Mock(side_effect=["", hashes, '{"ready":true}'])
        integration.install_and_check(cli, [])
        self.assertIn(str(integration.HERE / "remote_call.py"), cli.call_args_list[0].args[0])
        cli = Mock(side_effect=["", "wrong"])
        with self.assertRaisesRegex(RuntimeError, "mismatch"):
            integration.install_and_check(cli, [])
        self.assertEqual(cli.call_count, 2)

    def test_transport_audit_detects_missing_duplicate_and_changed_records(self):
        transport = {"request_id": "r", "delivery": "response_received", "status": 200}
        response = {**transport, "backend_log_status": "read", "backend_matches": []}
        integration.audit_transport([response], [transport])
        for rows in ([], [transport, transport], [{**transport, "status": 429}]):
            with self.assertRaises(RuntimeError):
                integration.audit_transport([response], rows)


if __name__ == "__main__":
    unittest.main()
