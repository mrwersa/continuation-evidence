"""Mutation tests for the offline harness integrity check."""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_harness import HARNESS, ROOT, check


class HarnessCheckTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ["revision-validated-protocol.json", "revision-diagnostic-protocol.json",
                     "anthropic-cap-change-protocol.json", "apigee_protocol.json",
                     *(p.name for p in ROOT.glob("*.cedar")), *(p.name for p in ROOT.glob("*.dogwood"))]:
            shutil.copy2(ROOT / name, self.root / name)
        self.harness = self.root / "harness"
        shutil.copytree(HARNESS, self.harness, ignore=shutil.ignore_patterns("__pycache__"))

    def tearDown(self):
        self.temp.cleanup()

    def errors(self):
        return check(self.harness, self.root)[1]

    def test_released_harness_passes(self):
        self.assertEqual(self.errors(), [])

    def test_changed_file_fails(self):
        path = self.harness / "agentcore/capture_continuation_live.py"
        path.write_text(path.read_text() + "\n")
        self.assertIn("changed file: agentcore/capture_continuation_live.py", self.errors())

    def test_unlisted_file_fails(self):
        (self.harness / "apigee/extra.py").write_text("pass\n")
        self.assertIn("unlisted file: apigee/extra.py", self.errors())

    def test_protocol_must_match_released_evidence(self):
        path = self.root / "revision-validated-protocol.json"
        path.write_text(path.read_text().replace("1000", "2000", 1))
        self.assertIn("differs from released evidence: agentcore/continuation-protocol.json", self.errors())

    def test_apigee_schedule_must_match_released_protocol(self):
        path = self.root / "apigee_protocol.json"
        path.write_text(path.read_text().replace('"no_update"', '"renamed_arm"', 1))
        self.assertIn("Apigee schedule differs from apigee_protocol.json", self.errors())

    def test_project_identifier_is_rejected(self):
        (self.harness / "apigee/extra.json").write_text('{"url": "organizations/someone-elses-org/apis"}\n')
        self.assertIn("credential or identifier pattern: apigee/extra.json", self.errors())

    def test_access_key_is_rejected(self):
        (self.harness / "apigee/extra.json").write_text('{"key": "AKIA' + "A" * 16 + '"}\n')
        self.assertIn("credential or identifier pattern: apigee/extra.json", self.errors())


if __name__ == "__main__":
    unittest.main()
