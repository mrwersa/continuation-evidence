"""Check or create a prospective source freeze after the offline suite passes."""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources():
    return sorted([*ROOT.glob("*.py"), *ROOT.glob("*.js"), ROOT / "PROTOCOL.md", ROOT / "dependencies.json"])


def check_freeze():
    from repeat_runner import check_dependencies
    check_dependencies()
    path = ROOT / "FREEZE.json"
    if not path.exists():
        raise RuntimeError("Repeat not frozen")
    freeze = json.loads(path.read_text())
    if freeze["status"] != "prospective_repeat_ready_for_provisioning":
        raise RuntimeError("Invalid freeze status")
    if set(freeze["sha256"]) != {p.name for p in sources()}:
        raise RuntimeError("Repeat source inventory changed")
    for name, expected in freeze["sha256"].items():
        if Path(name).name != name or digest(ROOT / name) != expected:
            raise RuntimeError("Changed frozen repeat file: " + name)
    if digest(ROOT / "offline_tests.json") != freeze["offline_tests_sha256"]:
        raise RuntimeError("Offline test record changed")
    return freeze


def freeze():
    if (ROOT / "FREEZE.json").exists():
        raise RuntimeError("Freeze already exists. Do not replace silently.")
    results = []
    before = {p.name: digest(p) for p in sources()}
    for directory in (ROOT, ROOT.parent / "gcp_mcp_study"):
        command = ["python3", "-m", "unittest", "discover", "-s", str(directory), "-v"]
        run = subprocess.run(command, capture_output=True, text=True, timeout=180)
        results.append({"command": command, "exit_code": run.returncode, "output": run.stdout + run.stderr})
        if run.returncode:
            print(run.stdout + run.stderr)
            raise RuntimeError("Offline tests failed")
    if before != {p.name: digest(p) for p in sources()}:
        raise RuntimeError("Source changed during tests")
    with (ROOT / "offline_tests.json").open("x") as handle:
        json.dump(results, handle, indent=2)
    value = {"status": "prospective_repeat_ready_for_provisioning",
             "utc": datetime.now(timezone.utc).isoformat(), "sha256": before,
             "offline_tests_sha256": digest(ROOT / "offline_tests.json")}
    with (ROOT / "FREEZE.json").open("x") as handle:
        json.dump(value, handle, indent=2)
    check_freeze()
    print("PASS: prospective repeat sources frozen after offline tests. No cloud traffic.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        freeze()
    else:
        check_freeze()
        print("PASS: repeat freeze and original dependency hashes match.")
