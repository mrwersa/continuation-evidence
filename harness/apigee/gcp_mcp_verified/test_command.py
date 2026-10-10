"""Use the actual candidate wrapper and reproduce the captured gcloud suffix."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent
sys.path.append(str(ROOT))
from gcloud_command import command


class CommandTests(unittest.TestCase):
    def test_resource_reads_keep_json_and_remote_commands_do_not(self):
        for operation in ("ssh", "scp"):
            args = ["compute", operation, "mcp-lab-client"]
            self.assertNotIn("--format=json", command(args, "test@example.invalid"))
            with self.assertRaises(ValueError):
                command([*args, "--format=json"], "test@example.invalid")
        self.assertIn("--format=json", command(["compute", "instances", "list"], "test@example.invalid"))

    def test_readiness_output_survives_actual_wrapper(self):
        with tempfile.TemporaryDirectory(prefix="gcp-mcp-retry.", dir="/tmp") as directory:
            root = Path(directory)
            (root / "authorisation.json").write_text('{"account":"test@example.invalid"}')
            spec = importlib.util.spec_from_file_location("candidate_resources", ROOT / "resources.py")
            module = importlib.util.module_from_spec(spec)
            with patch.dict(os.environ, {"MCP_REPEAT_SCRATCH": directory}):
                spec.loader.exec_module(module)
            captured = '{"ready":true,"backend_listening":true,"tls_version":"TLSv1.3"}\n'
            def fake_run(args, **kwargs):
                # Reproduce the real CLI behaviour that failed the previous setup.
                suffix = "[]\n" if "--format=json" in args else ""
                return Mock(returncode=0, stdout=captured + suffix, stderr="")
            with patch.object(module.subprocess, "run", side_effect=fake_run) as run:
                output = module.cli(["compute", "ssh", "mcp-lab-client", "--command=python3 readiness.py"])
            self.assertTrue(json.loads(output)["ready"])
            run.assert_called_once()
            with self.assertRaises(json.JSONDecodeError):
                json.loads(captured + "[]\n")

    def test_resource_json_still_parsed_by_actual_wrapper(self):
        with tempfile.TemporaryDirectory(prefix="gcp-mcp-retry.", dir="/tmp") as directory:
            root = Path(directory)
            (root / "authorisation.json").write_text('{"account":"test@example.invalid"}')
            spec = importlib.util.spec_from_file_location("candidate_resources2", ROOT / "resources.py")
            module = importlib.util.module_from_spec(spec)
            with patch.dict(os.environ, {"MCP_REPEAT_SCRATCH": directory}):
                spec.loader.exec_module(module)
            with patch.object(module.subprocess, "run", return_value=Mock(
                    returncode=0, stdout='[{"name":"default"}]', stderr="")) as run:
                self.assertEqual(module.cli(["compute", "networks", "list"]), [{"name": "default"}])
                self.assertIn("--format=json", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
