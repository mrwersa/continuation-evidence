import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location("receipt_server", ROOT / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class FixtureTests(unittest.TestCase):
    def test_only_limit_changes_between_bundles(self):
        with zipfile.ZipFile(ROOT / "proxy-1000.zip") as first, zipfile.ZipFile(ROOT / "proxy-700.zip") as second:
            self.assertEqual(first.namelist(), second.namelist())
            changed = [name for name in first.namelist() if first.read(name) != second.read(name)]
            self.assertEqual(changed, ["apiproxy/policies/RefundQuota.xml"])
            self.assertEqual(first.read(changed[0]).replace(b'count="1000"', b'count="700"'), second.read(changed[0]))

    def test_quota_is_native_and_synchronous(self):
        with zipfile.ZipFile(ROOT / "proxy-1000.zip") as archive:
            quota = ET.fromstring(archive.read("apiproxy/policies/RefundQuota.xml"))
            self.assertEqual(quota.tag, "Quota")
            self.assertEqual(quota.findtext("Distributed"), "true")
            self.assertEqual(quota.findtext("Synchronous"), "true")
            self.assertEqual(quota.find("Identifier").get("ref"), "smoke.task")
            self.assertEqual(quota.find("MessageWeight").get("ref"), "smoke.amount")

    def test_backend_does_not_enforce_quota(self):
        with tempfile.TemporaryDirectory(prefix="mcp-local-fixture-") as tmp:
            server.LOG = Path(tmp) / "backend.jsonl"
            http = server.HTTPServer(("127.0.0.1", 0), server.Handler)
            worker = threading.Thread(target=http.serve_forever, daemon=True)
            worker.start()
            try:
                for index in (1, 2):
                    body = {"jsonrpc": "2.0", "id": index, "method": "tools/call", "params": {"name": "refund", "arguments": {"amount": 600}}}
                    req = urllib.request.Request(f"http://127.0.0.1:{http.server_port}/mcp", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req) as response:
                        payload = json.load(response)
                    self.assertFalse(payload["result"]["isError"])
                    receipt = json.loads(payload["result"]["content"][0]["text"])
                    self.assertEqual(receipt["amount"], 600)
                    self.assertEqual(receipt["effect"], "none")
                self.assertEqual(len(server.LOG.read_text().splitlines()), 2)
            finally:
                http.shutdown()
                http.server_close()
                worker.join()


if __name__ == "__main__":
    unittest.main()
