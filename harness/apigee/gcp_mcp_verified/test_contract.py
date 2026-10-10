"""Contract tests execute the actual JavaScript from the deployment bundle."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from contract_check import evaluate, verify_contract
from bundles import contents
from task_keys import namespaced
from repeat_runner import Adapter, Stop


class ContractTests(unittest.TestCase):
    def test_original_failure_and_corrected_key_in_actual_validator(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "validate.js"
            source.write_text(contents("baseline", "2026-10-10")["apiproxy/resources/jsc/validate.js"])
            request = {"jsonrpc": "2.0", "id": "r", "method": "tools/call",
                "params": {"name": "refund", "arguments": {"amount": 1}}}
            old = "repeat-20261010-l6mm1sag:study-diag-001"
            new = namespaced("repeat-20261010-abc12345", "study-diag-001")
            rows = evaluate(source, [{"task": key, "request": request} for key in (old, new)])
            self.assertFalse(rows[0]["valid"])
            self.assertEqual(rows[1], {"valid": True, "task": new, "amount": 1})

    def test_all_generated_keys_and_amounts_in_every_actual_bundle(self):
        result = verify_contract("repeat-20261010-abc12345", "2026-10-10")
        self.assertEqual(result["variants"], 6)
        self.assertEqual(result["unique_keys"], 202)
        self.assertEqual(result["checks"], 9696)
        self.assertLessEqual(result["maximum_key_length"], 80)

    def test_invalid_keys_rejected_before_remote_dispatch(self):
        adapter = object.__new__(Adapter)
        for key in ("bad:key", "", "x" * 81, "bad/key", "space key"):
            with patch("repeat_runner.subprocess.run") as remote:
                with self.assertRaises(Stop):
                    adapter.request(key, {})
                remote.assert_not_called()
            with self.assertRaises(ValueError):
                namespaced("repeat-20261010-abc12345", key)
        with self.assertRaises(ValueError):
            namespaced("repeat-20261010-abc12345", "a" * 70)

    def test_response_failure_keeps_http_reason(self):
        from integration import dispatch
        row = {"request_id": "r", "delivery": "response_received", "status": 400,
            "body": '{"error":"invalid_input"}', "backend_log_status": "missing"}
        diagnostic = Mock()
        with self.assertRaises(RuntimeError):
            dispatch([], {"request": {"id": "r"}}, diagnostic, [],
                Mock(return_value=Mock(returncode=0, stdout=json.dumps(row))))
        self.assertEqual(diagnostic.call_args.args[0]["status"], 400)
        self.assertIn("invalid_input", diagnostic.call_args.args[0]["body"])

    def test_actual_validator_input_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "validate.js"
            source.write_text(contents("baseline", "2026-10-10")["apiproxy/resources/jsc/validate.js"])
            pairs = [("a" * 80, 1, True), ("a" * 81, 1, False),
                ("under_score-hyphen", 1000, True), ("bad:key", 1, False),
                ("key", 0, False), ("key", 1001, False), ("key", 1.5, False),
                ("key", "1", False), ("key", True, False)]
            cases = [{"task": key, "request": {"method": "tools/call",
                "params": {"name": "refund", "arguments": {"amount": amount}}}}
                for key, amount, _ in pairs]
            self.assertEqual([row["valid"] for row in evaluate(source, cases)],
                [expected for _, _, expected in pairs])
