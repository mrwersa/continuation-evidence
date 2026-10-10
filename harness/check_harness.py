"""Check the released capture harnesses offline without running any of them."""

import ast
import hashlib
import json
from pathlib import Path
import re
import sys

HARNESS = Path(__file__).resolve().parent
ROOT = HARNESS.parent
OWN = {"README.md", "PROVENANCE.json", "check_harness.py", "test_harness.py"}
SAME_AS_ROOT = {
    "agentcore/continuation-protocol.json": "revision-validated-protocol.json",
    "agentcore/continuation-diagnostic-protocol.json": "revision-diagnostic-protocol.json",
    "managed-agents/continuation-protocol.json": "anthropic-cap-change-protocol.json",
}
# Project paths must use the release placeholder. "another-project" is a fixture in the original tests.
FORBIDDEN = re.compile(
    rb"AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|sk-ant-[A-Za-z0-9_-]{8,}|AIza[0-9A-Za-z_-]{30,}|ya29\.[0-9A-Za-z_-]{8,}"
    rb"|-----BEGIN [A-Z ]*PRIVATE KEY-----[A-Za-z0-9+/=\s]{16,}|arn:aws:[a-z0-9-]+:[a-z0-9-]*:[0-9]{12}"
    rb"|/home/[a-z]|(?:projects/|organizations/|--project=)(?!(?:your-gcp-project|another-project)\b)[a-z][a-z0-9-]{4,28}[a-z0-9]\b"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(harness=HARNESS, root=ROOT):
    errors = []
    listed = json.loads((harness / "PROVENANCE.json").read_text())["files"]
    paths = {entry["path"].removeprefix("harness/"): entry for entry in listed}
    present = {p.relative_to(harness).as_posix() for p in harness.rglob("*")
               if p.is_file() and "__pycache__" not in p.parts}
    for name in sorted(present - set(paths) - OWN):
        errors.append(f"unlisted file: {name}")
    for name, entry in sorted(paths.items()):
        path = harness / name
        if not path.is_file():
            errors.append(f"missing file: {name}")
        elif digest(path) != entry["released_sha256"]:
            errors.append(f"changed file: {name}")
    for name in [*SAME_AS_ROOT, *(n for n in paths if n.startswith("agentcore/") and n.endswith((".cedar", ".dogwood")))]:
        twin = root / SAME_AS_ROOT.get(name, Path(name).name)
        if (harness / name).is_file() and (not twin.is_file() or digest(harness / name) != digest(twin)):
            errors.append(f"differs from released evidence: {name}")
    schedule = json.loads((harness / "apigee/gcp_mcp_study/schedule.json").read_text())
    released = json.loads((root / "apigee_protocol.json").read_text())
    strip = lambda rows: [{k: v for k, v in row.items() if k != "accounting_key"} for row in rows]
    if schedule["seed"] != released["seed"] or strip(schedule["trials"]) != strip(released["schedule"]):
        errors.append("Apigee schedule differs from apigee_protocol.json")
    for name in sorted(present):
        path = harness / name
        if name not in OWN and FORBIDDEN.search(path.read_bytes()):
            errors.append(f"credential or identifier pattern: {name}")
        if path.suffix == ".py":
            try:
                ast.parse(path.read_text(), filename=name)
            except SyntaxError as exc:
                errors.append(f"syntax error: {name}: {exc}")
    return len(paths), errors


if __name__ == "__main__":
    count, errors = check()
    for error in errors:
        print("FAIL", error)
    if errors:
        sys.exit(1)
    print(f"PASS: {count} harness files match PROVENANCE.json and the released evidence. No harness code ran.")
