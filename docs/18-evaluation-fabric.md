# Evaluation Fabric

Evaluation Fabric is the measurement layer across THM's logical memory, compute execution and physical storage planes. It introduces no retrieval or memory algorithm. Package/version and stable archive remain 1.4.0; this fabric is Unreleased. Adapter availability, fixture correctness, dataset retrieval, runtime performance and agent outcome are separate claims.

## Contracts and ownership

The installed `thm.evaluation` package defines schema `thm-evaluation/1` through typed `Adapter`, `Task`, `GroundTruth`, `Result`, `Receipt` and `Taxonomy` contracts. Dataclasses serialize to JSON; receipt SHA256 covers the complete public payload excluding its own hash. Source SHA binds canonical input JSON, while implementation SHA binds THM Python sources. Native projections additionally bind the applicable runner source SHA captured at module import, so changes outside the installed thm package invalidate their implementation identity. Canonical JSON hashes are distinct from upstream file-byte hashes. Existing native reports retain their original byte identities.

`Task` contains only source documents, query, scope, sequence and optional image identity. `GroundTruth` is evaluator-only and contains evidence IDs, unit, resolution, diagnostic status, answer and rubric. Only source documents enter SearchIndex. Result publication omits answers, rubrics, original queries and source text. Document/scope duplicates fail. Native source projections allowlist fields rather than indexing entire JSON records.

| Adapter | Native boundary | Evidence unit | What is implemented |
| --- | --- | --- | --- |
| LoCoMo | sample_id, conversation sessions, qa | document/dia_id | Protocol 2 gold parsing; complete evidence; category 5 diagnostic |
| LongMemEval-S | question_id, haystack_sessions, haystack_session_ids, answer_session_ids | session | Separate instance databases; one complete message can cover a gold session |
| LongMemEval-V2 | public trajectory states; insert/query | unavailable without a separately reviewed locator protocol | Text-only states projection; upstream registration factory; image queries explicitly rejected |
| BEAM | chat batches/turns; 10M plan nesting; probing_questions | unavailable | Native nested source projection and evaluator-only ideal_answer/ideal_response/rubric |
| MemoryArena / agent-benchmark | questions/answers/backgrounds; add/wrap_user_prompt | unavailable | Ordered subtask projection and memory interface across sessions; no environment campaign in acceptance |

V2 and BEAM use explicit transport envelopes: V2 is a list of `{id, trajectories, questions}`, where trajectories retain upstream public states and questions contain question/answer; BEAM is a list of `{id, chat_size, chat, probing_questions}`, retaining native chat and probing file payloads. Envelope IDs identify scopes, not gold locators. MemoryArena consumes native row lists. `fixtures.py` supplies tiny original examples; it redistributes no benchmark data. Live corpus preparation/download and official scoring remain upstream responsibilities.

## Three evidence layers

`memory-dataplane` measures any-gold, all-gold, macro/micro evidence recall, parent-locator coverage, budget use, empty context and p50/p95/p99 retrieval latency. Only complete packed evidence receives hits; parent coverage is distinct. Main denominators exclude no-gold, unresolved and diagnostic-only tasks. Missing locator labels produce null recall, never an answer-derived pseudo-recall. Session and document units must not be pooled as if identical.

`systems-runtime` records OS/Python/SQLite, operating point, wall time, documents/bytes processed and physical evidence. The default sparse operating point uses `utf8_bytes`, which is explicitly **not** a model tokenizer and cannot be compared numerically to historical 600 `cl100k_base` results. This fabric does not reinterpret CPU/CUDA backend labels as observed kernel dispatch.

`LLM-agent-outcome` defaults to `not-run`, zero generation/judge calls and null answer/environment scores. A real campaign must separately bind generated answers, model and judge identities, environment traces and evaluator receipts. Parser or interface fixtures cannot satisfy that layer. No generation provider is called by the acceptance or retrieval CLI. `outcomes.AgentOutcome` and `attach_outcomes` ingest separately produced evaluator scores only with exact executed task IDs, verified trace-byte SHA and model/evaluator identities. Fixture receipts cannot acquire live outcomes. Imported scores are externally supplied, not independently certified or automatically accepted. Layer-level answer accuracy and environment success are macro means over available per-task scores, with separate measured counts; missing scores remain null and are excluded from denominators. Per-task rows are retained.

Historical LoCoMo and LME runners now add `evaluation_fabric` operating-point projections through the same metric implementation; original native rows and summaries stay available. The LME projection explicitly excludes unresolved session labels even where historical native summary behavior differed. Historical receipts are not rewritten.

