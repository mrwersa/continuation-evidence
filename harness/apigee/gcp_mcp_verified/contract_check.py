"""Pre-allocation checks against every bundle's actual JavaScript validator."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from repeat_runner import check_dependencies
from bundles import contents, VARIANTS
from design import schedule
from task_keys import namespaced

HERE = Path(__file__).resolve().parent
REAL_RUN = subprocess.run


def evaluate(source, cases):
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node is required for the deployed-validator gate")
    result = REAL_RUN([node, str(HERE / "validate_fixture.js")],
        input=json.dumps({"source": str(source), "cases": cases}),
        text=True, capture_output=True, check=True, timeout=30)
    return json.loads(result.stdout)


def verify_contract(execution, window_date):
    check_dependencies()
    keys = {"study-calibration", "study-equality"}
    keys.update(f"study-diag-{i:03d}" for i in range(1, 111))
    keys.update(t["accounting_key"] for t in schedule())
    generated = [namespaced(execution, k) for k in sorted(keys)]
    if len(set(generated)) != len(keys):
        raise RuntimeError("Task-key collision")
    amounts = (1, 50, 100, 200, 300, 600, 800, 1000)
    cases = [{"task": key, "request": {"jsonrpc": "2.0", "id": "offline",
        "method": "tools/call", "params": {"name": "refund", "arguments": {"amount": amount}}}}
        for key in generated for amount in amounts]
    with tempfile.TemporaryDirectory(prefix="mcp-contract-") as directory:
        source = Path(directory) / "validate.js"
        for variant in VARIANTS:
            source.write_text(contents(variant, window_date)["apiproxy/resources/jsc/validate.js"])
            rows = evaluate(source, cases)
            if len(rows) != len(cases) or any(not row["valid"] or row["task"] != case["task"]
                    or row["amount"] != case["request"]["params"]["arguments"]["amount"]
                    for row, case in zip(rows, cases)):
                raise RuntimeError("Generated input rejected by actual bundle validator: " + variant)
    return {"variants": len(VARIANTS), "unique_keys": len(keys),
        "checks": len(VARIANTS) * len(cases), "maximum_key_length": max(map(len, generated))}
