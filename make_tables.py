"""Generate evidence-backed TeX from the vendored authority summary."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SUMMARY = ROOT / "evidence-summary.json"
DIGEST = ROOT / "evidence-summary.sha256"
CAPTURES = ROOT / "table_captures.tex"
VALUES = ROOT / "evidence_values.tex"
ANTHROPIC = ROOT / "anthropic-session-budgets.json"
ANTHROPIC_DIGEST = ROOT / "anthropic-session-budgets.sha256"
PAIRED_LATENCY = ROOT / "binding-paired-latency.json"
if not PAIRED_LATENCY.exists():
    PAIRED_LATENCY = ROOT / "artifact" / "binding-paired-latency.json"
PAIRED_LATENCY_DIGEST = PAIRED_LATENCY.with_suffix(".sha256")
BOOTSTRAP_SEED = 20260831
BOOTSTRAP_REPETITIONS = 100_000


def _macro(name: str, value: object) -> str:
    """Emit one \\newcommand, rejecting names TeX cannot parse.

    TeX control-sequence names are letters only. A digit in the name silently
    truncates the command and the remainder becomes body text, which surfaces as
    "Missing \\begin{document}" far from the real cause.
    """
    if not name.isalpha():
        raise ValueError(f"macro name must be letters only, got {name!r}")
    return rf"\newcommand{{\{name}}}{{{_tex(value)}}}"


def _tex(value: object) -> str:
    return (
        str(value)
        .replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("_", r"\_")
        .replace("%", r"\%")
        .replace("->", r"$\rightarrow$")
    )


def _load() -> dict[str, object]:
    raw = SUMMARY.read_bytes()
    expected = DIGEST.read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError("evidence-summary.json does not match its committed digest")
    data = json.loads(raw)
    anthropic_raw = ANTHROPIC.read_bytes()
    anthropic_expected = ANTHROPIC_DIGEST.read_text(encoding="utf-8").split()[0]
    anthropic_actual = hashlib.sha256(anthropic_raw).hexdigest()
    if anthropic_actual != anthropic_expected:
        raise ValueError("anthropic-session-budgets.json does not match its committed digest")
    captures = data["captures"]
    corrections = data["correction_classification"]
    if data["summary_version"] != 1:
        raise ValueError("unsupported evidence summary version")
    if data["capture_count"] != len(captures):
        raise ValueError("capture count does not match capture records")
    if data["authority_graph_count"] != sum(item["authority_graph"] for item in captures):
        raise ValueError("authority graph count does not match capture records")
    if corrections["complete"] or corrections["class_counts"] is not None:
        raise ValueError("incomplete legacy correction classes must not be reported")
    if (
        len(data["live_comparisons"]) != 1
        or len(data["managed_controls"]) != 1
        or len(data["temporal_sessions"]) != 1
        or len(data["mandate_bindings"]) != 1
        or len(data["temporal_repetitions"]) != 1
        or len(data["anthropic_session_budgets"]) != 1
    ):
        raise ValueError(
            "expected one live comparison, control, temporal, binding, and repetition record"
        )
    if data["anthropic_session_budgets"][0]["artifact_sha256"] != anthropic_actual:
        raise ValueError("Anthropic summary does not pin the vendored trial artifact")
    data["_anthropic_trials"] = json.loads(anthropic_raw)
    paired_raw = PAIRED_LATENCY.read_bytes()
    paired_expected = PAIRED_LATENCY_DIGEST.read_text(encoding="utf-8").split()[0]
    paired_actual = hashlib.sha256(paired_raw).hexdigest()
    if paired_actual != paired_expected:
        raise ValueError("binding-paired-latency.json does not match its committed digest")
    data["_paired_latency"] = json.loads(paired_raw)
    return data


def _bootstrap_median_interval(values: list[float]) -> tuple[float, float]:
    """Return a deterministic 95% percentile-bootstrap interval for the median."""
    rng = random.Random(BOOTSTRAP_SEED)
    medians = sorted(
        statistics.median(rng.choices(values, k=len(values)))
        for _ in range(BOOTSTRAP_REPETITIONS)
    )
    lower = medians[int(0.025 * BOOTSTRAP_REPETITIONS)]
    upper = medians[int(0.975 * BOOTSTRAP_REPETITIONS) - 1]
    return lower, upper


def _capture_table(data: dict[str, object]) -> str:
    kinds = {
        "static-source": "Static source",
        "local-runtime": "Local runtime",
        "managed-live": r"\textbf{Live}",
    }
    rows = []
    for capture in data["captures"]:
        rows.append(
            " & ".join(
                (
                    _tex(capture["upstream_project"]),
                    _tex(capture["domain"]),
                    _tex(capture["enforcement_pattern"]),
                    _tex(capture["pinned_version"]),
                    kinds[capture["capture_kind"]],
                )
            )
            + r" \\" 
        )
    return "\n".join(
        (
            r"\begin{table*}[t]",
            r"\centering",
            r"\caption{\EvidenceCaptureCount{} captures and their evidence kind. \EvidenceGraphCount{} include an analysable authority graph.}",
            r"\label{tab:captures}",
            r"\small",
            r"\begin{tabular}{@{}>{\raggedright\arraybackslash}p{0.20\textwidth}>{\raggedright\arraybackslash}p{0.13\textwidth}>{\raggedright\arraybackslash}p{0.21\textwidth}>{\raggedright\arraybackslash}p{0.17\textwidth}l@{}}",
            r"\toprule",
            r"Deployment & Domain & Enforcement pattern & Pinned at & Kind \\ ",
            r"\midrule",
            *rows,
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table*}",
            "",
        )
    )


def _values(data: dict[str, object]) -> str:
    corrections = data["correction_classification"]
    comparison = data["live_comparisons"][0]
    measurement = comparison["measurement"]
    controls = data["managed_controls"][0]
    sequence = controls["permitted_sequence"]
    temporal = data["temporal_sessions"][0]
    binding = data["mandate_bindings"][0]
    latency = binding["live_latency"]
    repetitions = data["temporal_repetitions"][0]
    session_cells = repetitions["session_cells"]
    policy_updates = repetitions["policy_updates"]
    binding_cells = repetitions["binding_cells"]
    paired = repetitions["paired_latency"]
    paired_artifact = data["_paired_latency"]
    semantic_noop = repetitions["semantic_noop_revision"]
    binding_revision = repetitions["binding_policy_revision"]
    anthropic = data["anthropic_session_budgets"][0]
    anthropic_trials = data["_anthropic_trials"]["trials"]
    anthropic_cells = {
        name: [trial for trial in anthropic_trials if trial["cell"] == name]
        for name in (
            "subagent_handoff",
            "concurrent_subagents_2",
            "concurrent_subagents_4",
        )
    }
    requests = {item["arguments"]["amount"]: item for item in comparison["requests"]}
    if requests[500]["change"] != "stable_allow" or requests[2000]["change"] != "widens":
        raise ValueError("live widening outcomes do not match the paper comparison")
    calls = sequence["calls"]
    if len(calls) != 2 or any(call["outcome"] != "allow" for call in calls):
        raise ValueError("permitted sequence must contain two allowed calls")
    same_calls = temporal["same_session"]["calls"]
    fresh_calls = temporal["fresh_sessions"]["calls"]
    if (
        [item["outcome"] for item in same_calls] != ["allow", "deny"]
        or [item["outcome"] for item in fresh_calls] != ["allow", "allow"]
        or temporal["conformance"]["within_session_accumulation"] != "observed"
        or temporal["conformance"]["fresh_session_reset"] != "observed"
    ):
        raise ValueError("temporal session outcomes do not match the paper experiment")
    if (
        [item["outcome"] for item in binding["same_signed_mandate"]["calls"]]
        != ["allow", "deny"]
        or [item["outcome"] for item in binding["different_signed_mandate"]["calls"]]
        != ["allow"]
        or latency["outcomes"] != ["allow"] * latency["samples"]
        or latency["gateway_verified_binding"] is not False
        or latency["credential_path"] != "exclusive trusted adapter"
    ):
        raise ValueError("mandate binding outcomes do not match the paper experiment")
    if (
        session_cells
        != {
            "concurrent_exactly_one_allow": 10,
            "concurrent_intervals_overlapped": 10,
            "fresh_sessions_allow_then_allow": 10,
            "same_session_allow_then_deny": 10,
        }
        or policy_updates["no_update_allow_then_deny"] != 10
        or policy_updates["old_session_rejected_as_stale"] != 10
        or policy_updates["fresh_recovery_allowed"] != 10
        or policy_updates["recovery_aggregate_across_revisions"] != 1200
        or binding_cells["same_binding_allow_then_deny"] != 10
        or binding_cells["different_binding_allowed"] != 10
        or binding_cells["tampered_rejected_before_network"] != 10
        or binding_cells["expired_rejected_before_network"] != 10
        or paired["pairs"] != 30
        or semantic_noop["byte_identical_write_created_revision"] is not False
        or semantic_noop["byte_identical_same_session_second_call"] != "deny"
        or semantic_noop["alpha_equivalent_revision_changed"] != 10
        or semantic_noop["byte_identical_revision_unchanged"] != 10
        or semantic_noop["byte_identical_second_request_denied"] != 10
        or semantic_noop["whitespace_only_revision_changed"] != 10
        or semantic_noop["description_only_revision_changed"] is not True
        or semantic_noop["description_only_statement_changed"] is not False
        or semantic_noop["predecessor_session_rejected_as_stale"] != 21
        or semantic_noop["fresh_successor_allow_then_deny"] != 21
        or semantic_noop["maximum_transition_seconds"] != 15.377992
        or binding_revision["old_binding_session_rejected_as_stale"] != 10
        or binding_revision["successor_binding_session_allowed"] != 10
        or binding_revision["same_mandate_across_revision_aggregate"] != 1200
    ):
        raise ValueError("repeated temporal outcomes do not match the paper experiment")
    if (
        any(len(cell) != 10 for cell in anthropic_cells.values())
        or any(not trial["topology"]["protocol_conformant"] for trial in anthropic_trials)
        or any(trial["idle_reason"] != "budget_reached" for trial in anthropic_trials)
        or any(
            trial["post_budget_refusal"]["api_error_type"] != "invalid_request_error"
            for trial in anthropic_trials
        )
        or sorted(
            trial["list_cost_minor_units"]
            for trial in anthropic_cells["subagent_handoff"]
        )
        != [1] * 4 + [2] * 6
        or sorted(
            trial["list_cost_minor_units"]
            for trial in anthropic_cells["concurrent_subagents_2"]
        )
        != [2] * 9 + [3]
        or [
            trial["list_cost_minor_units"]
            for trial in anthropic_cells["concurrent_subagents_4"]
        ]
        != [4] * 10
        or anthropic["binding"]["managed_platform_verifies_binding"] is not False
    ):
        raise ValueError("Anthropic trial outcomes do not match the paper experiment")
    platform = measurement["environment"]["platform"]
    platform_label = "x86_64 WSL2 Linux" if "WSL2" in platform else platform
    paired_differences = [
        record["bound_minus_unbound_ms"] for record in paired_artifact["records"]
    ]
    if (
        paired_artifact["pairs"] != paired["pairs"]
        or statistics.median(paired_differences)
        != paired["median_bound_minus_unbound_ms"]
    ):
        raise ValueError("paired latency artifact does not match the evidence summary")
    paired_ci_lower, paired_ci_upper = _bootstrap_median_interval(paired_differences)
    macros = {
        "EvidenceCaptureCount": data["capture_count"],
        "EvidenceGraphCount": data["authority_graph_count"],
        "CorrectionTotal": corrections["total_records"],
        "CanonicalCorrectionTotal": corrections["canonical_records"],
        "ComparisonMedianMs": comparison["analysis_wall_clock_ms"],
        "ComparisonRepetitions": f'{measurement["repetitions"]:,}',
        "ComparisonWarmups": measurement["warmups"],
        "ComparisonEnvironment": (
            f'{measurement["environment"]["implementation"]} '
            f'{measurement["environment"]["python"]} on {platform_label}'
        ),
        "SequenceCallAmount": calls[0]["amount"],
        "SequenceAggregateAmount": f'{sequence["aggregate_amount"]:,}',
        "SequenceThreshold": f'{sequence["per_request_threshold"]:,}',
        "TemporalThreshold": f'{temporal["threshold"]:,}',
        "TemporalRequestAmount": temporal["request_amount"],
        "TemporalAttemptedAggregate": f'{temporal["same_session"]["attempted_aggregate"]:,}',
        "TemporalPermittedAggregate": temporal["same_session"]["permitted_aggregate"],
        "TemporalCellTrials": session_cells["same_session_allow_then_deny"],
        "TemporalConcurrentTrials": session_cells["concurrent_exactly_one_allow"],
        "TemporalUpdateTrials": policy_updates["old_session_rejected_as_stale"],
        "TemporalUpdateRecoveryTrials": policy_updates["fresh_recovery_allowed"],
        "TemporalUpdateAggregate": f'{policy_updates["recovery_aggregate_across_revisions"]:,}',
        "SemanticNoopTrials": semantic_noop["alpha_equivalent_revision_changed"],
        "BindingRevisionTrials": binding_revision[
            "old_binding_session_rejected_as_stale"
        ],
        "BindingRevisionAggregate": f'{binding_revision["same_mandate_across_revision_aggregate"]:,}',
        "BindingRepetitionTrials": binding_cells["same_binding_allow_then_deny"],
        "BindingPairedPairs": paired["pairs"],
        "BindingPairedMedianMs": f'{paired["median_bound_minus_unbound_ms"]:.1f}',
        "BindingPairedLowerQuartileMs": f'{paired["q1_bound_minus_unbound_ms"]:.1f}',
        "BindingPairedUpperQuartileMs": f'{paired["q3_bound_minus_unbound_ms"]:.1f}',
        "BindingPairedBootstrapRepetitions": f"{BOOTSTRAP_REPETITIONS:,}",
        "BindingPairedBootstrapLowerMs": f"{paired_ci_lower:.1f}",
        "BindingPairedBootstrapUpperMs": f"{paired_ci_upper:.1f}",
        "AnthropicCellTrials": len(anthropic_cells["subagent_handoff"]),
        "AnthropicFreshPairs": anthropic["single_agent"]["fresh_session_pairs"][
            "both_sessions_reached_cap"
        ],
        "AnthropicHandoffExact": 4,
        "AnthropicHandoffOvershoot": 6,
        "AnthropicTwoChildTwoCent": 9,
        "AnthropicTwoChildThreeCent": 1,
        "AnthropicFourChildFourCent": 10,
    }
    return "\n".join(
        [r"% Generated by make_tables.py. Do not edit."]
        + [_macro(name, value) for name, value in macros.items()]
        + [""]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = _load()
    outputs = ((CAPTURES, _capture_table(data)), (VALUES, _values(data)))
    if args.check:
        stale = [path.name for path, content in outputs if not path.exists() or path.read_text() != content]
        if stale:
            print("FAIL  stale generated evidence: " + ", ".join(stale))
            return 1
        print("PASS  generated evidence matches the vendored summary")
        return 0
    for path, content in outputs:
        path.write_text(content, encoding="utf-8")
    print("wrote table_captures.tex and evidence_values.tex")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
