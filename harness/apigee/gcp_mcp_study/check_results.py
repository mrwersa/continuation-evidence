"""Audit exported original logs and summarise every planned sequence offline."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from design import schedule


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def audit(events, backend, remote_attempts, remote_responses):
    reservations = [r for r in events if r["kind"] == "call_reserved"]
    responses = [r for r in events if r["kind"] == "response"]
    requests = {r["request"]["id"]: r for r in reservations}
    assert len(requests) == len(reservations), "Duplicate reserved identity"
    response_ids = [r["request"]["id"] for r in responses]
    assert len(set(response_ids)) == len(response_ids), "Duplicate client response"
    assert set(response_ids) <= requests.keys(), "Unreserved response"
    remote_ids = [r["request"]["id"] for r in remote_attempts]
    assert len(remote_ids) == len(set(remote_ids)), "Duplicate remote attempt"
    assert set(remote_ids) <= requests.keys(), "Remote attempt not reserved locally"
    remote_by_id = {r["request_id"]: r for r in remote_responses}
    assert len(remote_by_id) == len(remote_responses), "Duplicate remote response"
    assert remote_by_id.keys() <= set(remote_ids), "Remote response not attempted"
    backend_by_id = defaultdict(list)
    for row in backend:
        backend_by_id[row["request"]["id"]].append(row)
    assert backend_by_id.keys() <= requests.keys(), "Unexplained backend dispatch"
    assert all(len(rows) == 1 for rows in backend_by_id.values()), "Duplicate backend dispatch"
    calls = [r for r in reservations if r["request"]["method"] == "tools/call"]
    assert len(calls) <= 500, "Exceeded call budget"
    assert [r["calls"] for r in calls] == list(range(1, len(calls)+1)), "Non-contiguous call reservation"
    observations = {}
    for row in responses:
        req, captured = row["request"], row["response"]
        rid = req["id"]
        assert captured == remote_by_id[rid], "Local and remote responses differ"
        assert captured["backend_matches"] == backend_by_id.get(rid, []), "Live backend audit differs from full export"
        assert req == requests[rid]["request"], "Reserved and sent arguments differ"
        assert captured.get("delivery") == "response_received", "Uncertain response, review manually"
        body = json.loads(captured["body"])
        fault = body.get("fault", {}).get("detail", {}).get("errorcode")
        if captured["status"] == 200 and "result" in body:
            assert body.get("id") == rid and not body["result"].get("isError", False)
            assert len(backend_by_id[rid]) == 1 and backend_by_id[rid][0]["request"] == req
            outcome = "admit"
            if req["method"] == "tools/call":
                receipt = json.loads(body["result"]["content"][0]["text"])
                assert receipt == {"receipt": rid, "amount": req["params"]["arguments"]["amount"], "effect": "none"}
        elif fault == "policies.ratelimit.QuotaViolation":
            assert not backend_by_id.get(rid), "Quota refusal reached backend"
            outcome = "refuse"
        else:
            outcome = "technical_error"
        if req["method"] == "tools/call":
            h = captured["headers"]
            observations[row["stage"]] = {"outcome": outcome, "used": int(h["x-smoke-used"]),
                "available": int(h["x-smoke-available"]), "revision": h["x-smoke-revision"],
                "limit": int(h["x-smoke-limit"]), "expiry": int(h["x-smoke-expiry"])}
    statuses = [r for r in events if r["kind"] == "sequence_status"]
    status_by_id = {r["id"]: r for r in statuses}
    assert len(status_by_id) == len(statuses), "Multiple final statuses"
    assert status_by_id.keys() <= {t["id"] for t in schedule()}
    results = []
    for trial in schedule():
        identity = trial["id"]
        status = status_by_id.get(identity, {"status": "unrecorded"})
        probes = [observations.get(identity+f"/probe-{i+1}") for i in range(2)]
        conformance = None
        distinct_revision = None
        if status["status"] == "complete":
            assert all(probes), "Complete sequence lacks both probes"
            expected = trial["conformance_pattern"]
            if expected is not None:
                conformance = [p["outcome"] for p in probes] == expected
                used = {"no_update": [900, 900], "identical": [900, 900], "whitespace": [900, 900],
                        "tighten700": [650, 650], "tighten500": [600, 600], "fresh1000": [300, 500], "fresh700": [50, 150]}[trial["arm"]]
                conformance = conformance and [p["used"] for p in probes] == used
                limit = 700 if trial["arm"] in ("tighten700", "fresh700") else 500 if trial["arm"] == "tighten500" else 1000
                conformance = conformance and all(p["limit"] == limit for p in probes)
                if trial["preload"]:
                    preload = observations.get(identity+"/preload")
                    conformance = conformance and bool(preload) and preload["used"] == 600 and preload["outcome"] == "admit" and preload["limit"] == 1000
                    conformance = conformance and all(p["expiry"] == preload["expiry"] for p in probes)
                    if trial["focal_variant"] is not None:
                        distinct_revision = all(p["revision"] != preload["revision"] for p in probes)
                        conformance = conformance and distinct_revision
            elif trial["preload"]:
                preload = observations.get(identity+"/preload")
                distinct_revision = bool(preload) and all(p["revision"] != preload["revision"] for p in probes)
        results.append({"id": identity, "arm": trial["arm"], "block": trial["block"], "status": status["status"],
                        "probes": probes, "observed_distinct_revision": distinct_revision, "observed_conformance": conformance})
    arms = {}
    for arm in sorted({t["arm"] for t in schedule()}):
        subset = [r for r in results if r["arm"] == arm]
        arms[arm] = {"planned": len(subset), "statuses": dict(Counter(r["status"] for r in subset)),
                     "observed_conforming": sum(r["observed_conformance"] is True for r in subset),
                     "combined_requirement_not_met": sum(r["observed_conformance"] is False for r in subset),
                     "observed_distinct_revisions": sum(r["observed_distinct_revision"] is True for r in subset),
                     "patterns": dict(Counter(",".join(p["outcome"] for p in r["probes"]) for r in subset if all(r["probes"])))}
    return {"reserved_tool_calls": len(calls), "responses": len(responses), "backend_records": len(backend),
            "unresolved_reservations": sorted(requests.keys()-set(response_ids)), "arms": arms, "sequences": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(*[read(args.directory/name) for name in ("events.jsonl", "backend.jsonl", "remote_attempts.jsonl", "remote_responses.jsonl")]), indent=2))
