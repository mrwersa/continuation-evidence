# Live capture harnesses

These are the programs that created cloud resources, sent the scheduled tool
calls and recorded provider responses for the paper. They are released so that
the deployments, request construction, readiness checks and capture can be
inspected and rerun. They are not needed for the offline checks at the
repository root.

**Running any of them creates billable resources in your own cloud or API
account.** Raw output contains live account, resource, request and session
identifiers. Keep it private and project it before sharing, as the released
evidence was.

## Contents

- [Coverage](#coverage)
- [Provenance](#provenance)
- [AgentCore](#agentcore)
- [Managed Agents](#managed-agents)
- [Apigee](#apigee)
- [Offline integrity check](#offline-integrity-check)

## Coverage

| Paper result | Live harness | Projection to released evidence |
|---|---|---|
| AgentCore single-permit matrix (`revision-validated-*`) | [agentcore/capture_continuation_live.py](agentcore/capture_continuation_live.py) | [agentcore/project_continuation.py](agentcore/project_continuation.py) |
| AgentCore configuration comparison (`revision-diagnostic-*`) | the same program with `--diagnostic` | the same projector with `--diagnostic` |
| Issuer-signed mandate binding | [agentcore/mandate_binding.py](agentcore/mandate_binding.py) and [agentcore/measure_binding_live.py](agentcore/measure_binding_live.py) | not applicable |
| Managed Agents session-budget and multi-agent cells | [managed-agents/capture.py](managed-agents/capture.py) | [sanitize_confirmation.py](managed-agents/sanitize_confirmation.py), [sanitize_multiagent.py](managed-agents/sanitize_multiagent.py) |
| Managed Agents cap-change and agent-update cells | [managed-agents/capture_continuation.py](managed-agents/capture_continuation.py) | [managed-agents/project_continuation.py](managed-agents/project_continuation.py) |
| Apigee complete execution, 90 sequences | [apigee/gcp_mcp_verified/supervise.py](apigee/gcp_mcp_verified/supervise.py) | allowlist projection described in [apigee_README.md](../apigee_README.md) |

Two AgentCore record sets have no released live driver: the permit–forbid
series (`revision-events.json` and its retained cells) and the principal
isolation control (`isolation-*`). They were collected with one-off operator
scripts that were not retained. Their sanitised records, verifiers and policy
inputs are at the repository root, and the paper's repeated description and
tightening results come from the single-permit matrix above.

## Provenance

[PROVENANCE.json](PROVENANCE.json) lists every file with its source repository,
commit, path and SHA-256 before and after release.

- **AgentCore and Managed Agents** come unchanged from
  [`mrwersa/agentmandate`](https://github.com/mrwersa/agentmandate) at commit
  `11d323302af1412eb83c07f498ff97b6db4946a8`, where they are also public.
- **Apigee** comes from the frozen source commit of the complete execution in
  the author's private study repository. One substitution was made: the
  author's Google Cloud project identifier is replaced by `your-gcp-project`.
  Because the runner pins its dependencies by hash,
  `gcp_mcp_verified/dependencies.json` is re-pinned to the released bytes. The
  original hashes remain in `PROVENANCE.json`. The private protocol narrative
  is replaced by a short `gcp_mcp_verified/PROTOCOL.md` for your own run. The
  design itself is in `gcp_mcp_study/schedule.json`.

The protocol and policy files these programs read are byte-identical to the
released copies at the root. [check_harness.py](check_harness.py) verifies this.

## AgentCore

Python 3.12, `boto3` and AWS credentials for an account you control, in
`us-east-1`. The program creates the IAM roles, Lambda target, policy engine,
Gateway and policies it needs, runs the fixed design in
`continuation-protocol.json`, and deletes and verifies the removal of every
resource it created.

```sh
cd harness/agentcore
python3 capture_continuation_live.py --output /path/to/private/run
python3 capture_continuation_live.py --diagnostic --output /path/to/private/diagnostic
python3 project_continuation.py --help
```

`measure_binding_live.py` measures the binding adapter through an existing
Gateway. It takes the Gateway URL, tool name and binding module as arguments.
Pinned versions are in `requirements-binding-latency.txt`.

## Managed Agents

Python 3.12 and the pinned `anthropic` client in `requirements-capture.txt`.
Set `ANTHROPIC_API_KEY`. The programs create agents, an environment and
sessions under the caps in `protocol.json`, `multiagent-protocol.json` and
`continuation-protocol.json`, then delete or archive them.

```sh
cd harness/managed-agents
python3 capture.py --help
python3 capture_continuation.py --output /path/to/private/run
```

## Apigee

The harness provisions an evaluation Apigee organisation, a private network,
a client VM and a receipt-recording backend, deploys the quota-policy variants
and runs the fixed schedule in `gcp_mcp_study/schedule.json`. Its seed and
sequences match [apigee_protocol.json](../apigee_protocol.json), whose
accounting keys are aliased. It requires the Google Cloud CLI, Node and OpenSSL.

1. Replace `your-gcp-project` with your project identifier in every file under
   `harness/apigee`, then re-pin `gcp_mcp_verified/dependencies.json`, because
   the runner refuses changed dependencies.
2. Record your run in `gcp_mcp_verified/PROTOCOL.md`, then run
   `python3 freeze_repeat.py --freeze` there. It runs the offline suites and
   writes `FREEZE.json`. The supervisor refuses any source that differs from it.
3. Create a scratch directory named `/tmp/gcp-mcp-retry.<suffix>` and set
   `MCP_REPEAT_SCRATCH` to it. The resource code refuses any other location.
   Write `authorisation.json` there with the keys `supervise.py` and
   `resources.py` read (`approved`, `project`, `account`, `execution_id`,
   `source_commit`, `not_before_epoch` and the preflight flags), run
   `python3 resources.py prices` and write `cost_gate.json`.
4. Start `python3 supervise.py`. It allocates the evaluation organisation,
   sets up the network, VM and proxy, runs `live_repeat.py` once and always
   calls `cleanup.py`, which deletes the organisation, VM, network and
   temporary SSH key and records each removal. It never resumes an
   interrupted collection.

`manual_rehearsal.py` runs the same validator and backend over local HTTPS with
modelled quota behaviour and no cloud account. Before the execution, the
frozen sources passed 51 candidate and 34 original offline tests and two
complete local rehearsals. Those runs used the original bytes. The released
copy differs only as described under [Provenance](#provenance).

## Offline integrity check

```sh
python3 harness/check_harness.py
```

It checks every file against `PROVENANCE.json`, checks that the protocol and
policy copies match the root evidence, checks that the Apigee schedule matches
the released protocol, parses every Python file and scans for credentials and
account identifiers. It makes no network call and runs none of the harness.

[Back to the README](../README.md)
