# Testing, document publication and bounded release

Run the public checks from the repository root:

```bash
python -m unittest discover -s tests -v
python scripts/thm_numeric_audit.py
python scripts/check_docs.py
```

The engine tests import scripts/thm.py directly and use temporary synthetic source stores. They cover stable IDs, prefix collisions, directory separation, ambiguous updates, invalid dates/events, retry behavior, confirmation scheduling, validity, pins, conflict rejection, write failure, migration and CLI error codes. Independent child processes test concurrent updates and release of a killed lock holder. No real profile or external model is used.

The document-check unit tests use intentionally synthetic documents and a test-specific historical digest. The standalone check_docs.py command checks the actual repository, including the original preserved report's fixed Git blob, relative links, JSON files, source-list shape and Python syntax. It accepts additional documents and inspects them, rather than blocking every documentation addition with an exact Markdown count. Neither unit tests nor syntax checks certify external facts.

The ten numeric tests preserve the old specification and its counterexamples. A passing assertion that old high-cost entries could not be evicted is a historical diagnostic, not proof of repaired behavior. The current engine tests verify the new behavior separately.

## Reproducibility record

The [machine-readable hardening record](../reports/2026-09-06-engine-hardening.json) identifies the starting commit, actual commands, Python version and file hashes. Raw local unittest and numeric logs are published alongside it. It explicitly distinguishes the materialized repair subset from unchanged remote documents. An inability to materialize an entire checkout must not be written as a full local repository-check pass.

The GitHub workflow runs the complete repository checkout on Linux, Windows and macOS. Workflow presence is not a pass; inspect the run for the exact commit. There are no API credentials, model calls or paid research jobs in the workflow. Failed operating-system jobs retain their failures.

## Publication inventory

The [document index](README.md) lists every project document maintained here. Existing research/architecture and original reports are retained. The public bundle adds the engine guide, explicit migration procedure, implementation status, repair report, current tests and historical defect probes. The former upstream document is retained as a dated historical source file; its corrected successor states which claims were narrowed.

Personal indexes, actual memory text, configuration, private reference code, mixed-project chat exports and protected third-party project material are not public documents in this repository. Missing private ZIP bytes are not reconstructed or claimed uploaded. Source code and documentation uploads do not install the tool or migrate user data.

## Finite next work

First use the CLI against a copied test profile and review migration output. Native host integration, task retrieval and model evaluation need their own small, explicit acceptance work. This repair does not create a new runtime, database server, research platform, provider farm or automatic submission to the upstream repository.
