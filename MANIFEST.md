# Manifest

What each committed file establishes, and what it does not.

| File | Establishes | Does not establish |
|---|---|---|
| `evidence-summary.json` | The captures, their pinned versions, classified review corrections, and the retained live outcomes and timings | That every retained measurement is used by the manuscript, or that the analysis producing them is correct |
| `evidence-summary.sha256` | That the copy vendored into the paper is the copy published here | Anything about how the summary was produced upstream |
| `binding-paired-latency.json` | Ancillary randomised raw timings for all 30 matched pairs | A manuscript claim, population-level estimate or causal isolation of adapter overhead |
| `binding-paired-latency.sha256` | That the paired timing vector is byte-exact | That the enforcement system would reproduce the same timings |
| `anthropic-session-budgets.json` | Sanitised session-budget outcomes, topology checks, costs, stop reasons and refusal types, including the fanout cells | That every cell is used by the manuscript, that cost is equivalent to application authority, or that in-flight overshoot violates a provider promise |
| `anthropic-session-budgets.sha256` | That the second-provider trial record is byte-exact | That another model, prompt or cap would reproduce the distribution |
| `revision-policy-a.dogwood` and `revision-policy-b.dogwood` | The exact sanitised temporal policy forms submitted to the permit–forbid policy | Equivalence across any other policy forms or the whole language |
| `revision-events.json` | Every sanitised call, statement update, managed response, UTC timestamp, status poll and outcome in the permit–forbid policy's byte-identical, renaming and whitespace-only arms | The unsanitised provider responses or future service behaviour |
| `revision-metadata-events.json` | A single description-only update to the permit–forbid policy, with unchanged statement digest and resulting stale, Allow, Deny sequence | A repeated rate; the manuscript's description-only result comes from the single-permit policy |
| `revision-summary.json` | The canonical row-by-row projection and computed counts derived from the permit–forbid policy's transition events | A causal interpretation beyond the observed transition |
| `revision-cleanup.json` | Direct not-found or empty results for every task-scoped resource type after cleanup | The absence of unrelated resources in the provider account |
| `revision-threshold-trials.json` | Each trial of an alternating 1,000/1,001 threshold cell: direction, no-update control, stale-session rejection, recovery outcome and activation latency | Call timestamps, native request and response bodies, or a manuscript claim; the manuscript's threshold result comes from the single-permit policy's tightening arm |
| `revision-evidence.sha256` | That the permit–forbid policy's forms, event records, canonical summary, cleanup record and threshold trials are byte-exact | That the live service would reproduce them |
| `continuation-permit.cedar` and `continuation-forbid-{a,b,a-700}.dogwood` | The permit–forbid policy templates as registered, with a reviewed gateway placeholder | That the live deployment used no other policy |
| `continuation-candidate-permit-{a,b,a-700}.dogwood` | The single-permit policy's base, renamed and tightened templates as registered | Equivalence to the permit–forbid policy beyond the tested controls |
| `revision-validated-protocol.json` | The arms, templates and their digests, descriptions, trial count, seed, polling rule, validation order and outcome wording fixed before the matrix ran | That the protocol anticipated every outcome; its byte-identical prediction was not met |
| `revision-validated-deployment.json` | That the permit–forbid policy failed `FAIL_ON_ANY_FINDINGS` as overly permissive, the single-permit policy passed for every variant, the gateway ran in `ENFORCE`, and cleanup verified every resource absent | The unsanitised validation findings or account state |
| `revision-validated-events.json` | Every sanitised call, update, reset, status poll, response body and UTC and monotonic clock reading in the 60 matrix trials, plus preflight and postflight controls | Future service behaviour or behaviour under other policy forms |
| `revision-validated-summary.json` | Per-arm revision, staleness, successor and tightening counts derived from those events | A causal interpretation beyond the observed transitions |
| `revision-validated-corrections.json` | That a first deployment attempt stopped on a malformed description parameter before any scored trial and was cleaned up | That no other undetected harness defect existed |
| `revision-diagnostic-protocol.json` | The three configurations, seed, controls and outcome wording fixed before the configuration comparison ran | A separation of policy form from validation mode, which the protocol states it cannot provide |
| `revision-diagnostic-events.json` | Every sanitised call, update, status poll, response body and clock reading in the three comparison blocks, with their controls | Behaviour under a strictly validated permit–forbid policy, which the service rejects |
| `revision-diagnostic-summary.json` | Per-configuration revision and refusal counts derived from those events | Which of policy form or validation mode causes deduplication |
| `anthropic-cap-change-protocol.json` | The cells, classification margins, seed, pilot rule, spend ceiling and a pre-execution amendment to the work-unit bound | That the margins hold for another model or prompt |
| `anthropic-cap-change-trials.json` | Every trial's work units with costs and idle reasons, the cap or agent update and its echo, versions, refusals and final cost, plus pilot and cleanup records | Provider-internal accounting or cost as application authority |
| `anthropic-cap-change-summary.json` | Per-cell classifications derived from those trials | A provider promise about carry or version pinning |
| `anthropic-cap-change-corrections.json` | That the capture-time refusal label was corrected before analysis because the service quotes the field name | That no other labelling defect existed; the verifier re-derives every refusal from its message |
| `isolation-events.json` | Every sanitised call, outcome, principal alias, session alias and duration in the 20 isolation trials and their four single-request controls | The provider's internal keying, or behaviour for identities beyond the two tested |
| `isolation-summary.json` | Same-principal and changed-principal counts, the direction split and the per-principal controls derived from those events | That cumulative history is isolated for every identity type |
| `isolation-policy.dogwood`, `isolation-permit.cedar`, `isolation-deployment.json`, `isolation-cleanup.json` and `isolation-corrections.json` | The control's policy templates, deployment shape, verified teardown and one classified correction | The unsanitised account state |
| `continuation-evidence.sha256` | That the validated, comparison, cap-change and isolation files and all templates are byte-exact | That the live services would reproduce them |
| `verify_revision.py` | That the permit–forbid policy's submitted statements match the released forms, named forms differ only by consistent bound-variable renaming, timestamps are canonical and causally ordered, the captured arm schedule and bounds hold, each transition stays within the tested window, every released cell reproduces the published counts, and the retained threshold trials reproduce their consolidated counts | A native policy-language semantic analysis or a replay of the live service |
| `verify_continuation.py` | That the validated matrix, comparison and cap-change trials follow their seeded order and registered configurations, templates match their digests, outcomes follow from response bodies, monotonic order and the one-hour window hold, every summary reproduces, and staleness follows revision creation across both configurations | Provenance of the sanitised projections or a replay of the live services |
| `continuation_model.py` | Sequential local checks for carried totals, reserved work, replay of one nonce within one instance, closed-predecessor admissions, signature tampering and widening | Shared successor ownership, stale imports with fresh nonces, completeness of an honestly signed summary, concurrent admission or settlement, a deployment, or live service behaviour |
| `test_scope.py` | Bounded scalar inclusion checks, recipient-set examples, and reproduction of duplicate successor allowance and stale-total overwrite | A general policy-equivalence solver, a corrected coordinator, or empirical provider results |
| `coordinator_model.py` | Single-process retained accounting with one active owner, strict scalar admissions, reservations and idempotent settlement under a shared lock | Authentication, persistence, distributed enforcement, variable settlement amounts, renewal, general policy translation or provider behaviour |
| `test_coordinator.py` | Seventeen passing tests including stale tickets, competing owners, reservations and completions, settlement across handover, 12 bounded event orderings, and recovery probes | Exhaustive interleaving verification or a deployment |
| `compare_recovery.py` and `coordinator_table.tex` | The three-strategy table reproduces two independently initialised offline probes per strategy | Additional live experiments or general availability guarantees |
| `make_tables.py` | That the supporting capture table and numeric macros regenerate from the committed records | That all generated outputs are used by the manuscript or that the summary itself is complete |
| `table_captures.tex` | A byte-exact generated view of the wider capture corpus | A manuscript table; the current manuscript does not include it |
| `evidence_values.tex` | The byte-exact generated numerical macros, of which the manuscript cites a checked subset | That every retained macro supports a manuscript claim |
| `apigee_protocol.json` | Complete planned sequence order, amounts, attached controls, window and stop rule | Completion of all planned work or independent collection periods |
| `apigee_records.json` | All selected request and response fields, remote attempts, independently exported transport, backend receipts, readiness observations and 90 completed statuses | Original wire bytes or independent authentication of provider provenance |
| `apigee_policies.json` | Policy variants with uniform deployment-only placeholders | Original project, host or network identities |
| `apigee_summary.json`, `apigee_table.tex` and `apigee_evidence.sha256` | Recomputed counts, per-arm table and byte-exact projection | A population failure rate, causal equivalence to Gateway recovery or undocumented provider defect |
| `verify_apigee.py` and `test_apigee.py` | Reconciliation of all records, declared policy differences, calibration, limits, observed readiness, sequence order and 16 offline tests, including transport matching | A live replay, capture completeness beyond the projection or trusted task-key binding |
| `apigee_README.md` | Design, collection, interpretation and explicit sanitisation rules | Population prevalence, distributed coordination or independent provider provenance |

## Reading the live records

Live outcomes are recorded as counts over repeated trials rather than as single
observations. A cell reading ten of ten means the outcome held in every trial,
not that it must hold. External systems vary, and the sample sizes here are
small enough that a reader should treat each as an existence result with a
consistency count attached.

Timing samples remain as an ancillary raw vector, so their deterministic
summary can be recomputed rather than trusted. The current manuscript makes no
latency claim from that vector.

The second-provider records retain every multiagent and cap-change trial rather
than only aggregate counts. Child counts, parentage, event-backed overlap, final
cost, cap updates, agent versions and native budget refusal can therefore be
recomputed independently. The current manuscript uses the sequential,
fresh-session, cap-raise, cap-change, agent-update, one-child and fanout cells.

## Writing tools not included

The manuscript's prose checker is a writing tool, not evidence, so it is not
included.

## Identifying content

This bundle was reviewed for credentials and deployment identifiers before
publication. It contains no account identifier, internal hostname, resource
name or credential.
Third-party systems that were captured are named, because the capture protocol
requires pinned upstream sources and those projects are public.
