"""One-shot entry point. Requires a separately frozen repeat and private manifest."""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from repeat_runner import Adapter, Guard, Journal, ROOT, Runner, Stop, check_dependencies


def validate(config, now):
    check_dependencies()
    freeze_path = ROOT / "FREEZE.json"
    if not freeze_path.exists():
        raise Stop("Repeat is not frozen")
    freeze = json.loads(freeze_path.read_text())
    if freeze.get("status") != "prospective_repeat_ready_for_provisioning":
        raise Stop("Invalid freeze status")
    if hashlib.sha256(freeze_path.read_bytes()).hexdigest() != config["freeze_sha256"]:
        raise Stop("Repeat freeze mismatch")
    required = {"credentials.py", "repeat_runner.py", "live_repeat.py", "PROTOCOL.md",
                "dependencies.json", "test_credentials.py", "test_repeat_runner.py"}
    if not required <= freeze["sha256"].keys():
        raise Stop("Incomplete repeat freeze")
    for name, digest in freeze["sha256"].items():
        if Path(name).name != name or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise Stop("Changed frozen repeat source")
    if config["project"] != "your-gcp-project" or config["billing_type"] != "EVALUATION" or config["subscription_type"] != "TRIAL":
        raise Stop("Personal evaluation-only gate")
    if not config["offline_failure_tests_passed"] or not config["cleanup_ready"]:
        raise Stop("Test or cleanup gate")
    if not config["cost_review_passed"] or not config["prior_resources_absent"]:
        raise Stop("Cost or prior-resource gate")
    start = config["provision_start_epoch"]
    if config["vm_delete_epoch"] > start + 8 * 3600 or config["vm_delete_epoch"] <= now + 600:
        raise Stop("Invalid deletion or export headroom")
    if config["new_cost_ceiling_gbp"] != 5 or config["cumulative_ceiling_gbp"] != 20:
        raise Stop("Unauthorised financial ceiling")
    return Guard(start, config["expiry_epoch"], config["prior_total_cost_bound_gbp"],
                 config["hourly_cost_bound_gbp"], config["fixed_cost_bound_gbp"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--authorised-live", action="store_true", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    config = json.loads(args.manifest.read_text())
    guard = validate(config, time.time())
    journal = Journal(args.manifest.parent / "events.jsonl")
    succeeded = False
    try:
        journal.write("run_manifest", manifest=config)
        adapter = Adapter(config, journal)
        runner = Runner(adapter, journal, guard, config["execution_id"])
        org = adapter.manager.request("GET", "organizations/your-gcp-project")
        if org.get("billingType") != "EVALUATION" or org.get("subscriptionType") != "TRIAL":
            raise Stop("Live evaluation billing check failed")
        succeeded = runner.collect()
    except Exception as exc:
        journal.write("entrypoint_stopped", error=type(exc).__name__)
    finally:
        journal.close()
    raise SystemExit(0 if succeeded else 2)


if __name__ == "__main__":
    main()
