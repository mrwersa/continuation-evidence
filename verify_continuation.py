"""Verify the validated revision matrix, configuration comparison and cap-change cells.

Every count is derived from the released per-trial records. Recorded outcome labels are
checked against the managed response bodies rather than trusted. Causal order uses the
recorded monotonic clock. UTC readings are retained as observed and checked for canonical
form only, because the capture host's wall clock can step backwards during a call.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from itertools import pairwise
from pathlib import Path
from typing import Any

from verify_revision import _instant
from verify_revision import summary as pair_summary

ROOT = Path(__file__).resolve().parent
DIGESTS = ROOT / "continuation-evidence.sha256"
TOOL = "ContinuationTarget___process_refund"
MARKER = "when temporal {\n"
PERMIT_A = "continuation-candidate-permit-a.dogwood"
AMOUNT = 600
MODE = "FAIL_ON_ANY_FINDINGS"
ARMS = {
    "byte_identical_statement": ((PERMIT_A, "exact"), None),
    "bound_variable_renaming": (("continuation-candidate-permit-b.dogwood", "exact"), None),
    "whitespace_only": ((PERMIT_A, "whitespace"), None),
    "description_only": (None, "D1"),
    "identical_description": (None, "D0"),
    "tightening_to_700": (("continuation-candidate-permit-a-700.dogwood", "exact"), None),
}


def _read(name: str) -> Any:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def _sha256(name: str) -> str:
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()


def _ordered(label: str, *values: int) -> None:
    if any(before > after for before, after in pairwise(values)):
        raise ValueError(f"{label} monotonic timestamps are not causally ordered")


def _shuffled(items: list[Any], seed: int) -> list[Any]:
    random.Random(seed).shuffle(items)
    return items


def _statement(value: Any, templates: dict[str, str]) -> tuple[str, str]:
    if not isinstance(value, dict):
        raise TypeError("policy snapshot lacks a statement")
    name, variant = value.get("template"), value.get("variant")
    if name not in templates or variant not in ("exact", "whitespace"):
        raise ValueError(f"statement names an unreviewed template or variant: {name}")
    if _sha256(name) != templates[name]:
        raise ValueError(f"{name} does not match its preregistered digest")
    text = (ROOT / name).read_text(encoding="utf-8").rstrip("\n")
    if variant == "whitespace":
        if MARKER not in text:
            raise ValueError(f"{name} lacks the whitespace insertion point")
        text = text.replace(MARKER, MARKER + "\n", 1)
    if hashlib.sha256(text.encode()).hexdigest() != value.get("sha256"):
        raise ValueError(f"recorded {name} digest does not match the reviewed text")
    return name, variant


def _outcome(call: dict[str, Any], amount: int = AMOUNT) -> str:
    request, response = call.get("request", {}), call.get("response", {})
    params = request.get("params", {})
    if (
        request.get("method") != "tools/call"
        or params.get("name") != TOOL
        or params.get("arguments") != {"amount": amount}
        or call.get("http_status") != 200
    ):
        raise ValueError("call does not match the reviewed request")
    _instant(call["started_utc"])
    _instant(call["finished_utc"])
    _ordered("call", call["started_monotonic_ns"], call["finished_monotonic_ns"])
    error = response.get("error", {})
    if response.get("result", {}).get("isError") is False and not error:
        outcome = "allow"
    elif error.get("code") == -32002:
        outcome = "deny"
    elif error.get("code") == -32005 and "Policy session is stale" in str(error.get("message")):
        outcome = "stale_session"
    else:
        raise ValueError("response is neither an allow, a denial nor a stale-session error")
    if call.get("derived_outcome") != outcome:
        raise ValueError("recorded outcome label disagrees with the managed response")
    return outcome


def _update(
    value: dict[str, Any],
    templates: dict[str, str],
    mode: str,
    statement: tuple[str, str] | None,
    description: str | None,
) -> bool:
    before, after, polls = value["before"], value["after"], value["polls"]
    submitted = value["submitted"]
    if (
        submitted.get("operation") != "UpdatePolicy"
        or submitted.get("validation_mode") != mode
        or submitted.get("definition_supplied") is not (statement is not None)
        or submitted.get("description") != description
        or value["managed_response"].get("status") != "UPDATING"
        or not polls
        or any(poll.get("poll_index") != index for index, poll in enumerate(polls))
        or polls[-1] != after
        or {before.get("status"), after.get("status")} != {"ACTIVE"}
        or {before.get("enforcement_mode"), after.get("enforcement_mode")} != {"ACTIVE"}
    ):
        raise ValueError("policy update does not match the reviewed request")
    for snapshot in (before, after, *polls):
        _statement(snapshot["statement"], templates)
    if statement is None:
        if submitted.get("statement") is not None or after["statement"] != before["statement"]:
            raise ValueError("description update changed the statement")
    elif (
        _statement(submitted["statement"], templates) != statement
        or after["statement"] != submitted["statement"]
    ):
        raise ValueError("active statement differs from the submitted statement")
    if after["description"] != (before["description"] if description is None else description):
        raise ValueError("active description differs from the submitted description")
    for stamp in (before, *polls):
        _instant(stamp["observed_utc"])
    _instant(value["requested_utc"])
    _instant(value["completed_utc"])
    _ordered(
        "policy update",
        before["observed_monotonic_ns"],
        value["requested_monotonic_ns"],
        *(poll["observed_monotonic_ns"] for poll in polls),
        value["completed_monotonic_ns"],
    )
    changed = before["revision_alias"] != after["revision_alias"]
    if value.get("revision_changed") is not changed:
        raise ValueError("recorded revision change disagrees with the revision aliases")
    if not changed and any(poll["revision_alias"] != before["revision_alias"] for poll in polls):
        raise ValueError("deduplicated update exposed a different revision while polling")
    return changed


def _controls(value: dict[str, Any]) -> bool:
    below, boundary = value["single_below"], value["single_boundary"]
    first, second = value["same_session_pair"]
    sessions = {below["session_alias"], boundary["session_alias"], first["session_alias"]}
    if (
        _outcome(below, 500) != "allow"
        or _outcome(boundary, 1000) != "deny"
        or [_outcome(first), _outcome(second)] != ["allow", "deny"]
        or first["session_alias"] != second["session_alias"]
        or len(sessions) != 3
        or value.get("matches_prediction") is not True
    ):
        raise ValueError(f"{value.get('label')} controls do not match their prediction")
    return True


def _sequence(trial: dict[str, Any], names: tuple[str, ...]) -> list[str]:
    calls = [trial[name] for name in names]
    update = trial["update"]
    _ordered(
        "trial",
        calls[0]["started_monotonic_ns"],
        calls[0]["finished_monotonic_ns"],
        update["requested_monotonic_ns"],
        update["completed_monotonic_ns"],
        *(
            stamp
            for call in calls[1:]
            for stamp in (call["started_monotonic_ns"], call["finished_monotonic_ns"])
        ),
    )
    elapsed = (calls[-1]["finished_monotonic_ns"] - calls[0]["started_monotonic_ns"]) / 1e9
    if trial.get("elapsed_monotonic_seconds") != elapsed or not 0 <= elapsed < 3600:
        raise ValueError("trial elapsed time is inconsistent or leaves the one-hour window")
    return [_outcome(call) for call in calls]


def matrix() -> dict[str, Any]:
    protocol = _read("revision-validated-protocol.json")
    events = _read("revision-validated-events.json")
    deployment = _read("revision-validated-deployment.json")
    templates, descriptions = protocol["templates"], protocol["descriptions"]
    attempts = deployment["validation_attempts"]
    if (
        [(attempt["candidate"], attempt["validated"]) for attempt in attempts]
        != [("permit_and_forbid", False), ("single_permit", True)]
        or "Overly Permissive" not in attempts[0]["error"]["message"]
        or events["candidate"] != "single_permit"
        or events["validation_mode"] != MODE
        or deployment["deployment"]["gateway"]["policy_engine_mode"] != "ENFORCE"
        or deployment["cleanup_complete"] is not True
        or not all(item["verified_absent"] for item in deployment["cleanup"])
        or list(protocol["arms"]) != list(ARMS)
    ):
        raise ValueError("validated matrix deployment does not match the reviewed protocol")
    trials = sorted(events["trials"], key=lambda trial: trial["order"])
    order = _shuffled(
        [(arm, index) for arm in ARMS for index in range(protocol["trials_per_arm"])],
        protocol["random_seed"],
    )
    if [(trial["arm"], trial["trial"]) for trial in trials] != order:
        raise ValueError("validated matrix trials do not follow the preregistered order")
    preflight, postflight = events["controls"]
    if (preflight["label"], postflight["label"]) != ("preflight", "postflight"):
        raise ValueError("validated matrix lacks its preflight and postflight controls")
    _controls(preflight)
    _controls(postflight)
    last = trials[-1].get("recovery_after_call", trials[-1]["predecessor_after_call"])
    _ordered(
        "validated matrix window",
        preflight["same_session_pair"][1]["finished_monotonic_ns"],
        trials[0]["before_call"]["started_monotonic_ns"],
        last["finished_monotonic_ns"],
        postflight["single_below"]["started_monotonic_ns"],
    )
    rows: dict[str, dict[str, Any]] = {}
    for trial in trials:
        statement, key = ARMS[trial["arm"]]
        base = trial["update"]["before"]
        if (
            trial.get("conforming") is not True
            or _statement(base["statement"], templates) != (PERMIT_A, "exact")
            or base["description"] != descriptions["D0"]
        ):
            raise ValueError("trial did not start from the validated base state")
        if trial["reset"] is not None:
            reset = trial["reset"]
            _update(reset, templates, MODE, (PERMIT_A, "exact"), descriptions["D0"])
            _ordered(
                "reset",
                reset["completed_monotonic_ns"],
                trial["before_call"]["started_monotonic_ns"],
            )
        description = None if key is None else descriptions[key]
        changed = _update(trial["update"], templates, MODE, statement, description)
        names: tuple[str, ...] = ("before_call", "predecessor_after_call")
        if "recovery_call" in trial:
            names = (*names, "recovery_call", "recovery_after_call")
        outcomes = _sequence(trial, names)
        sessions = [trial[name]["session_alias"] for name in names]
        if outcomes[0] != "allow" or sessions[0] != sessions[1]:
            raise ValueError("predecessor session does not admit then reuse one session")
        row = rows.setdefault(
            trial["arm"],
            {"elapsed": [], "changed": 0, "predecessor": Counter(), "successor": Counter()},
        )
        row["elapsed"].append(trial["elapsed_monotonic_seconds"])
        row["changed"] += changed
        row["predecessor"][outcomes[1]] += 1
        if len(names) == 4:
            if sessions[2] != sessions[3] or sessions[2] == sessions[0]:
                raise ValueError("successor does not use one fresh session")
            row["successor"]["-".join(outcomes[2:])] += 1
    derived: dict[str, Any] = {}
    for arm, row in rows.items():
        derived[arm] = {
            "maximum_elapsed_seconds": max(row["elapsed"]),
            "nonconforming": 0,
            "predecessor_after_update": dict(row["predecessor"]),
            "revision_changed": row["changed"],
            "trials": len(row["elapsed"]),
        }
        if row["successor"]:
            derived[arm]["successor_sequence"] = dict(row["successor"])
    tightened = rows["tightening_to_700"]["successor"]
    derived["tightening_to_700"]["discrimination"] = {
        "carry_refuses_first_successor_call": sum(
            count for sequence, count in tightened.items() if sequence.startswith("deny")
        ),
        "reset_admits_first_successor_call": sum(
            count for sequence, count in tightened.items() if sequence.startswith("allow")
        ),
    }
    released = _read("revision-validated-summary.json")
    if (
        released["arms"] != derived
        or released["controls"] != {"preflight": True, "postflight": True}
        or released["candidate"] != events["candidate"]
        or released["validation_mode"] != events["validation_mode"]
        or released["stopped"] is not None
    ):
        raise ValueError("validated matrix summary does not reproduce from its events")
    return derived


def comparison() -> dict[str, Any]:
    protocol = _read("revision-diagnostic-protocol.json")
    events = _read("revision-diagnostic-events.json")
    templates = _read("revision-validated-protocol.json")["templates"]
    names = _shuffled(list(protocol["configurations"]), protocol["design"]["random_seed"])
    if (
        events["diagnostic_protocol_sha256"] != _sha256("revision-diagnostic-protocol.json")
        or events["block_order"] != names
        or [block["configuration"] for block in events["blocks"]] != names
        or events["cleanup_complete"] is not True
        or events["stopped"] is not None
    ):
        raise ValueError("comparison blocks do not follow the preregistered order")
    derived = {}
    for block in events["blocks"]:
        configuration = protocol["configurations"][block["configuration"]]
        mode = configuration["validation_mode"]
        if (
            block["validation_mode"] != mode
            or block["update_sets_enforcement_mode"]
            is not configuration["update_sets_enforcement_mode"]
            or block["controls"]["label"] != block["configuration"]
        ):
            raise ValueError("comparison block does not match its preregistered configuration")
        controls = _controls(block["controls"])
        changed, predecessor, statuses = 0, Counter(), Counter()
        for trial in block["trials"]:
            if trial.get("conforming") is not True or trial["reset"] is not None:
                raise ValueError("comparison trial is nonconforming or needed a reset")
            base = (configuration["base"], "exact")
            revision = _update(trial["update"], templates, mode, base, None)
            outcomes = _sequence(trial, ("before_call", "predecessor_after_call"))
            if (
                outcomes[0] != "allow"
                or trial["before_call"]["session_alias"]
                != trial["predecessor_after_call"]["session_alias"]
            ):
                raise ValueError("comparison trial does not reuse its predecessor session")
            changed += revision
            predecessor[outcomes[1]] += 1
            statuses[trial["update"]["managed_response"]["status"]] += 1
        derived[block["configuration"]] = {
            "controls_match": controls,
            "managed_response_status": dict(statuses),
            "nonconforming": 0,
            "predecessor_after_update": dict(predecessor),
            "revision_changed": changed,
            "trials": len(block["trials"]),
            "update_sets_enforcement_mode": block["update_sets_enforcement_mode"],
            "validation_mode": mode,
        }
    released = _read("revision-diagnostic-summary.json")
    if released["configurations"] != derived or released["cleanup_complete"] is not True:
        raise ValueError("comparison summary does not reproduce from its events")
    return derived


def _classify(trial: dict[str, Any], cell: dict[str, Any]) -> str:
    before = trial["before_update"]
    if not before or any(unit["session_status"] != "idle" for unit in before):
        raise ValueError("cap-change trial lacks idle work before its transition")
    if trial["cell"] == "cap_at_or_below_spend_refused":
        result = trial["result"]
        reported = result["reported_cents"]
        refused = (
            reported >= cell["consume_until_reported_cents_at_least"]
            and before[-1]["list_cost_minor_units"] == reported
            and result["attempted_cap"] == reported - 1
            and result["refusal"]["status_code"] == 400
            and "must be greater than the session's consumed list cost"
            in result["refusal"]["message"]
            and result["retrieved_cap"] == cell["create_cap_cents"]
        )
        return "refused" if refused else "indeterminate"
    after = trial["after_update"]
    if not after or after[-1]["idle_reason"] != "budget_reached":
        raise ValueError("cap-change trial did not stop at its session budget")
    if trial["cell"] == "lowered_cap_carries_spend":
        update, result = trial["cap_update"], trial["result"]
        reported = update["reported_cents"]
        if (
            reported < cell["consume_until_reported_cents_at_least"]
            or before[-1]["list_cost_minor_units"] != reported
            or update["requested_cap"] != reported + 2
            or update["response_cap"] != update["requested_cap"]
            or update["retrieved_cap"] != update["requested_cap"]
            or result["final_reported_cents"] != after[-1]["list_cost_minor_units"]
            or result["added_cents"] != result["final_reported_cents"] - reported
            or trial["post_budget_refusal"]["status_code"] != 400
            or "session budget reached" not in trial["post_budget_refusal"]["message"]
        ):
            raise ValueError("lowered-cap trial does not match its preregistered procedure")
        if result["added_cents"] <= 3:
            return "carry"
        return "reset" if result["added_cents"] >= 5 else "indeterminate"
    update, result = trial["agent_update"], trial["result"]
    if (
        update["reported_cents"] < cell["consume_until_reported_cents_at_least"]
        or before[-1]["list_cost_minor_units"] != update["reported_cents"]
        or update["updated_version"] != update["original_version"] + 1
        or result["final_reported_cents"] != after[-1]["list_cost_minor_units"]
    ):
        raise ValueError("agent-update trial does not match its preregistered procedure")
    pinned = (
        update["session_version_after_update"] == update["original_version"]
        and result["session_version_at_budget"] == update["original_version"]
    )
    if pinned and result["final_reported_cents"] <= 7:
        return "pinned_and_retained"
    return "reset" if result["final_reported_cents"] >= 8 else "indeterminate"


def cap_change() -> dict[str, dict[str, int]]:
    protocol = _read("anthropic-cap-change-protocol.json")
    evidence = _read("anthropic-cap-change-trials.json")
    cells = list(protocol["cells"])
    trials = sorted(evidence["trials"], key=lambda trial: trial["order"])
    order = _shuffled(
        [(cell, index) for cell in cells for index in range(1, protocol["trials_per_cell"] + 1)],
        protocol["random_seed"],
    )
    if (
        evidence["protocol_sha256"] != _sha256("anthropic-cap-change-protocol.json")
        or [(trial["cell"], trial["trial"]) for trial in trials] != order
        or evidence["stopped"] is not None
        or evidence["cleanup"]["complete"] is not True
        or evidence["pilot"]["excluded_from_results"] is not True
    ):
        raise ValueError("cap-change trials do not follow the preregistered protocol")
    counts: dict[str, Counter[str]] = {cell: Counter() for cell in cells}
    for trial in trials:
        classification = _classify(trial, protocol["cells"][trial["cell"]])
        if classification != trial["classification"]:
            raise ValueError("recorded cap-change classification disagrees with its trial")
        counts[trial["cell"]][classification] += 1
    derived = {cell: dict(values) for cell, values in counts.items()}
    released = _read("anthropic-cap-change-summary.json")["results"]
    if {cell: result["classifications"] for cell, result in released.items()} != derived:
        raise ValueError("cap-change summary does not reproduce from its trials")
    return derived


def isolation() -> dict[str, Any]:
    events = _read("isolation-events.json")
    released = _read("isolation-summary.json")
    amount, threshold = released["request_amount"], released["threshold"]
    if (
        events["provider"] != "AWS AgentCore Gateway Policy"
        or events["principal_identity"]["authenticated_by"] != "AWS_IAM"
        or events["principal_identity"]["raw_identifiers_retained"] is not False
        or events["retry"]["application_retries"] != 0
        or released["mandate_sha256"] != events["mandate_sha256"]
        or len(events["trials"]) != 2 * released["trials_per_arm"]
    ):
        raise ValueError("isolation events do not match the reviewed capture")

    controls: dict[str, dict[str, str]] = {}
    for control in events["controls"]:
        value = control["request"]["params"]["arguments"]["amount"]
        label = "below_500" if value < threshold else "boundary_1000"
        controls.setdefault(f"principal_{control['principal_alias']}", {})[label] = control[
            "outcome"
        ]

    durations, arms = [], {"same": Counter(), "changed": Counter()}
    directions: Counter[str] = Counter()
    for trial in events["trials"]:
        sequence = trial["principal_sequence"]
        same = sequence[0] == sequence[1]
        if (
            trial["arm"] != ("same" if same else "changed")
            or [call["principal_alias"] for call in trial["calls"]] != sequence
            or not isinstance(trial["session_alias"], str)
            or not trial["session_alias"]
            or len(trial["calls"]) != 2
            or any(
                call["request"]["params"]["arguments"] != {"amount": amount}
                for call in trial["calls"]
            )
        ):
            raise ValueError(f"isolation trial {trial['trial']} does not hold its session fixed")
        for call in trial["calls"]:
            _instant(call["started_at"])
            _instant(call["finished_at"])
            if call["duration_ms"] <= 0:
                raise ValueError(f"isolation trial {trial['trial']} has a non-positive duration")
        durations.extend(call["duration_ms"] for call in trial["calls"])
        arms[trial["arm"]]["-".join(call["outcome"] for call in trial["calls"])] += 1
        if not same:
            directions[f"{sequence[0]}_to_{sequence[1]}"] += 1

    derived = {
        "changed_principal_aggregate": 2 * amount,
        "changed_principal_allow_then_allow": arms["changed"]["allow-allow"],
        "direction_counts": dict(sorted(directions.items())),
        "managed_call_ms": {"maximum": max(durations), "minimum": min(durations)},
        "same_principal_allow_then_deny": arms["same"]["allow-deny"],
        "single_request_controls": {name: dict(sorted(v.items())) for name, v in controls.items()},
    }
    if released["results"] != derived:
        raise ValueError("isolation summary does not reproduce from its events")
    if sum(arms["same"].values()) != sum(arms["changed"].values()) != released["trials_per_arm"]:
        raise ValueError("isolation arms are not balanced")
    return derived


def main() -> None:
    for line in DIGESTS.read_text().splitlines():
        expected, name = line.split()
        if _sha256(name) != expected:
            raise ValueError(f"{name} does not match the released continuation digest")
    arms = matrix()
    blocks = comparison()
    cells = cap_change()

    forms = {
        style: (ROOT / f"revision-policy-{style}.dogwood").read_text(encoding="utf-8").rstrip("\n")
        for style in ("a", "b")
    }
    pair = pair_summary(
        _read("revision-events.json"), forms, _read("revision-metadata-events.json")
    )
    pair_revisions = [*pair["alpha_equivalent_trials"], *pair["whitespace_only_trials"]]
    created = [*arms.values(), *(row for row in blocks.values() if row["revision_changed"])]
    unchanged = [row for row in blocks.values() if not row["revision_changed"]]
    revisions = sum(row["revision_changed"] for row in created)
    revisions += sum(row["update"]["revision_changed"] for row in pair_revisions)
    stale = sum(row["predecessor_after_update"].get("stale_session", 0) for row in created)
    stale += sum(
        row["predecessor_session_after_update"] == "stale_session" for row in pair_revisions
    )
    deduplicated = sum(row["trials"] for row in unchanged) + len(pair["byte_identical_trials"])
    kept = sum(row["predecessor_after_update"].get("deny", 0) for row in unchanged)
    kept += sum(row["same_session_after_write"] == "deny" for row in pair["byte_identical_trials"])
    if revisions != stale or deduplicated != kept:
        raise ValueError("session staleness does not track revision creation")

    tightened = arms["tightening_to_700"]["discrimination"]["reset_admits_first_successor_call"]
    trials = sum(row["trials"] for row in arms.values())
    print(
        f"PASS  validated matrix reproduces {trials} trials in preregistered order, and the "
        f"tightened successor admitted its first request in {tightened}"
    )
    print(
        "PASS  configuration comparison reproduces "
        + ", ".join(
            f"{name} {row['revision_changed']}/{row['trials']} revisions"
            for name, row in blocks.items()
        )
    )
    print(
        f"PASS  across both configurations {revisions} revision-creating writes made their "
        f"session stale and {deduplicated} deduplicated writes kept refusal"
    )
    print(
        "PASS  cap-change record reproduces "
        + ", ".join(f"{cell} {values}" for cell, values in cells.items())
    )
    separation = isolation()
    print(
        "PASS  isolation record reproduces "
        f"{separation['same_principal_allow_then_deny']} same-principal Allow then Deny and "
        f"{separation['changed_principal_allow_then_allow']} changed-principal Allow then Allow"
    )


if __name__ == "__main__":
    main()
