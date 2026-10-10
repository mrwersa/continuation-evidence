"""Reconcile the sanitised capture and regenerate its summary and manuscript table."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
LABELS = {"no_update": "No update", "identical": "Identical import",
          "whitespace": "Whitespace import", "tighten700": "Tighten to 700",
          "tighten500": "Tighten to 500", "rename_policy": "Policy-name change",
          "fresh1000": "Fresh key, 1,000", "fresh700": "Fresh key, 700"}


def unique(rows, field):
    result = {r[field]: r for r in rows}
    assert len(result) == len(rows), "Duplicate identity"
    return result


def epoch(utc):
    return datetime.fromisoformat(utc).timestamp()


def analyse(protocol, records, policies):
    assert policies["identical"] == policies["baseline"]
    base = policies["baseline"]
    quota = "apiproxy/policies/RefundQuota.xml"
    for variant, files in policies.items():
        expected = dict(base)
        if variant.startswith("tighten"):
            expected[quota] = expected[quota].replace('count="1000"', f'count="{variant[7:]}"')
        elif variant == "whitespace":
            expected[quota] = expected[quota].replace("/><Interval>", "/>\n    <Interval>")
        elif variant == "rename_policy":
            expected = {k.replace("RefundQuota", "RefundQuotaRenamed"):
                        v.replace("RefundQuota", "RefundQuotaRenamed") for k, v in base.items()}
        assert files == expected, "Unexpected policy difference"
        for name, value in files.items():
            if name.endswith('.xml'):
                ET.fromstring(value)
    calls = unique([{**r, "id": r["request"]["id"]} for r in records["calls"]], "id")
    client = unique(records["client_responses"], "id")
    remote = unique(records["remote_responses"], "id")
    attempts = unique([{**r, "id": r["request"]["id"]} for r in records["remote_attempts"]], "id")
    backend = unique([{**r, "id": r["request"]["id"]} for r in records["backend"]], "id")
    assert calls.keys() == client.keys() == remote.keys() == attempts.keys()
    assert client == remote, "Client and remote responses differ"
    if protocol.get("schema") == 2:
        assert unique(records["remote_transport"], "id") == remote, "Transport and remote responses differ"
    assert backend.keys() <= calls.keys()
    stages, outcomes, calibration = {}, Counter(), []
    ready = {}
    for r in records["deployments"]:
        if r["state"] == "READY":
            ready.setdefault(r["revision"], epoch(r["utc"]))
    for rid, call in calls.items():
        request, response = call["request"], client[rid]
        assert attempts[rid]["request"] == request and attempts[rid]["task"] == call["task"]
        assert epoch(call["utc"]) <= attempts[rid]["reserved_at"] <= response["start"] <= response["end"]
        assert response["delivery"] == "response_received"
        if response.get("fault") == "policies.ratelimit.QuotaViolation":
            assert response["status"] == 429 and rid not in backend
            outcome = "R"
        else:
            assert response["status"] == 200 and response["result_present"] and not response["is_error"]
            assert response["rpc_id"] == rid
            assert backend[rid]["request"] == request
            assert response["start"] <= epoch(backend[rid]["utc"]) <= response["end"]
            outcome = "A"
        if request["method"] != "tools/call":
            continue
        h = response["headers"]
        assert h["x-smoke-operation"] == "tools/call/refund"
        assert int(h["x-smoke-expiry"]) == protocol["window_expiry"]
        assert response["end"] * 1000 < protocol["window_expiry"]
        assert ready[h["x-smoke-revision"]] <= response["start"]
        if outcome == "A":
            assert response["receipt"] == {"id": rid, "amount": request["amount"], "effect": "none"}
        stages[call["stage"]] = {"outcome": outcome, "amount": request["amount"],
            "used": int(h["x-smoke-used"]), "available": int(h["x-smoke-available"]),
            "limit": int(h["x-smoke-limit"]), "revision": h["x-smoke-revision"],
            "task": call["task"], "start": response["start"], "end": response["end"]}
        if call["stage"] in ("calibration", "equality_observation"):
            calibration.append((call["stage"], request["amount"], outcome, int(h["x-smoke-used"])))
        outcomes[outcome] += 1
    tool_calls = [r for r in calls.values() if r["request"]["method"] == "tools/call"]
    assert calibration == [("calibration", 600, "A", 600), ("calibration", 600, "R", 600),
                           ("calibration", 300, "A", 900), ("equality_observation", 1000, "A", 1000),
                           ("equality_observation", 1, "R", 1000)], "Calibration differs"
    assert [r["count"] for r in tool_calls] == list(range(1, len(tool_calls)+1))
    assert len(tool_calls) <= protocol["tool_call_ceiling"]
    statuses = unique(records["statuses"], "id")
    assert statuses.keys() == {t["id"] for t in protocol["schedule"]}
    assert [r["id"] for r in records["statuses"]] == [t["id"] for t in protocol["schedule"]]
    status_order = [r["status"] for r in records["statuses"]]
    assert status_order == sorted(status_order, key={"complete": 0, "truncated": 1, "not_started": 2}.get)
    assert dict(Counter(status_order)) == protocol["expected_statuses"], "Execution status counts differ"
    if status_order.count("truncated"):
        assert len(records["abort"]) == 1 and records["management_errors"], "Partial stop unrecorded"
    else:
        assert not records["abort"] and not records["management_errors"], "Complete run has error records"
    trials = []
    keys = []
    for t in protocol["schedule"]:
        identity = t["id"]
        probes = [stages.get(identity + '/probe-' + str(i)) for i in (1, 2)]
        preload = stages.get(identity + '/preload')
        status = statuses[identity]["status"]
        if status == "complete":
            assert all(probes)
            assert [p["amount"] for p in probes] == t["probes"]
            assert all(p["task"] == t["accounting_key"] for p in probes)
            assert probes[0]["revision"] == probes[1]["revision"]
            expected_limit = 700 if t["arm"] in ("tighten700", "fresh700") else 500 if t["arm"] == "tighten500" else 1000
            assert all(p["limit"] == expected_limit for p in probes), "Wrong arm limit"
            keys.append(t["accounting_key"])
            if t["preload"]:
                assert preload and preload["outcome"] == "A" and preload["amount"] == 600
                assert preload["used"] == 600 and preload["limit"] == 1000
                assert preload["task"] == t["accounting_key"] and preload["end"] <= probes[0]["start"]
                if t["focal_variant"]:
                    assert preload["revision"] != probes[0]["revision"]
                if t["arm"] == "no_update":
                    assert probes[0]["start"] - preload["end"] >= 120
            if t["uses_parent_deployment"]:
                assert probes[0]["revision"] == stages[t["uses_parent_deployment"] + '/probe-1']["revision"]
        elif status == "not_started":
            assert not preload and not any(probes)
        elif status == "truncated":
            assert preload and not any(probes)
        else:
            raise AssertionError("Unexpected recorded status")
        trials.append({"id": identity, "arm": t["arm"], "block": t["block"], "status": status,
                       "preload": preload, "probes": probes})
    assert len(keys) == len(set(keys))
    arms = {}
    for arm in LABELS:
        subset = [r for r in trials if r["arm"] == arm]
        complete = [r for r in subset if r["status"] == "complete"]
        arms[arm] = {"planned": len(subset), "complete": len(complete),
            "statuses": dict(Counter(r["status"] for r in subset)),
            "requests": dict(Counter(', '.join(str(p["amount"]) for p in r["probes"]) for r in complete)),
            "patterns": dict(Counter(', '.join(p["outcome"] for p in r["probes"]) for r in complete)),
            "used": dict(Counter(', '.join(str(p["used"]) for p in r["probes"]) for r in complete))}
    return {"statuses": dict(Counter(t["status"] for t in trials)), "arms": arms,
            "tool_calls": len(tool_calls), "tool_outcomes": dict(outcomes),
            "responses": len(client), "backend_records": len(backend),
            "ready_revisions": len(ready), "abort": records["abort"], "trials": trials}


def table(result):
    lines = [r'\begin{table}[t]', r'\centering\small',
        r'\caption{Apigee MCP sequences. Every sequence in an arm had the listed result: A is admission and R quota refusal. Requests and Used give the two probe amounts and the resulting native totals. All but fresh-key controls preload 600. Limits are 1,000 unless named.}',
        r'\label{tab:apigee}', r'\setlength{\tabcolsep}{4pt}',
        r'\begin{tabular}{@{}lrrcr@{}}', r'\toprule',
        r'Arm & Seq. & Requests & Result & Used \\', r'\midrule']
    for arm, label in LABELS.items():
        row = result['arms'][arm]
        assert row['complete'] == row['planned'], 'Incomplete arm'
        assert len(row['requests']) == len(row['patterns']) == len(row['used']) == 1
        requests = next(iter(row['requests'])).replace(', ', '/')
        pattern = next(iter(row['patterns'])).replace(', ', '/')
        used = next(iter(row['used'])).replace(', ', '/')
        lines.append(f"{label} & {row['complete']} & {requests} & {pattern} & {used}" + r' \\')
    lines += [r'\bottomrule', r'\end{tabular}', r'\end{table}', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    names = ('apigee_protocol.json', 'apigee_records.json', 'apigee_policies.json')
    result = analyse(*[json.loads((ROOT/n).read_text()) for n in names])
    outputs = {'apigee_summary.json': json.dumps(result, indent=2)+'\n',
               'apigee_table.tex': table(result)}
    for name, value in outputs.items():
        if args.write:
            (ROOT/name).write_text(value)
        else:
            assert (ROOT/name).read_text() == value, 'Stale generated file: '+name
    hashes = ''.join(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()+'  '+n+'\n'
                     for n in (*names, *outputs))
    if args.write:
        (ROOT/'apigee_evidence.sha256').write_text(hashes)
    else:
        assert (ROOT/'apigee_evidence.sha256').read_text() == hashes
    print('PASS: records reconciled, '+str(result['statuses'])+', '+str(result['tool_calls'])+' tool calls')


if __name__ == '__main__':
    main()
