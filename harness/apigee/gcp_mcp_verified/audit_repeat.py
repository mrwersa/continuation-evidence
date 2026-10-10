"""Audit a new execution separately, never combining earlier observations."""
import argparse
import json
import re
from pathlib import Path

from repeat_runner import check_dependencies
from check_results import audit, read
from design import schedule
from task_keys import namespaced


def audit_repeat(events, backend, attempts, responses, execution_id):
    check_dependencies()
    assert re.fullmatch(r"repeat-[0-9]{8}-[a-z0-9]{8}", execution_id)
    prefix = execution_id + "-"
    expected = {trial["id"]: trial for trial in schedule()}
    started = [row for row in events if row["kind"] == "sequence_started"]
    expected_order = [trial["id"] for trial in schedule()]
    assert [row["trial"]["id"] for row in started] == expected_order[:len(started)], "Changed order"
    for row in started:
        assert row["trial"] == expected[row["trial"]["id"]], "Changed scientific design"
    reservations = {row["request"]["id"]: row for row in events if row["kind"] == "call_reserved"}
    for row in attempts:
        assert row["task"] == reservations[row["request"]["id"]]["task"], "Remote task differs"
    for row in events:
        if row["kind"] in ("call_reserved", "response"):
            assert row["task"].startswith(prefix), "Key not in fresh execution namespace"
            stage = row["stage"].split("/")[0]
            if stage in expected:
                # Diagnostics have their own accounts even inside a trial stage.
                if not row["stage"].endswith("/diagnostic"):
                    assert row["task"] == namespaced(execution_id, expected[stage]["accounting_key"]), "Changed task key"
    summary = audit(events, backend, attempts, responses)
    assert all(row["status"] != "unrecorded" for row in summary["sequences"]), "Missing planned status"
    summary["execution_id"] = execution_id
    summary["pooled_with_previous_execution"] = False
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--execution-id", required=True)
    args = parser.parse_args()
    from integration import audit_transport
    logs = [read(args.directory / name) for name in
            ("events.jsonl", "backend.jsonl", "remote_attempts.jsonl", "remote_responses.jsonl")]
    audit_transport(logs[3], read(args.directory / "remote_transport.jsonl"))
    print(json.dumps(audit_repeat(*logs, args.execution_id), indent=2))
