# A Session Is Not a Mandate

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23283296.svg)](https://doi.org/10.5281/zenodo.23283296)

Evidence and offline checks for **A Session Is Not a Mandate: Safe Continuation
for Agent Authorisation Across Policy Revisions**, by Saeed Aghaee, accepted at
Security Standardisation Research (SSR 2026).

The paper asks whether an agent's cumulative limit still accounts for earlier
work after a policy revision. This repository contains the sanitised provider
records, policy inputs, generated results and offline models used to examine
that question. The checks use only the Python standard library. They require
no cloud account, credentials or paid calls.

## Contents

- [Quick start](#quick-start)
- [Find the evidence for a result](#find-the-evidence-for-a-result)
- [Repository structure](#repository-structure)
- [Reading guides](#reading-guides)
- [What the checks establish](#what-the-checks-establish)
- [Contributing and repository protection](#contributing-and-repository-protection)
- [Licence](#licence)
- [Citation](#citation)

## Quick start

Clone or download this repository, then run the commands from its root.
Python 3.12 is the tested version. No package installation is needed.

```sh
git clone https://github.com/mrwersa/continuation-evidence.git
cd continuation-evidence
```

Verify the generated numbers, provider records and recovery comparison:

```sh
python3 make_tables.py --check
python3 verify_revision.py
python3 verify_continuation.py
python3 verify_apigee.py
python3 compare_recovery.py --check
```

Run the scalar example and all 38 artifact tests:

```sh
python3 continuation_model.py
python3 -m unittest discover -s . -p 'test_scope.py' -v
python3 -m unittest discover -s . -p 'test_coordinator.py' -v
python3 -m unittest test_apigee -v
```

Successful verification commands print `PASS`. The three test suites contain
5 scope tests, 17 coordinator tests and 16 Apigee tests. The scope tests include
reproductions of the local scalar model's limitations. Their passing does not
make that model a coordinated handover implementation.

For what each command checks, see the
[verification guide](docs/guide.md#reproducing-the-papers-numbers).
To inspect generated output, use `python3 make_tables.py` or
`python3 verify_apigee.py --write`. The quick-start checks above do not rewrite
the committed results or make provider calls.

## Find the evidence for a result

| Paper result | Where to start | Offline check |
|---|---|---|
| AgentCore policy updates can make a session stale, and prescribed recovery can omit its earlier consumption | [Revision records and policy forms](docs/evidence-map.md#agentcore-policy-revisions) | `verify_revision.py` and `verify_continuation.py` |
| AgentCore's tested history includes both principal and session | [Principal isolation control](docs/evidence-map.md#agentcore-principal-isolation) | `verify_continuation.py` |
| Apigee retains consumption with stable counter identity, but a quota-policy rename selects a separate total | [Apigee records](docs/evidence-map.md#apigee-mcp-quotas) and [study guide](apigee_README.md) | `verify_apigee.py` |
| Managed Agents carries cost across cap changes and child-agent handoff, while in-flight work can exceed the cap | [Managed Agents records](docs/evidence-map.md#managed-agents-cost-accounting) | `make_tables.py --check` and `verify_continuation.py` |
| Retained accounting can preserve both the limit and usable allowance during an ownership change | [Offline coordinator and recovery probes](docs/evidence-map.md#offline-models-and-recovery-comparison) | `test_coordinator.py` and `compare_recovery.py --check` |
| A recipient count alone cannot distinguish histories that permit different future actions | [Scalar and recipient-set examples](test_scope.py) | `test_scope.py` |

The complete Apigee execution contains **90 sequences and 365 tool calls**.
AgentCore's revision evidence covers **120 scored policy updates**: 90 created
a revision and made the predecessor session stale, while 30 retained its
refusal. These are counts for the captured deployments and collection periods,
not estimates of provider-wide failure rates.

## Repository structure

```text
continuation-evidence/
├── README.md                 quick start and result-to-evidence links
├── MANIFEST.md               what each evidence file establishes
├── docs/
│   ├── evidence-map.md       clickable index grouped by experiment
│   └── guide.md              methods, checks and interpretation boundaries
├── .github/
│   ├── CODEOWNERS            maintainer ownership
│   ├── scripts/              documentation-link checks and tests
│   └── workflows/            offline verification on pushes and pull requests
├── *.json                    protocols, sanitised records and summaries
├── *.sha256                  committed evidence checksums
├── *.cedar, *.dogwood        policy inputs
├── *.py                      offline verifiers, models and tests
└── *.tex                     generated tables and numerical macros
```

Evidence and script filenames remain at the root so that verification commands,
checksum indexes and existing references keep working. The
[evidence map](docs/evidence-map.md) groups them by experiment without changing
their bytes or paths.

## Reading guides

- **Understand the terms:** [Vocabulary](docs/guide.md#vocabulary).
- **Trace a reported result:** [Evidence map](docs/evidence-map.md).
- **Understand the checks:** [Reproduction and verification](docs/guide.md#reproducing-the-papers-numbers).
- **Inspect the Apigee design:** [Apigee MCP accounting continuity](apigee_README.md).
- **Assess each file's scope:** [Manifest](MANIFEST.md).
- **Understand the offline implementation:** [Single-process coordinator](docs/guide.md#separate-single-process-coordinator).
- **Inspect sanitisation and resource handling:** [Sanitisation](docs/guide.md#sanitisation) and [cloud resources](docs/guide.md#cloud-resources).

## What the checks establish

The verifiers reconcile released records, check declared policy changes and
trial order, validate checksums and regenerate the reported outputs. They
establish internal consistency of the sanitised evidence. They do not
independently authenticate provider provenance or replay a live cloud service.

Live recapture requires cloud accounts, provisioning and charges. The capture
harnesses and source analysis implementation are outside this release. Some
Managed Agents controls retain aggregate counts rather than per-trial records.
The offline coordinator illustrates one trusted process, not a distributed or
production enforcement system. See the [detailed boundaries](docs/guide.md#artifact-boundary)
and [file-by-file manifest](MANIFEST.md).

## Contributing and repository protection

Changes go through a pull request and the **CI gate**, which runs the offline
checks, all 38 artifact tests and the documentation-link tests. Evidence changes
must explain their provenance and update any affected generated outputs and
checksum indexes. Never include credentials or deployment identifiers.

The repository owner is the maintainer. Public read access and forks do not
grant write access to this repository. Protected `main` requires passing checks
and resolved conversations, including for the owner. Force pushes and deletion
of `main` are disabled. Required approval count is zero because the repository
has one maintainer who cannot approve their own pull request.

## Licence

Python source code is licensed under the [MIT License](LICENSE). The evidence,
policy files, generated tables, checksum indexes and documentation are licensed
under [CC BY 4.0](LICENSE-DATA). Please cite the paper when you reuse them.

## Citation

If you use this artifact, please cite the paper. Release v1.0.0, the version
described in the paper, is archived at
[doi.org/10.5281/zenodo.23283296](https://doi.org/10.5281/zenodo.23283296). GitHub's "Cite this
repository" uses [CITATION.cff](CITATION.cff). Proceedings volume, pages and
DOI can be added when the final bibliographic record is available.

```bibtex
@inproceedings{aghaee2026session,
  author    = {Saeed Aghaee},
  title     = {A Session Is Not a Mandate: Safe Continuation for Agent
               Authorisation Across Policy Revisions},
  booktitle = {Security Standardisation Research (SSR 2026)},
  series    = {Lecture Notes in Computer Science},
  publisher = {Springer},
  year      = {2026}
}
```
