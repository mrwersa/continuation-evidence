"""Offline setup/cleanup gates. No cloud commands are executed."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location("repeat_test_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="gcp-mcp-retry.", dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        auth = {"account": "researcher@example.invalid", "execution_id": "repeat-20261010-abc12345",
                "prior_deletion_reconfirmed": True}
        (self.path / "authorisation.json").write_text(json.dumps(auth))
        (self.path / "gbp_prices.json").write_text("[]")
        self.cost = {"prior_total_cost_bound_gbp": 5, "hourly_cost_bound_gbp": .1,
                     "fixed_cost_bound_gbp": 1}
        self.write_cost()
        with patch.dict(os.environ, {"MCP_REPEAT_SCRATCH": self.tmp.name}):
            self.resources = load("resources")
        self.cli = Mock(side_effect=lambda args, **kw: [{"name": "default"}]
                        if args == ["compute", "networks", "list"] else [])
        self.resources.cli = self.cli
        self.api = Mock(side_effect=lambda method, *a, **kw:
                        (403, {}) if method == "GET" else (200, {"name": "operation"}))
        self.resources.api = self.api
        self.date = Mock()
        self.date.now.return_value = datetime(2026, 10, 10, 0, 5, tzinfo=timezone.utc)

    def write_cost(self):
        (self.path / "cost_gate.json").write_text(json.dumps(self.cost))

    def allocate(self):
        with patch("freeze_repeat.check_freeze"), patch("contract_check.verify_contract", return_value={}), \
                patch.object(self.resources, "datetime", self.date), \
                patch.object(self.resources.shutil, "which", return_value="/test/gcloud"):
            self.resources.allocate()

    def test_only_one_allocation_can_be_attempted(self):
        self.allocate()
        with self.assertRaises(FileExistsError):
            self.allocate()
        self.assertEqual(sum(c.args[0] == "POST" for c in self.api.call_args_list), 1)

    def test_cost_rejected_before_any_cloud_call(self):
        for prior, hourly in [(19, .1), (0, .4), (float("nan"), .1)]:
            self.cost.update(prior_total_cost_bound_gbp=prior, hourly_cost_bound_gbp=hourly)
            self.write_cost()
            with self.assertRaises(RuntimeError):
                self.allocate()
        self.cli.assert_not_called()
        self.api.assert_not_called()

    def test_missing_cli_or_validator_stops_before_cloud_requests(self):
        with patch("freeze_repeat.check_freeze"), patch.object(self.resources, "datetime", self.date), \
                patch.object(self.resources.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "gcloud"):
                self.resources.allocate()
        with patch("freeze_repeat.check_freeze"), patch.object(self.resources, "datetime", self.date), \
                patch.object(self.resources.shutil, "which", return_value="/test/gcloud"), \
                patch("contract_check.verify_contract", side_effect=RuntimeError("validator failure")):
            with self.assertRaisesRegex(RuntimeError, "validator"):
                self.resources.allocate()
        self.cli.assert_not_called()
        self.api.assert_not_called()
        self.assertFalse((self.path / "allocation.started").exists())

    def test_late_window_rejected_before_any_cloud_call(self):
        self.date.now.return_value = datetime(2026, 10, 10, 23, 0, tzinfo=timezone.utc)
        with self.assertRaisesRegex(RuntimeError, "cutoff"):
            self.allocate()
        self.cli.assert_not_called()

    def test_existing_vm_never_becomes_cleanup_target(self):
        self.cli.return_value = [{"name": "mcp-lab-client"}]
        self.cli.side_effect = None
        with self.assertRaisesRegex(RuntimeError, "VM inventory"):
            self.allocate()
        self.assertFalse((self.path / "resources_owned.json").exists())
        with patch.dict(sys.modules, {"resources": self.resources}):
            cleanup = load("cleanup")
        self.cli.reset_mock()
        cleanup.cleanup()
        self.cli.assert_not_called()
        self.api.assert_not_called()

    def test_existing_organisation_stops_before_network_creation(self):
        self.api.side_effect = None
        self.api.return_value = (200, {"billingType": "EVALUATION"})
        with self.assertRaisesRegex(RuntimeError, "absence"):
            self.allocate()
        self.assertFalse((self.path / "resources_owned.json").exists())
        self.assertFalse(any("create" in c.args[0] for c in self.cli.call_args_list))

    def test_refused_allocation_is_not_retried(self):
        self.api.side_effect = lambda *a: (403, {})
        with self.assertRaisesRegex(RuntimeError, "refused"):
            self.allocate()
        self.assertEqual(sum(c.args[0] == "POST" for c in self.api.call_args_list), 1)
        self.assertEqual(json.loads((self.path / "allocation.json").read_text())["status"], 403)

    def test_cleanup_failure_does_not_remove_unverified_network(self):
        self.allocate()
        self.cli.reset_mock()
        self.api.side_effect = lambda *a: (403, {})
        with patch.dict(sys.modules, {"resources": self.resources}):
            cleanup = load("cleanup")
        with self.assertRaisesRegex(AssertionError, "absence unverified"):
            cleanup.cleanup()
        self.assertFalse(any("delete" in c.args[0] for c in self.cli.call_args_list))


if __name__ == "__main__":
    unittest.main()
