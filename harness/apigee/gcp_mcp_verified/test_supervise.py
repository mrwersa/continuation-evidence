"""Failure-path checks without credentials, cloud resources or network access."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        auth = {"approved": True, "project": "your-gcp-project",
                "cost_review_passed": True, "prior_resources_absent": True,
                "not_before_epoch": 0, "source_commit": "abc",
                "account": "test@example.invalid", "execution_id": "repeat-20261010-12345678"}
        self.resources = types.ModuleType("resources")
        self.resources.ROOT, self.resources.AUTH = self.root, auth
        for name in ("allocate", "cli", "record"):
            setattr(self.resources, name, Mock())
        self.setup = types.ModuleType("setup_repeat")
        self.setup.wait_runtime = Mock(return_value=({}, {}))
        self.setup.create_vm = Mock()
        self.setup.configure_access = Mock(return_value={})
        self.cleanup = types.ModuleType("cleanup")
        self.cleanup.cleanup = Mock()
        freeze = types.ModuleType("freeze_repeat")
        freeze.check_freeze = Mock()
        self.modules = patch.dict(sys.modules, {"resources": self.resources,
            "setup_repeat": self.setup, "cleanup": self.cleanup, "freeze_repeat": freeze})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        spec = importlib.util.spec_from_file_location("tested_supervise", Path(__file__).with_name("supervise.py"))
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.module.SOURCE = self.root
        (self.root / "FREEZE.json").write_text("{}")
        self.patches = [patch.object(self.module.signal, "signal"),
                        patch.object(self.module.subprocess, "run"),
                        patch.object(self.module.time, "time", return_value=1000),
                        patch.object(self.module.os, "umask")]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def allocated(self):
        (self.root / "resources.json").write_text(json.dumps({
            "provision_start_epoch": 1000, "vm_delete_epoch": 1000 + 8 * 3600}))

    def test_setup_failure_cleans_owned_resources(self):
        self.resources.allocate.side_effect = self.allocated
        self.setup.wait_runtime.side_effect = RuntimeError("setup failed")
        self.assertEqual(self.module.main(), 2)
        self.cleanup.cleanup.assert_called_once()
        self.resources.cli.assert_not_called()

    def test_every_export_failure_still_cleans(self):
        self.resources.allocate.side_effect = self.allocated
        (self.root / "remote_source_check.txt").write_text("verified")
        self.setup.configure_access.side_effect = RuntimeError("access failed")
        self.resources.cli.side_effect = RuntimeError("export failed")
        self.assertEqual(self.module.main(), 2)
        self.assertEqual(self.resources.cli.call_count, 6)
        self.cleanup.cleanup.assert_called_once()

    def test_preflight_failure_never_allocates_or_cleans(self):
        self.resources.AUTH["approved"] = False
        with self.assertRaises(RuntimeError):
            self.module.main()
        self.resources.allocate.assert_not_called()
        self.cleanup.cleanup.assert_not_called()

    def test_timeout_terminates_runner_before_cleanup(self):
        self.resources.allocate.side_effect = self.allocated
        process = Mock(pid=123)
        process.wait.side_effect = [subprocess.TimeoutExpired("runner", 1), 0]
        process.poll.return_value = None
        with patch.object(self.module.subprocess, "Popen", return_value=process), \
                patch.object(self.module.os, "killpg") as kill:
            self.assertEqual(self.module.main(), 2)
            kill.assert_called_once_with(123, self.module.signal.SIGTERM)
        self.cleanup.cleanup.assert_called_once()

    def test_success_exports_then_cleans(self):
        self.resources.allocate.side_effect = self.allocated
        (self.root / "remote_source_check.txt").write_text("verified")
        process = Mock()
        process.wait.return_value = 0
        order = []
        self.resources.cli.side_effect = lambda *a, **k: order.append("export")
        self.cleanup.cleanup.side_effect = lambda: order.append("cleanup")
        with patch.object(self.module.subprocess, "Popen", return_value=process):
            self.assertEqual(self.module.main(), 0)
        self.assertEqual(order, ["export"] * 6 + ["cleanup"])


if __name__ == "__main__":
    unittest.main()
