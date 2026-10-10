"""One allocation and execution, with export and cleanup on success or failure."""
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from freeze_repeat import check_freeze
from resources import ROOT, AUTH, allocate, cli, record
from setup_repeat import wait_runtime, create_vm, configure_access
from cleanup import cleanup

SOURCE = Path(__file__).resolve().parent


def stop_on_signal(signum, frame):
    raise KeyboardInterrupt("Supervisor interrupted")


def main():
    os.umask(0o077)
    check_freeze()
    if not AUTH.get("approved") or AUTH.get("project") != "your-gcp-project":
        raise RuntimeError("Explicit repeat authorisation missing")
    if not AUTH.get("cost_review_passed") or not AUTH.get("prior_resources_absent"):
        raise RuntimeError("Preflight gates missing")
    # No resource creation while waiting. The launch gate is checked again in allocate.
    not_before = AUTH["not_before_epoch"]
    while time.time() < not_before:
        time.sleep(min(15, not_before - time.time()))
    check_freeze()
    source_commit = AUTH["source_commit"]
    # Unrelated repository commits must not invalidate a checked frozen runner.
    # Verify the authorised commit exists, then check every repeat/dependency byte.
    subprocess.run(["git", "cat-file", "-e", source_commit + "^{commit}"],
                   cwd=SOURCE, capture_output=True, check=True)
    check_freeze()
    with (ROOT / "supervisor.started").open("x") as handle:
        handle.write(str(time.time()))
    signal.signal(signal.SIGTERM, stop_on_signal)
    process = None
    code = 2
    try:
        print("Starting one evaluation-only allocation", flush=True)
        allocate()
        org, instance = wait_runtime()
        print("Evaluation runtime ready, preparing scoped client", flush=True)
        create_vm()
        info = configure_access(org, instance)
        resources = json.loads((ROOT / "resources.json").read_text())
        manifest = {**resources, **info, "account": AUTH["account"],
            "execution_id": AUTH["execution_id"], "source_commit": source_commit,
            "freeze_sha256": hashlib.sha256((SOURCE / "FREEZE.json").read_bytes()).hexdigest(),
            "ssh_key_file": str(ROOT / "ssh_key"), "api_key_file": str(ROOT / "api.key"), "offline_failure_tests_passed": True,
            "cleanup_ready": True, "cost_review_passed": True, "prior_resources_absent": True,
            "new_cost_ceiling_gbp": 5, "cumulative_ceiling_gbp": 20}
        with (ROOT / "run_manifest.json").open("x") as handle:
            json.dump(manifest, handle, indent=2)
        remaining = min(resources["provision_start_epoch"] + 7 * 3600,
                        resources["vm_delete_epoch"] - 600) - time.time()
        if remaining < 4 * 3600:
            raise RuntimeError("Insufficient collection time after setup")
        print("Starting frozen 90-sequence collection", flush=True)
        with (ROOT / "runner_console.log").open("x") as output:
            process = subprocess.Popen(["python3", str(SOURCE / "live_repeat.py"),
                "--manifest", str(ROOT / "run_manifest.json"), "--authorised-live"],
                stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            code = process.wait(timeout=resources["vm_delete_epoch"] - time.time() - 600)
        record("supervisor.jsonl", {"kind": "runner_finished", "code": code})
    except BaseException as exc:
        record("supervisor.jsonl", {"kind": "interrupted", "error": type(exc).__name__, "reason": str(exc)[:300]})
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
    finally:
        if (ROOT / "resources.json").exists():
            print("Exporting evidence and removing scoped resources", flush=True)
            try:
                if (ROOT / "remote_source_check.txt").exists():
                    for filename in ("backend.jsonl", "remote_attempts.jsonl", "remote_transport.jsonl", "remote_responses.jsonl", "readiness.jsonl", "server.log"):
                        try:
                            cli(["compute", "scp", "mcp-lab-client:/tmp/mcp-study/" + filename,
                                 str(ROOT / filename), "--zone=europe-west2-a", "--tunnel-through-iap",
                                 "--ssh-key-file=" + str(ROOT / "ssh_key")])
                        except Exception as exc:
                            record("supervisor.jsonl", {"kind": "export_failed", "file": filename,
                                "error": type(exc).__name__})
                            code = 2
            finally:
                cleanup()
    return code


if __name__ == "__main__":
    sys.exit(main())
