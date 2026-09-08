# Zero-LLM heterogeneous runtime — Unreleased successor

This is an implementation and local acceptance contract, not an accepted performance release. The immutable 1.4 stable pointer remains `e6e4dda5835e3cb345207457d5491131c6959b2c`. The predecessor is main `9eb904c21fd25aa0a77d2420ed080702fac17e59` (merged PR #12). No hardware speedup or new retrieval gain is claimed before the user's real local experiment.

## Architecture and boundaries

THM Core needs only Python/SQLite: tiers, FTS, scoped source packing, observations and advisory residency control. The optional Semantic Accelerator supplies local encoder vectors. Agent/LLM harnesses consume the same canonical `SearchIndex`; no generative model is needed to construct a query or invoke recall. The new runtime does not promote/demote, mutate resident budgets, turn retrieval/prefetch/mentions into hits, or rewrite memory truth.

`pip install .` does not install a tensor stack or run benchmarks. `python -m thm runtime doctor` works without keys, models, CUDA, NumPy, Torch or SentenceTransformers. The core-only test blocks provider/tensor imports and network, then exercises direct recall and legacy MCP initialize/tools/list/status/recall. Modern MCP's existing optional SDK contract is unchanged.

## Hardware observations

`HardwareProfile` distinguishes installed logical CPUs, OS-visible CPUs, process affinity and effective process capacity. Linux reads process masks, visible cgroup-v2 quota/cpuset ancestors, CPU flags, NUMA membership, physical core/socket identifiers, memory and cache metadata. Windows uses public processor-count/process-mask/group APIs and optional CIM CPU metadata. Darwin uses public sysctl observations. Optional explicit backend probing occurs in a subprocess; ordinary imports never initialize CUDA or Torch.

Missing or unreliable data remains null, including unsupported topology, unavailable ISA flags, Windows ISA dispatch and many NPU/POWER/RISC-V observations. x86 and ARM capability slots include AVX2/AVX512/VNNI/BF16/FP16/AMX, NEON/dot-product/I8MM/SVE/SVE2/SME/SME2; POWER MMA/RVV slots do not imply implemented optimized backends. A missing backend is not installed automatically. Hardware support, backend capability and observed kernel dispatch are separate fields. Dispatch remains null until an explicit profiler receipt with matching embedding profile and raw evidence hash is imported.

No BIOS, governor, power-plan or global environment changes occur. Thread/affinity candidates run in child processes. Default candidate planning uses a bounded subset of process capacity; topology-based masks are considered only when observed. Linux cgroup-v1 and nonobservable Windows group-wide allocation are not inferred from a CPU product name.

## Embedding identity and vector storage

`EmbeddingProfile` binds source model manifest SHA256, backend/version, device, precision, transformation, derived manifest, dimension, exact-input and L2 normalization contracts. A Torch CPU vector and an INT8/OpenVINO/CUDA query never silently share a model-ID namespace. Each request uses one profile's complete generation.

Legacy `vectors` JSON remains intact. New `embedding_profiles`, `vector_generations` and `vectors_v2` coexist; sparse reads of legacy indexes remain available. Legacy semantic queries need either their original explicit encoder/model identity or operator-certified transactional migration into a concrete profile. Migration validates the expected generation, completeness and vectors, refuses an existing target generation, and preserves the old table. New profile vectors default to JSON; little-endian float32 BLOB is optional pending measured acceptance. Truncation, wrong dimensions, nonfinite/zero vectors and incompatible profiles fail closed.

The immutable embedding cache keys profile ID plus SHA256 of exact UTF-8 encoder input. Only vectors are shared across scopes; ownership, authorization, row ID, source, tier and activity remain in each scoped index. Speaker-prefix changes, text changes and profile changes produce different keys. Same-key nondeterministic vector output is refused. A census measures exact repeated LME encoder inputs and avoided bytes/counter units; it does not estimate speedup.

## Local backends and preparation

The lazy registry implements Torch FP32, ORT FP32/INT8 and OpenVINO FP32/INT8 via optional packages. Torch is the fixed reference. ONNX provider names permit explicitly installed CPU/CUDA/CoreML/DirectML/QNN-style providers; the provider must actually be available. OpenVINO device selection is explicit. Other providers remain extension capabilities, not claims of tested hardware.

`thm-runtime prepare` copies a local source model into private staging, exports locally, verifies the original source hash, then publishes to a fresh content-addressed directory. It disables remote code/downloads in its isolated worker, does not overwrite the original model, and records converter versions and exact derived bytes. ORT INT8 uses dynamic QInt8; OpenVINO INT8 uses NNCF weight-only compression, explicitly distinct from activation PTQ/VNNI execution. Unsupported model exports fail closed. Partial or existing output namespaces are consumed, never silently replaced.

Backend API contracts follow [SentenceTransformers local backend documentation](https://sbert.net/docs/package_reference/sentence_transformer/model.html) and [ORT execution-provider documentation](https://onnxruntime.ai/docs/execution-providers/). Real encoder/provider execution remains `pending-real-local-runtime`; deterministic test doubles validate orchestration, not model quality or hardware speed.

## Calibration, profiles and scheduling

Explicit `runtime autotune` uses a versioned, SHA-bound label-free multilingual/technical micro corpus, not LoCoMo/LME QA. Each bounded candidate spawns, loads, warms up, measures and exits. Receipts include load latency, document/query throughput, single-query encoder-plus-selected-scorer p50/p95 (including transfer), batch latency, repeats/sample count and memory where reliable. Failures/timeouts produce failed candidates without leaking process-global thread state. Document throughput uses a separate SHA-bound workload of 512 unique inputs, exceeding every supported document batch size, with one full-batch warmup and three timed repetitions; the eight-document semantic corpus remains separate. Query throughput uses 128 unique SHA-bound inputs in configured query batches and scores against the 512-document matrix; three warm repetitions expose all generated query batch sizes. Interactive scorer measurements use the same document matrix. Interactive selection minimizes query p95, bulk maximizes query throughput, and background maximizes document throughput.

Admission compares finite normalized embeddings and actual canonical retrieval ranked IDs, packed selected IDs, budgets and scores against reference snapshots. The fastest eligible candidate wins; a micro-corpus pass is not full Protocol 2 acceptance. Fingerprints bind hardware/process allocation, package versions, source/derived model identities, embedding profile and THM implementation. Explicit invalidation preserves the old profile and creates a refusal marker. Changes require recalibration; no full benchmark runs at ordinary startup. Standalone auto-safe research execution requires a calibrated runtime profile and local model before encoder startup.

| Policy | Contract |
|---|---|
| reference | Torch FP32, explicit fixed device/profile, sequential queries, JSON vectors, no cache/overlap/experimental retrieval |
| auto-safe | Strict micro-corpus parity, default calibrated features only, one profile pinned for the session; explicit sparse fallback allowed |
| auto-throughput | Route requests among registered complete profile indexes; each request internally consistent; measured drift disclosed |
| approximate-performance | Explicit approximate precision and independent quality/parity evidence |

Scheduler registration verifies worker-reported threads, document/query batching and affinity against the runtime profile as well as embedding identity. The scheduler separates interactive, bulk and background workloads, bounded queue capacity, warm/cold state and observed caller-supplied load/VRAM hints. No unmeasured batching delay is inserted. Its fallback receipt identifies requested/actual profile, policy and reason; it does not silently replace a failed encoder with another semantic profile. Source/index validation still applies. Each profile owns an independent read-only index connection, cache and lock, allowing different CPU/GPU profiles to execute concurrently while preserving each request snapshot. Requests on the same profile remain serialized at its reader. Shutdown cancels pending work, drains active requests and closes owned readers and workers; the caller-owned index stays open. Encoder timeout terminates the child.

## Batching, overlap and timing

Document batch size is validated and reaches the actual outer encoder calls. A bounded pipeline prepares one next CPU text batch while one encoder batch runs, then atomically publishes all vectors only if source generation is unchanged. No partial generation is marked complete.

Batch and overlap paths reuse the same profile/exact-query vector cache as scalar search; only misses are encoded. `SearchIndex.search_many` provides a production batch API: one scope/read snapshot, encode_many, `D @ Q.T`, stable row-order tie handling and ordinary fusion/packing per query. `numpy_reference` is the default scorer; Torch CPU/CUDA scorers are explicit alternatives with transfer timing. Device=CUDA for embedding does not imply CUDA scoring. No epsilon tie policy is introduced.

`search_many(overlap=True)` runs a batch encoder worker while the caller prepares canonical lexical channels, then reuses those channels for fusion; receipts distinguish requested versus active overlap and account for the combined preparation wall interval. `search_overlap` runs query encoding on one worker while caller-thread SQLite performs FTS; SQLite is not shared across worker threads. LME query pre-encoding can reuse exact query vectors across isolated per-instance databases without merging FTS IDF. Runtime rows retain legacy timing fields and add FTS, matrix load/scoring, fusion, materialization and expansion fields. Batched rows label post-batch search timing and report embedding/scoring once in `batch_receipt`, with an amortized total including shared matrix load. Research summaries use that amortized total and retain the raw breakdown and batch receipt; this is not interactive latency.

## Deterministic retrieval successors

All features default off. `RetrievalFeatures(entity=True)` delegates to the existing entity projection; it is not a second entity engine. Harness configuration and MCP `--features-json` share this type.

- Explicit alias locators come from supplied alias pairs and exact speaker/source/technical identifiers. No bilingual alias generation or canonical memory mutation occurs.
- Temporal v2 ranks only query-conditioned lexical candidates with observable dates: ISO or explicit English month/day/year, anchored before/after/between/previous/next, first/latest and month/year hints. Unanchored duration/relative phrases remain hints without invented temporal truth.
- Finite grammar extracts WHO/WHEN/WHERE/VERSION, temporal operators, exact identifiers and explicit AND/OR. Unparsed queries use the ordinary path; only high-confidence hints affect ranking.
- Segment v2 packs actual bounded parent text slices with offsets and `complete=false`. `parent_locator_ids` and `complete_evidence_ids` are separate. Whole-turn LoCoMo gold credit never transfers automatically to a segment.
- Association v2 expands bounded explicit speaker/source/session adjacency/identifier relations, with hop/edge receipts under the same packing budget. Retrieval/mentions/prefetch never create edges or activity.

First-generation failures remain in [the frontier evidence](16-zero-llm-retrieval-frontier.md): old temporal showed no useful category gain, segment regressed, adjacency mixed gains with open-domain regression, size-normalized ranking failed. No successor feature becomes a production default until its independent local A/B admission.

## Workload policy basis

| User/workload | Generative LLM required | Local encoder | CPU/accelerator usage | Priority |
|---|---|---|---|---|
| Core-only deterministic | No | No | Bounded SQLite/FTS CPU | Latency |
| Occasional personal agent | No | Optional | Lazy local encoder, pinned profile | Latency/load cost |
| High-intensity coding agent | No | Optional | Warm encoder + exact cache | Latency |
| Multi-agent server | No | Optional | Bounded queues, complete multi-profile indexes | Throughput with per-request identity |
| Large history / few queries | No | Optional | Background builds, exact content reuse | Build cost and memory |
| Benchmark/research | No | Explicit | Fixed reference plus separately identified candidates | Reproducibility |
| Headless CI/IDE automation | No | No | Error signature/file/branch query directly to recall | Deterministic ignition |

See [the local verification plan](../reports/2026-09-08-local-runtime-verification-plan.md). This successor PR must remain open, with local acceptance pending. Stable pointers and accepted version are unchanged.