## Orthogonal taxonomies

| Axis | Meaning | Does not imply |
| --- | --- | --- |
| T0–T3 | Logical residency and access | DRAM, VRAM, SSD or HDD |
| Compute profile | Encoder, precision, device, scorer and scheduling | Tier or physical location |
| Physical placement | Representation, target and transport | Source authority, validity, activity or relevance |

`Taxonomy` carries three independent fields; changing one never derives either of the others. Default fixture retrieval runs on a Python sparse CPU profile and SQLite OS-managed placement. Labels for other configurations require corresponding observed receipts.

## Physical storage receipts

Each CLI benchmark receipt includes a separate `physical_probe` under `systems-runtime`: public StorageTarget, serialized StorageProfile and profile ID, extent placement and actual PhysicalTelemetry. The probe uses at most 1 MiB scratch and a five-second access-loop budget. It uses the existing physical adapter to verify and read a content-addressed fixture. Absolute roots are omitted from public records.

SQLite I/O remains `unavailable` because the retrieval database path has no extent instrumentation. The separate probe is never substituted for query I/O or end-to-end acceleration. OS locality/capability observations may remain unknown; an unavailable probe is reported explicitly and does not invent a profile. CXL, DAX, SPDK, GDS and specialized transport performance remain unvalidated extension descriptions.

## Bounded execution

From a source checkout or installed core package:

```powershell
python -m thm.evaluation --mode acceptance --wall-seconds 3300 --output .thm-evaluation/acceptance-01
```

Acceptance needs Python 3.10+, no optional model/tokenizer dependency, no credentials and no network. Smoke executes at most two tasks per adapter, acceptance at most eight. External bounded inputs are limited to 4 MB, each task to 2,000 documents and 2 MB of source text. Limits reject oversized tasks rather than silently truncating their evidence corpus. Task caps disclose truncation. The supervisor enforces the deadline on the owned process tree on Windows, Linux and macOS; timeout/error returns nonzero and cannot create a passed acceptance receipt. Use a new output directory for every run.

The Windows example sets 3,300 seconds, leaving 300 seconds below one hour for process startup and cleanup. It validates fixture contracts and native interface behavior, not the user's actual GPU model/dispatch or a full dataset. Unit, docs, Hermes and CLI harness gates run separately in CI.

Full external retrieval campaigns require two explicit switches and a dataset:

```bash
python -m thm.evaluation --mode full-research --full-research --benchmark beam --dataset /prepared/beam-envelope.json --wall-seconds 86400 --output /new/beam-research
```

Use `longmemeval-v2` or `memoryarena` for their independent inputs. This command does not start a live environment/reader/judge. For a real V2 harness, install THM into the separately provisioned upstream environment, call `thm.evaluation.memory.register_longmemeval_v2()` before upstream `build_memory`, then select `memory_type=thm_text` with an explicit budget. The backend supports fresh builds; prebuilt save/load explicitly fails. For MemoryArena, substitute a per-task `AgentMemory` object at the MemoryClient boundary and keep it alive across that task's sessions; `add` receives only actual agent/environment observations. Close the object at task end. No mock environment is reported as a real outcome.

Native legacy LoCoMo/LME command-line runners require `--full-research`. The separately supervised runtime verifier may invoke these research runners on its explicitly capped sample arms; its existing wall limit and receipt remain controlling. The full retrieval/frontier GitHub workflows require manual dispatch with `full_research=true`; pushes cannot launch them. Work execution in this successor is restricted to fixtures and bounded gates.

## Upstream interface provenance

Interface inspection on 2026-09-09 used the official source trees below. These are interface references, not performance evidence or dataset acceptance:

- [LongMemEval-V2](https://github.com/xiaowu0162/LongMemEval-V2/tree/2cc8c540bdb87fe6761629b585e727e1c4704520): `memory_modules/memory.py`, `trajectory_store.py`.
- [BEAM](https://github.com/mohammadtavakoli78/BEAM/tree/b2da22eac88bb0874c64665f13457eb99835774a): native answer-generation/chunking input paths and probing-question schema.
- [MemoryArena](https://github.com/ZexueHe/MemoryArena/tree/6cd9de14b71915e39ac742a20dc33785e14b6aab): `memory/client.py`; [native dataset structure](https://memoryarena.github.io/).

See [validation contract](03-validation-contract.md), [runtime](17-zero-llm-heterogeneous-runtime.md), [physical storage](physical-storage-fabric.md) and [testing/release](08-testing-and-release.md).
