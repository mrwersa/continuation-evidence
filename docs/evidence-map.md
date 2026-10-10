# Evidence map

Use this index to move from a result to its inputs, recorded responses,
derived output and verifier. Links open the actual files in the repository.
For the limits of each file, see the [manifest](../MANIFEST.md).

## Contents

- [Consolidated evidence and generated values](#consolidated-evidence-and-generated-values)
- [AgentCore policy revisions](#agentcore-policy-revisions)
- [AgentCore principal isolation](#agentcore-principal-isolation)
- [Apigee MCP quotas](#apigee-mcp-quotas)
- [Managed Agents cost accounting](#managed-agents-cost-accounting)
- [Offline models and recovery comparison](#offline-models-and-recovery-comparison)

## Consolidated evidence and generated values

| Purpose | Files |
|---|---|
| Consolidated captures and outcomes | [evidence-summary.json](../evidence-summary.json), [checksum](../evidence-summary.sha256) |
| Generated numerical macros | [evidence_values.tex](../evidence_values.tex) |
| Supporting corpus table, outside the manuscript | [table_captures.tex](../table_captures.tex) |
| Ancillary paired timings, outside the manuscript's claims | [binding-paired-latency.json](../binding-paired-latency.json), [checksum](../binding-paired-latency.sha256) |
| Generator and consistency check | [make_tables.py](../make_tables.py) |

## AgentCore policy revisions

The permit–forbid and single-permit configurations have separate records.
Their comparison does not isolate policy form from validation mode.

### Permit–forbid series

| Purpose | Files |
|---|---|
| Rename-only policy forms | [form A](../revision-policy-a.dogwood), [form B](../revision-policy-b.dogwood) |
| Recorded transition events | [revision-events.json](../revision-events.json) |
| Derived counts | [revision-summary.json](../revision-summary.json) |
| Retained description-only event | [revision-metadata-events.json](../revision-metadata-events.json) |
| Retained threshold-change cell | [revision-threshold-trials.json](../revision-threshold-trials.json) |
| Verified resource removal | [revision-cleanup.json](../revision-cleanup.json) |
| Checksums and verifier | [revision-evidence.sha256](../revision-evidence.sha256), [verify_revision.py](../verify_revision.py) |

The retained description-only and alternating-threshold cells above are
ancillary. The manuscript's repeated description and tightening results come
from the single-permit matrix below.

### Single-permit matrix and configuration comparison

| Purpose | Files |
|---|---|
| Permit–forbid templates | [permit](../continuation-permit.cedar), [forbid A](../continuation-forbid-a.dogwood), [forbid B](../continuation-forbid-b.dogwood), [tightened forbid](../continuation-forbid-a-700.dogwood) |
| Single-permit templates | [base](../continuation-candidate-permit-a.dogwood), [renamed](../continuation-candidate-permit-b.dogwood), [tightened](../continuation-candidate-permit-a-700.dogwood) |
| Fixed matrix design | [revision-validated-protocol.json](../revision-validated-protocol.json) |
| Validation and deployment | [revision-validated-deployment.json](../revision-validated-deployment.json) |
| Matrix events and derived counts | [events](../revision-validated-events.json), [summary](../revision-validated-summary.json) |
| Recorded setup correction | [revision-validated-corrections.json](../revision-validated-corrections.json) |
| Fixed comparison design | [revision-diagnostic-protocol.json](../revision-diagnostic-protocol.json) |
| Comparison events and derived counts | [events](../revision-diagnostic-events.json), [summary](../revision-diagnostic-summary.json) |
| Checksums and verifier | [continuation-evidence.sha256](../continuation-evidence.sha256), [verify_continuation.py](../verify_continuation.py) |

## AgentCore principal isolation

| Purpose | Files |
|---|---|
| Policy inputs | [temporal policy](../isolation-policy.dogwood), [permit](../isolation-permit.cedar) |
| Recorded calls and derived counts | [isolation-events.json](../isolation-events.json), [isolation-summary.json](../isolation-summary.json) |
| Deployment, removal and correction | [deployment](../isolation-deployment.json), [cleanup](../isolation-cleanup.json), [correction](../isolation-corrections.json) |
| Checksums and verifier | [continuation-evidence.sha256](../continuation-evidence.sha256), [verify_continuation.py](../verify_continuation.py) |

## Apigee MCP quotas

All 90 scheduled sequences completed. The record reconciles 250 scheduled tool
calls, 110 deployment diagnostics and five calibration calls.

| Purpose | Files |
|---|---|
| Study design and interpretation | [apigee_README.md](../apigee_README.md) |
| Fixed sequence schedule | [apigee_protocol.json](../apigee_protocol.json) |
| Calls, responses, transport and backend receipts | [apigee_records.json](../apigee_records.json) |
| Policy variants | [apigee_policies.json](../apigee_policies.json) |
| Derived counts and manuscript table | [apigee_summary.json](../apigee_summary.json), [apigee_table.tex](../apigee_table.tex) |
| Checksums | [apigee_evidence.sha256](../apigee_evidence.sha256) |
| Verifier and 16 mutation tests | [verify_apigee.py](../verify_apigee.py), [test_apigee.py](../test_apigee.py) |

## Managed Agents cost accounting

These records concern provider-reported cost, not application authority. Cap
changes and handoff are distinct from the policy revisions tested on AgentCore
and Apigee.

| Purpose | Files |
|---|---|
| Session-budget and multi-agent outcomes | [anthropic-session-budgets.json](../anthropic-session-budgets.json), [checksum](../anthropic-session-budgets.sha256) |
| Fixed cap-change and agent-update design | [anthropic-cap-change-protocol.json](../anthropic-cap-change-protocol.json) |
| Trial records and derived classifications | [trials](../anthropic-cap-change-trials.json), [summary](../anthropic-cap-change-summary.json) |
| Recorded classification correction | [anthropic-cap-change-corrections.json](../anthropic-cap-change-corrections.json) |
| Checksums | [continuation-evidence.sha256](../continuation-evidence.sha256) |
| Verifiers | [make_tables.py](../make_tables.py), [verify_continuation.py](../verify_continuation.py) |

## Offline models and recovery comparison

The local scalar model and the retained-account coordinator are different
implementations. The first exposes local handover limitations. The second
checks coordinated ownership inside one trusted process.

| Purpose | Files |
|---|---|
| Local scalar model | [continuation_model.py](../continuation_model.py) |
| Scalar inclusion, recipient sets and local model limitations | [test_scope.py](../test_scope.py) |
| Retained-account coordinator | [coordinator_model.py](../coordinator_model.py) |
| 17 handover, reservation and settlement tests | [test_coordinator.py](../test_coordinator.py) |
| Refuse, fresh-recovery and carry comparison | [compare_recovery.py](../compare_recovery.py), [coordinator_table.tex](../coordinator_table.tex) |
| Implementation assumptions | [Coordinator guide](guide.md#separate-single-process-coordinator) |

[Back to the README](../README.md)
