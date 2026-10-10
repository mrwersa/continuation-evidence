"""Real local HTTP/TLS rehearsal. Apigee quota/deployment behaviour is modelled.

No Google API, model service, provider traffic or financial effect is used.
The bundle JavaScript, remote client and receipt-server handler are executed.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import shutil
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from repeat_runner import Adapter, Guard, Journal, Runner, ORIGINAL
from contract_check import evaluate, verify_contract
from bundles import bundle, VARIANTS
from audit_repeat import audit_repeat
from integration import audit_transport

HERE = Path(__file__).resolve().parent
REAL_RUN = subprocess.run


class Clock:
    def __init__(self, now):
        self.now = now
    def __call__(self):
        return self.now
    def sleep(self, duration):
        self.now += duration


class ModelManagement:
    """Only the external management API and counter are substituted."""
    def __init__(self, state, root):
        self.state, self.root, self.revisions = state, root, {}
        self.promotions = 0
    def request(self, method, path, data=None, content_type="application/json"):
        if method == "POST" and "action=import" in path:
            archive = zipfile.ZipFile(io.BytesIO(data))
            quota_name = next(n for n in archive.namelist() if n.endswith("Quota.xml") or n.endswith("QuotaRenamed.xml"))
            quota = ET.fromstring(archive.read(quota_name))
            revision = str(len(self.revisions) + 1)
            self.revisions[revision] = {"revision": revision, "name": quota.attrib["name"],
                "limit": int(quota.find("Allow").attrib["count"]),
                "javascript": archive.read("apiproxy/resources/jsc/validate.js").decode()}
            return {"revision": revision}
        revision = path.split("/revisions/")[1].split("/")[0]
        if method == "POST":
            self.promotions += 1
            self.state.update(self.revisions[revision])
            (self.root / "validate.js").write_text(self.state["javascript"])
            return {}
        return {"revision": revision, "state": "READY"}


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def rehearse(root):
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    now = int(time.time())
    date = datetime.fromtimestamp(now, timezone.utc)
    expiry = int((date + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    if expiry - now < 8 * 3600:
        # Local model only. Never adjust the window of a real study.
        expiry += 86400
    execution = "repeat-20261010-manual01"
    contract = verify_contract(execution, date.date().isoformat())
    certificate, key = root / "ca.pem", root / "tls.key"
    REAL_RUN(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-keyout", str(key), "-out", str(certificate), "-subj", "/CN=runtime.invalid",
        "-addext", "subjectAltName=DNS:runtime.invalid"], check=True, capture_output=True)
    client = root / "client"
    client.mkdir()
    shutil.copyfile(HERE / "remote_call.py", client / "remote_call.py")
    shutil.copyfile(certificate, client / "ca.pem")
    (client / "api.key").write_text("local-test-only")
    (client / "backend.jsonl").touch(exist_ok=False)
    spec = importlib.util.spec_from_file_location("actual_receipt_server", ORIGINAL.parent / "gcp_mcp_smoke/server.py")
    backend_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backend_module)
    backend_module.LOG = client / "backend.jsonl"
    backend = HTTPServer(("127.0.0.1", 0), backend_module.Handler)
    state = {"counts": {}, "expiry": expiry * 1000}
    manager = ModelManagement(state, root)
    request_log = []

    class Gateway(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            task = self.headers.get("x-task-id")
            request_log.append({"task": task, "request": request})
            headers = {"x-smoke-revision": state["revision"]}
            if self.headers.get("x-api-key") != "local-test-only":
                raise RuntimeError("Unexpected local credential")
            status, body = 200, None
            if request["method"] == "tools/call":
                checked = evaluate(root / "validate.js", [{"task": task, "request": request}])[0]
                if not checked["valid"]:
                    status, body = 400, {"error": "invalid_input"}
                else:
                    account = (state["name"], checked["task"])
                    used = state["counts"].get(account, 0)
                    if used + checked["amount"] > state["limit"]:
                        status, body = 500, {"fault": {"detail": {"errorcode": "policies.ratelimit.QuotaViolation"}}}
                    else:
                        used += checked["amount"]
                        state["counts"][account] = used
                    headers.update({"x-smoke-limit": str(state["limit"]), "x-smoke-used": str(used),
                        "x-smoke-available": str(state["limit"] - used), "x-smoke-expiry": str(state["expiry"])})
            if body is None:
                forwarded = urllib.request.Request(f"http://127.0.0.1:{backend.server_port}/mcp",
                    data=json.dumps(request).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(forwarded, timeout=10) as response:
                    body = json.load(response)
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(encoded)

    gateway = HTTPServer(("127.0.0.1", 0), Gateway)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    gateway.socket = context.wrap_socket(gateway.socket, server_side=True)
    for server in (backend, gateway):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    config = {"url": f"https://runtime.invalid:{gateway.server_port}/mcp", "host": "runtime.invalid",
        "connect_ip": "127.0.0.1", "deadline": now + 8 * 3600, "expiry": expiry}
    (client / "remote_config.json").write_text(json.dumps(config))
    log = Journal(root / "events.jsonl")
    adapter = object.__new__(Adapter)
    adapter.log, adapter.manager = log, manager
    adapter.config = {"account": "offline@example.invalid", "ssh_key_file": "local-only",
        "api_key_file": str(client / "api.key"), "window_date": date.date().isoformat(),
        "bundle_sha256": {v: hashlib.sha256(bundle(v, date.date().isoformat())).hexdigest() for v in VARIANTS}}

    def dispatch_local(command, **kwargs):
        assert command[:3] == ["gcloud", "compute", "ssh"]
        assert "--format=json" not in command and "--tunnel-through-iap" in command
        return REAL_RUN([sys.executable, str(client / "remote_call.py")], **kwargs)

    try:
        # Reproduce the captured failure over real TLS using the actual validator.
        revision = adapter.import_bundle("baseline")
        adapter.promote(revision)
        bad = root / "bad-client"
        bad.mkdir()
        for name in ("remote_call.py", "ca.pem", "api.key", "remote_config.json"):
            shutil.copyfile(client / name, bad / name)
        request = {"jsonrpc": "2.0", "id": "original-failure", "method": "tools/call",
            "params": {"name": "refund", "arguments": {"amount": 1}}}
        result = REAL_RUN([sys.executable, str(bad / "remote_call.py")],
            input=json.dumps({"task": "repeat-20261010-l6mm1sag:study-diag-001", "request": request}),
            capture_output=True, text=True, check=True, timeout=30)
        rejected = json.loads(result.stdout)
        assert rejected["status"] == 400 and json.loads(rejected["body"])["error"] == "invalid_input"
        assert rejected["backend_log_status"] == "missing" and not rejected["backend_matches"]
        before = len(request_log)
        duplicate = REAL_RUN([sys.executable, str(bad / "remote_call.py")],
            input=json.dumps({"task": "repeat-20261010-l6mm1sag:study-diag-001", "request": request}),
            capture_output=True, text=True, timeout=30)
        assert duplicate.returncode != 0 and "Duplicate request identity" in duplicate.stderr
        assert len(request_log) == before
        expired_config = {**config, "deadline": 0}
        (bad / "remote_config.json").write_text(json.dumps(expired_config))
        expired = REAL_RUN([sys.executable, str(bad / "remote_call.py")],
            input=json.dumps({"task": "valid-key", "request": {**request, "id": "expired-request"}}),
            capture_output=True, text=True, timeout=30)
        assert expired.returncode != 0 and "Remote deadline" in expired.stderr
        assert len(request_log) == before
        clock = Clock(now)
        guard = Guard(now, expiry, 11, .1, 1, clock)
        runner = Runner(adapter, log, guard, execution, clock.sleep)
        initial_promotions = manager.promotions
        with patch("repeat_runner.subprocess.run", side_effect=dispatch_local):
            assert runner.collect(), "Local full schedule stopped"
        log.close()
        events, receipts = read(root / "events.jsonl"), read(client / "backend.jsonl")
        attempts, responses = read(client / "remote_attempts.jsonl"), read(client / "remote_responses.jsonl")
        transport = read(client / "remote_transport.jsonl")
        audit_transport(responses, transport)
        summary = audit_repeat(events, receipts, attempts, responses, execution)
        assert len(summary["sequences"]) == 90 and all(t["status"] == "complete" for t in summary["sequences"])
        assert guard.calls == 365 and manager.promotions - initial_promotions == 110
        refusals = [r for r in responses if r["status"] != 200]
        assert all(not r["backend_matches"] for r in refusals)
        report = {"status": "PASS", "environment": "local_rehearsal_not_provider_evidence",
            "original_invalid_input_reproduced": True, "contract": contract,
            "sequences": 90, "tool_calls": guard.calls, "promotions": 110,
            "real_tls_responses": len(responses), "backend_receipts": len(receipts),
            "refused_requests": len(refusals), "quota_and_management": "modelled",
            "provider_calls": 0, "real_request_and_response_bodies_verified": True,
            "duplicate_and_expired_requests_blocked_before_http": True,
            "clock": "virtual deployment/control waits, real HTTP/TLS"}
        (root / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        return report
    finally:
        if not log.handle.closed:
            log.close()
        for server in (gateway, backend):
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(rehearse(args.output), indent=2))
