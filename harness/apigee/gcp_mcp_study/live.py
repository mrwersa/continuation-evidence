"""Explicit live entry point. Requires a private, preflight-checked run manifest.

Run on the workstation. The VM has no Google credentials or service account.
This never provisions, deletes, retries a mutation or resumes a collection.
"""
import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from bundles import bundle
from runner import Guard, Journal, Runner, Stop


class Management:
    def __init__(self, journal):
        self.log = journal
        self.token = None
        self.token_time = 0

    def request(self, method, path, data=None, content_type="application/json"):
        if not path.startswith("organizations/your-gcp-project/") and path != "organizations/your-gcp-project":
            raise Stop("Out-of-scope management path")
        if not self.token or time.time() - self.token_time > 2700:
            self.token = subprocess.run(["gcloud", "auth", "print-access-token"], check=True, capture_output=True, text=True, timeout=45).stdout.strip()
            self.token_time = time.time()
        self.log.write("management_reserved", method=method, path=path,
                       body_sha256=hashlib.sha256(data).hexdigest() if data else None)
        request = urllib.request.Request("https://apigee.googleapis.com/v1/" + path, data=data, method=method,
                                         headers={"Authorization": "Bearer " + self.token, "Content-Type": content_type,
                                                  "x-goog-user-project": "your-gcp-project"})
        try:
            response = urllib.request.urlopen(request, timeout=60)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            payload = json.load(response)
            self.log.write("management_response", method=method, path=path, status=response.status, payload=payload)
            if response.status >= 400:
                raise Stop(f"Management HTTP {response.status}")
            return payload


class Adapter:
    base = "organizations/your-gcp-project"
    proxy = "mcp-lab-refund"

    def __init__(self, config, journal):
        self.config = config
        self.manager = Management(journal)
        self.log = journal

    def import_bundle(self, variant):
        data = bundle(variant, self.config["window_date"])
        if hashlib.sha256(data).hexdigest() != self.config["bundle_sha256"][variant]:
            raise Stop("Bundle differs from run manifest")
        response = self.manager.request("POST", self.base + f"/apis?action=import&name={self.proxy}", data, "application/octet-stream")
        return response["revision"]

    def promote(self, revision):
        return self.manager.request("POST", self.base + f"/environments/eval/apis/{self.proxy}/revisions/{revision}/deployments?override=true", b"{}")

    def deployment(self, revision):
        return self.manager.request("GET", self.base + f"/environments/eval/apis/{self.proxy}/revisions/{revision}/deployments")

    def request(self, key, request):
        command = ["gcloud", "compute", "ssh", "mcp-lab-client", "--project=your-gcp-project",
                   "--zone=europe-west2-a", "--tunnel-through-iap", "--quiet",
                   "--ssh-key-file=" + self.config["ssh_key_file"],
                   "--command=cd /tmp/mcp-study && python3 remote_call.py"]
        result = subprocess.run(command, input=json.dumps({"task": key, "request": request}), text=True,
                                capture_output=True, timeout=90)
        if result.returncode:
            self.log.write("ssh_transport_error", code=result.returncode, stderr=result.stderr[-3000:])
            raise Stop("Remote execution uncertain")
        return json.loads(result.stdout)


def validate_manifest(config, now):
    if config["project"] != "your-gcp-project" or config["billing_type"] != "EVALUATION":
        raise Stop("Project or evaluation gate")
    if config["subscription_type"] != "TRIAL":
        raise Stop("Trial gate")
    if config["vm_delete_epoch"] > config["provision_start_epoch"] + 8 * 3600:
        raise Stop("VM deletion exceeds deadline")
    if config["vm_delete_epoch"] <= now:
        raise Stop("VM expired")
    root = Path(__file__).parent
    freeze = json.loads((root / "FREEZE.json").read_text())
    if hashlib.sha256((root / "FREEZE.json").read_bytes()).hexdigest() != config["freeze_sha256"]:
        raise Stop("Design snapshot differs")
    for filename, digest in freeze["sha256"].items():
        if hashlib.sha256((root / filename).read_bytes()).hexdigest() != digest:
            raise Stop("Frozen file changed: " + filename)
    for filename, digest in config["runner_sha256"].items():
        if Path(filename).name != filename or hashlib.sha256((root / filename).read_bytes()).hexdigest() != digest:
            raise Stop("Runner changed")
    for name in ("runner.py", "live.py", "remote_call.py", "test_runner.py", "test_transport.py"):
        if name not in config["runner_sha256"]:
            raise Stop("Runner or test missing from manifest")
    if not config["offline_failure_tests_passed"]:
        raise Stop("Offline failure tests not recorded")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--authorised-live", action="store_true", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    config = json.loads(args.manifest.read_text())
    validate_manifest(config, time.time())
    guard = Guard(config["provision_start_epoch"], config["expiry_epoch"], config["prior_smoke_cost_bound_gbp"],
                  config["hourly_cost_bound_gbp"], config["fixed_cost_bound_gbp"])
    # This is intentionally create-only. Never restart an interrupted collection.
    journal = Journal(args.manifest.parent / "events.jsonl")
    try:
        journal.write("run_manifest", manifest=config)
        adapter = Adapter(config, journal)
        org = adapter.manager.request("GET", "organizations/your-gcp-project")
        if org.get("billingType") != "EVALUATION" or org.get("subscriptionType") != "TRIAL":
            raise Stop("Live evaluation billing check failed")
        succeeded = Runner(adapter, journal, guard).collect()
    finally:
        journal.close()
    raise SystemExit(0 if succeeded else 2)


if __name__ == "__main__":
    main()
