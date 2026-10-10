# Apigee MCP accounting continuity

This component contains sanitised evidence from a complete collection on
10 October 2026, through Apigee's native MCP parser and synchronous distributed
quota. The quota weights each refund invocation by its requested amount.
The backend records receipts and has no financial side effect or quota logic.

## Reproduce offline

```sh
python3 verify_apigee.py
python3 -m unittest test_apigee -v
```

Both commands use the Python standard library, without credentials or network
access. `verify_apigee.py --write` regenerates the summary, table and checksums
from the supplied records. A normal check changes no file.

The verifier matches each client reservation to a remote attempt and response,
compares the client and remote response fields, checks each admitted call's
backend receipt, and requires every quota refusal to lack backend dispatch.
It checks observed readiness before tool traffic, one quota expiry, stable
keys within sequences, distinct keys between sequences, probe amounts and the
recorded statuses. It also matches the independently exported transport
responses. Policy comparisons permit only the declared changes.
These checks establish consistency of this projection, not independent
authentication of provider provenance.

## Design and observations

The fixed schedule contains 90 sequences in two execution blocks, with seed
20261009. It includes 20 tightenings to 700 and ten sequences in each other
arm. Five fresh-700 controls per block follow predetermined tightening parents
and use another key under the same deployment. They are not additional revision
trials. The two blocks are not independent collection periods.

The primary arm preloads 600 under 1,000, promotes a 700 revision, then requests
50 and 100. Other probes are recorded in `apigee_protocol.json`. Policy-name
changes have no preselected conformance outcome. No-update controls wait
120 seconds after preload. Every promotion requires management readiness and
a diagnostic on a distinct key. Diagnostics under 1,000 request 1, under 700
request 800, and under 500 request 600. Initialisation and discovery are separate
from tool calls. Calibration probes 600, 600, 300 on one key and 1,000, 1 on
another. The observed equality boundary is inclusive.

## Collection, 10 October

All 90 planned sequences completed. The capture contains 365 tool calls:
250 scheduled calls, 110 deployment diagnostics and five calibration calls.
There are 367 responses including initialisation and discovery, 263 admitted
tool calls and 102 quota refusals. The backend has 265 records including the
two non-tool requests. None of the 102 refusals reached the backend. The
60 focal updates and the baseline and restorations together required 110
promotions, all observed ready. A further setup-only import was undeployed.

All 20 tightenings to 700 retained the 600 preload, admitted 50 and refused
100, reporting 650 used after both probes. All ten tightenings to 500 refused
1 and 50, retaining 600 used. The ten identical imports and ten whitespace
imports retained consumption. All ten policy-name changes admitted 300 and
200 after the initial 600, reporting 300 then 500 used. Thus 1,100 units
were admitted across an unchanged 1,000 limit. Fresh-key and no-update
controls produced their planned patterns in all ten sequences each.

Each task, calibration and diagnostic key had a new execution prefix,
validated before dispatch. The client refreshed management credentials from
their reported expiry. No tool call or uncertain mutation was replayed.
Allocation, scientific and transport audits, resource deletion and removal
of the temporary cloud SSH key were verified privately before projection.
The two blocks are not independent periods.

## Interpretation

The policy-name intervention changes documented accounting scope, not the
limit. The counter values show which total governed admission, not deletion
of the old counter. This is separate from cosmetic-update conformance and
does not identify an undocumented provider defect.

The client supplies task keys. Trusted binding of those keys to mandates is an
assumption, and fresh-key controls do not demonstrate an adversarial bypass.
All observations share one runtime and collection period. No binomial
reliability bound or provider-comparison significance test is claimed.

## Files and projection rules

- `apigee_protocol.json`: planned arms, complete fixed order, request amounts,
  attached controls, limits, window, pause and stop rule.
- `apigee_records.json`: all reservations and selected client and remote
  response fields, transport observations, all backend receipts, sequence
  statuses, import and promotion records and deployment observations.
- `apigee_policies.json`: all policy variants, with deployment-only names and
  the backend address replaced by placeholders.
- `apigee_summary.json` and `apigee_table.tex`: generated observations and
  per-arm counts. The table generator rejects an arm with a missing sequence.
- `apigee_evidence.sha256`: checksums of those five files.
- `test_apigee.py`: checks that missing and duplicate records, altered receipts,
  unobserved revisions, altered transport and falsely completed sequences
  are rejected. All 16 tests run offline.

Projection uses an explicit field allowlist. Request IDs and task keys receive
consistent ordinal aliases across client, remote and backend records. Native
revision numbers, dates, amounts, counter values, expiry, decisions, error codes
and chronological order remain unchanged. HTTP response bodies are parsed to
retain result presence, error status and receipt fields. Unused body fields and
headers are omitted, so this is not a release of original wire bytes.

Account and project identifiers, hostnames, internal IP addresses, credentials,
cloud resource inventories, local paths, source-repository identifiers and
commit metadata are omitted. Backend addresses become `backend.invalid`, the
proxy name becomes `study-proxy`, and its base path becomes `study-mcp`.
The quota policy names are retained because their difference is the treatment.
Those replacements are uniform across every variant. The `smoke` prefixes in
policy variables are literal fixture names, not separate observations or an
extra evidence set. The capture and teardown were checked privately against
the original records. Live recapture requires accounts, provisioning and cost.
