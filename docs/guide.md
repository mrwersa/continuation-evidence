# Evidence and verification guide

This guide explains the evidence, verification commands and interpretation
boundaries for *A Session Is Not a Mandate*. Start with the
[repository README](../README.md) for the quick start, or use the
[evidence map](evidence-map.md) to find a particular record.

## Contents

- [Vocabulary](#vocabulary)
- [What this artifact supports](#what-this-artifact-supports)
- [File organisation](#file-organisation)
- [Reproducing the paper's numbers](#reproducing-the-papers-numbers)
  - [Single-process coordinator](#separate-single-process-coordinator)
- [What the evidence summary contains](#what-the-evidence-summary-contains)
  - [Apigee MCP records](#apigee-mcp-records)
  - [Gateway and Managed Agents records](#gateway-and-managed-agents-records)
- [Sanitisation](#sanitisation)
- [Cloud resources](#cloud-resources)
- [Artifact boundary](#artifact-boundary)

## Vocabulary

The paper uses a few terms more narrowly than everyday product documentation:

- A **cumulative constraint** decides a request from the aggregate of earlier
  qualifying actions, not from that request alone.
- **Consumed state** is the runtime record of that aggregate so far.
- A **mandate** is one reviewed, bounded unit of agent work. It is not assumed
  to be the same thing as a provider session.
- An **enforcement system** applies or accounts for a cumulative constraint. A
  **provider-operated enforcement system** is one run outside the application
  team's control.
- The **policy decision point** is the component within that system that
  returns the managed allow or refuse decision. The **runtime** executes the
  agent loop and its tool calls.
- A **policy revision** is a distinct deployed version of a policy. The Gateway
  experiment tests which writes create one. Apigee explicitly imports and
  promotes revisions, so its identical-import arm tests continuity rather than
  write deduplication.
- The **permit–forbid policy** and **single-permit policy** are the two
  configurations in the revision experiment. The first has separate permit and
  temporal-forbid rules and runs under `IGNORE_ALL_FINDINGS` because native
  validation rejects it. The second keeps the total below the threshold inside
  one permit rule and passes `FAIL_ON_ANY_FINDINGS`.
- **Safe continuation** is the property the paper states and tests: across a
  non-widening administrative revision, where the successor admits a request
  from a given history only if the predecessor would, the successor must not
  admit work the predecessor state would have refused, unless the issuer amends
  the mandate. Equivalent policies and a tightened threshold are the cases the
  central experiment tests. It is a property of authority, not of session
  storage.

## What this artifact supports

Two kinds of claim, and the distinction matters when deciding what can be
re-run.

**Reproducible without cloud access.** Every generated numeric macro cited by
the paper is derived from committed evidence by scripts in this bundle, and
every revision and cap-change count in the paper is derived from released
per-trial records. A reviewer can regenerate the macros and summaries, then
compare them against the committed copies. Numeric macros and the recovery
and Apigee tables are generated. The remaining prose and layout are authored.

**Not reproducible without cloud access and cost.** The live captures ran
against three provider-operated enforcement systems. Reproducing them requires
provider accounts, incurs charges, and creates and destroys real resources. The
consolidated summary preserves sanitised outcomes and trial counts. The
Managed Agents multiagent and cap-change trials are included at full
resolution. Its sequential, fresh-session and cap-raise cells are retained as
aggregate counts rather than per-trial records. The paired latency record is
retained as ancillary evidence outside the manuscript's present claim set.
The Apigee projection retains every tool attempt and all 90 completed sequences
from 10 October.

The artifact therefore separates offline-verifiable claims from live recapture.
It does not describe a billable deployment as cost-free reproducibility.

## File organisation

```
repository root/
  README.md               quick start and navigation
  MANIFEST.md             what each committed file establishes
  evidence-summary.json   consolidated captures, corrections, live outcomes
  evidence-summary.sha256 digest of the above as vendored into the paper
  binding-paired-latency.json   ancillary sanitised paired timing vector
  binding-paired-latency.sha256 digest of the paired timing vector
  anthropic-session-budgets.json  sanitised second-provider trial records
  anthropic-session-budgets.sha256 digest of those records

  # revision experiment, permit–forbid policy
  revision-policy-a.dogwood  first rename-only temporal policy form
  revision-policy-b.dogwood  second rename-only temporal policy form
  revision-events.json    sanitised events for the byte-identical, renaming and whitespace arms
  revision-metadata-events.json  sanitised single description-only event
  revision-summary.json   canonical projection and computed counts from those events
  revision-cleanup.json   direct not-found checks after resource removal
  revision-threshold-trials.json  per-trial outcomes for an alternating 1,000/1,001 threshold cell
  revision-evidence.sha256  digests for the files above

  # revision experiment, single-permit policy and configuration comparison
  continuation-permit.cedar, continuation-forbid-{a,b,a-700}.dogwood
                          the permit–forbid policy templates
  continuation-candidate-permit-{a,b,a-700}.dogwood
                          the single-permit policy templates
  revision-validated-protocol.json  protocol fixed before the randomised matrix
  revision-validated-deployment.json  validation attempts, deployment shape, cleanup
  revision-validated-events.json  sanitised events for all 60 matrix trials and controls
  revision-validated-summary.json  per-arm counts derived from those events
  revision-validated-corrections.json  a deployment attempt aborted before any scored trial
  revision-diagnostic-protocol.json  protocol fixed before the configuration comparison
  revision-diagnostic-events.json  sanitised events for its three ten-trial blocks
  revision-diagnostic-summary.json  per-configuration counts derived from those events

  # second provider, cap change and agent update
  anthropic-cap-change-protocol.json  protocol fixed before the randomised cells
  anthropic-cap-change-trials.json  sanitised records for all 30 trials
  anthropic-cap-change-summary.json  per-cell classifications derived from those records
  anthropic-cap-change-corrections.json  a classification correction made before analysis

  # Apigee MCP quota continuity
  apigee_README.md         design, collection and sanitisation rules
  apigee_protocol.json     all 90 planned sequences and their fixed order
  apigee_records.json      attempts, responses, transport and backend receipts
  apigee_policies.json     quota variants with deployment placeholders
  apigee_summary.json      generated counts and per-sequence observations
  apigee_table.tex         generated manuscript table
  apigee_evidence.sha256   digests of the five data and output files
  verify_apigee.py         record reconciliation and table regeneration
  test_apigee.py           mutation tests for the verifier

  # principal isolation control
  isolation-policy.dogwood, isolation-permit.cedar  the control's policy templates
  isolation-events.json   sanitised calls for 20 trials and four single-request controls
  isolation-summary.json  counts derived from those events
  isolation-deployment.json, isolation-cleanup.json, isolation-corrections.json
                          deployment shape, verified teardown and one classified correction
  continuation-evidence.sha256  digests for the files above

  verify_revision.py      checks the permit–forbid policy and recomputes its counts
  verify_continuation.py  recomputes the validated, comparison, cap-change and isolation counts
  continuation_model.py   sequential scalar fixture, not a coordinated handover implementation
  test_scope.py           offline policy examples and reproduced fixture limitations
  coordinator_model.py    separate single-process coordinator with retained accounting
  test_coordinator.py     handover, reservation and recovery comparison tests
  compare_recovery.py     independent offline probes of three recovery strategies
  coordinator_table.tex   manuscript table checked against those probes
  make_tables.py          regenerates supporting tables and numeric macros
  table_captures.tex      supporting corpus table, not used by the manuscript
  evidence_values.tex     generated value macros checked byte-for-byte
  docs/                  reading guides and a clickable evidence map
```

## Reproducing the paper's numbers

Run these commands from the repository root, not from `docs/`. They use only
the Python standard library, without network access or credentials.

```
python3 make_tables.py --check
python3 verify_revision.py
python3 verify_continuation.py
python3 continuation_model.py
python3 -m unittest discover -s . -p 'test_scope.py' -v
python3 -m unittest discover -s . -p 'test_coordinator.py' -v
python3 compare_recovery.py --check
python3 verify_apigee.py
python3 -m unittest test_apigee -v
```

The first command regenerates the supporting capture table and the value macros
from `evidence-summary.json`, independently recomputes the paired timing
statistics from `binding-paired-latency.json`, and fails if the committed copies
or the two records differ. A pass establishes that every generated numeric macro
used by the manuscript follows mechanically from the committed evidence. The
capture table and paired timing statistics are retained checks over the wider
evidence record; the manuscript does not cite them.

The second command checks the permit–forbid policy. It verifies that every submitted statement
update equals its expected temporal-policy form, that the two named forms differ
only by consistent renaming of their three bound variables, and that the
byte-identical, renaming and whitespace-only arms reproduce the canonical and
consolidated counts. It also requires canonical microsecond UTC timestamps,
causal call, update and poll order, the captured byte/rename interleaving, and
the overall capture bounds. Each revision-producing sequence must complete
inside the one-hour policy window. The same command checks two retained records
that the manuscript does not cite: a single description-only event and an
alternating 1,000/1,001 threshold cell. The manuscript's description and
threshold results come from the single-permit policy, where each arm has 10 trials
with full response bodies and clock readings.

The third command checks the rest of the revision experiment and the second
provider's cap-change cells. For the single-permit policy it:

- reproduces the 60-trial order from the protocol's random seed;
- checks every policy template against its preregistered digest and every
  recorded statement digest against the template text;
- derives each call outcome from the managed response body rather than the
  recorded label, and each revision change from the revision aliases;
- requires the base state, the preflight and postflight controls, and a fresh
  successor session in every arm that runs one; and
- reproduces the per-arm summary, including the tightening arm's separation of
  carried from fresh accounting.

For the configuration comparison it reproduces the block order from its seed,
checks each block against its preregistered configuration, and derives the
per-configuration revision and refusal counts. Combined with the permit–forbid policy's events,
it confirms that all 90 writes that created a revision made the predecessor
session stale and all 30 that did not left its refusal in place. For the second
provider it reproduces the trial order and re-derives every classification from
the recorded costs, caps, versions and refusals. For the isolation control it
re-derives the same-principal and changed-principal counts, the direction split
and the per-principal single-request controls, and requires the session
identifier to stay fixed while the principal changes.

Causal order in the revision and cap-change records uses the recorded monotonic
clock. The capture host's wall clock stepped backwards by fractions of a second
inside a few calls, so UTC readings are retained as observed and checked for
canonical form only. The isolation control predates that practice and keeps wall
clock stamps and measured durations rather than a monotonic clock. One of its
twenty trials shows the same backwards step, of 0.128 seconds, between two
calls. Its outcomes do not depend on call ordering, so the verifier checks
stamp format and positive durations there rather than causal order.

The fourth command runs the sequential scalar fixture. It demonstrates local
checks: a declared in-flight mandate waits for a carry, a carried total and
reservations constrain admissions, the same nonce is refused on replay within
one instance, a closed predecessor refuses admissions, and widening needs an
issuer amendment. The tampered-summary case tests signature rejection, not the
completeness of an honestly signed summary. An HMAC substitutes for the issuer
signature. The fixture uses an inclusive limit, unlike the live strict threshold.

It does not implement coordinated handover. Two successor instances can each
accept the same record. A closed predecessor can issue a fresh nonce whose old
total overwrites later successor consumption. The fifth command reproduces
these two limits and checks the manuscript's recipient-set example and a bounded
enumeration of its scalar sufficient condition. Passing these tests records
the limits, not compliance with the full interface. No command calls a provider.

In the single-permit matrix and configuration comparison, the capture obtains
the operational revision marker from `GetPolicy.updatedAt` before an update and
after `ACTIVE`. Equal values receive equal `revision_alias` values. This is
update metadata, not a dedicated revision identifier. The verifiers compare
those aliases independently of the later stale-session response. Sanitised
records alone cannot establish the provenance of the underlying native values.

### Separate single-process coordinator

`coordinator_model.py` is an offline design illustration, separate from the
live experiments and the sequential `continuation_model.py`. One shared lock
serialises admissions, ownership changes and settlement. Accounts cannot be
reopened. Closing an owner prevents further admissions and creates one pending
handover ticket. Acceptance changes the owner and generation while retaining
the same consumed total and operation records. A ticket references that state
instead of importing a consumption snapshot. A fresh nonce, another successor
or an earlier generation cannot overwrite the account. The holder name may stay
the same across handover. Its incremented generation invalidates the old lease.
The manuscript also specifies a copied-summary alternative with operation-level
settlement routing. Only the retained-account path is implemented here.

Admission reserves a positive integer amount before work starts. The strict
check includes consumed and reserved amounts. Trusted completion transfers
exactly the reserved amount to consumption once. It may arrive while handover
is pending or after a successor has taken over. Duplicate settlement leaves
the account unchanged. Operation identifiers remain occupied after settlement.

The model assumes one trusted coordinator, a stable account identifier, trusted
initial grants and completion reports, fixed event units and window, and complete
mediation. Leases are ownership identifiers, not cryptographic credentials. It
does not implement authentication, crash persistence, distributed consensus,
variable actual costs, expiry, cancellation, compensation, policy translation or
issuer amendments. Widening is refused. Credential renewal is not modelled.
It must not be presented as production middleware or general conformance proof.

The 17 tests include three competing-thread checks and all 12 orderings of
close, accept, a late reservation and settlement in which close precedes accept.
These are bounded checks, not exhaustive concurrency verification. The scope
tests expose the sequential fixture's limits separately. No coordinator test
is an expected failure.

`compare_recovery.py` prints the two probes for each strategy as JSON and checks
the manuscript table with `--check`. Every probe begins independently with 600
consumed under a strict 1,000 threshold. Refusal keeps the original account
closed. Fresh recovery deliberately assigns a new empty account to the same
logical mandate, as a negative control. Carry transfers ownership of the
original account. Thus refusal denies both 300 and 600, fresh recovery admits
both, and carry admits 300 but denies 600. All three rows are offline. The table
does not claim that these exact probes were run on either provider.

To see the regenerated output rather than only the comparison:

```
python3 make_tables.py
```

## What the evidence summary contains

### Apigee MCP records

The independent quota path retained consumption across all 20 tightenings
to 700, ten tightenings to 500 and twenty identical or whitespace imports.
All ten policy-name changes selected a separate total under the same
task key, admitting 1,100 across an unchanged 1,000 limit. This matches documented
counter scope rather than establishing an undocumented defect.

All 90 planned sequences completed on 10 October. `verify_apigee.py` reconciles
365 tool responses with remote attempts, independently exported transport and
backend records, checks policy variants, calibration and the recorded order,
and regenerates the per-arm counts.

The 16 tests check rejection of damaged, missing or falsely completed records.
See [apigee_README.md](../apigee_README.md) for the design and projection rules.
All sequences share one runtime and collection period, so counts are not
a reliability estimate.

### Gateway and Managed Agents records

One record per capture, with the upstream project, the pinned version or commit,
the enforcement pattern it exemplifies, and whether it yields an analysable
authority graph. One record per classified review correction. For the live work, the
policy revisions, request values, managed decisions, trial counts and timing
samples. The separate session-budget record retains all thirty second-provider
multiagent outcomes.

The permit–forbid policy's revision record is also released at event resolution beside the two
exact policy forms. It is a sanitised reviewed projection of the managed run,
not a claim that the live service can be replayed offline. It retains each call,
submitted `UpdatePolicy` body, managed update response, ACTIVE status poll,
revision-change result, stale-session diagnostic and two successor outcomes. A
separate canonical summary is mechanically derived from those events.

The single-permit and comparison records have the same event resolution, plus
monotonic clock readings, the submitted description, reset updates that restore
the base state, and the controls run before and after each block. Their
protocols record predictions, trial counts, seeds and stop rules. A protocol's
status field is frozen at registration, so it reads as not yet executed.

[MANIFEST.md](../MANIFEST.md) states, for each part, what it establishes and what it does not.

## Sanitisation

Live captures were sanitised before commit. Account identifiers, credentials,
resource names, trace identifiers and gateway endpoints were removed. Decision
fields were not altered. Where a denial message embedded a generated policy
identifier or resource, it was replaced by a reviewed alias and the replacement
recorded rather than silently applied. Policy templates carry a reviewed
placeholder in place of the live gateway identifier.

No credential, key, token or account number appears anywhere in this bundle. The
capture tooling asserts this before writing, and the assertion is part of the
committed test suite in the analysis repository.

## Cloud resources

Every live capture created short-lived resources and removed them afterwards.
For the gateway captures, removal was verified by querying each resource type
and confirming an empty result rather than assuming the delete call succeeded.
For the managed-agent captures, every session deletion was followed by a typed
not-found response; agents were archived and the environment deletion was
acknowledged by the service. A reusable bootstrap stack was left in place and
is noted in the gateway capture records.

## Artifact boundary

The source analysis implementation and live capture harnesses are not included.
The bundle instead contains the exact released inputs, sanitised managed events,
derived summaries and offline checks. These checks establish internal
consistency, not the provenance or completeness of the sanitised projections.
The analysis implementation and capture harnesses are not part of this release.

Managed Agents exposes a managed cost cap rather than the Gateway's
policy language. It replicates the session boundary, measures child-thread
fanout and carries consumed cost across a lowered cap, but has no counterpart to
the policy-revision transition because a live session keeps its saved agent
version.

For the paper's citation, see [the repository README](../README.md#citation).
