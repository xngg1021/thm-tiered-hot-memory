# Runtime optimizer — 1.5 implementation

The optimizer seeks a material execution improvement within semantic and resource constraints. It can retain the current/reference path indefinitely when evidence is noisy, incomplete or incompatible. Normal use collects observations; a user benchmark is not a prerequisite.

## Evidence before selection

A `ProfileKey` binds hardware/allocation, OS build, driver/runtime, provider versions, source/compiled model identities, embedding dimension/precision, index implementation/generation, corpus scale, index configuration, physical placement, workload, semantic policy and implementation identity. Placement changes and source-generation changes invalidate reuse. Unknown native driver identity restricts reuse to the current process. Corrupt, stale, future-clock or unsupported-schema evidence cannot become a selected point.

The SQLite profile store preserves checksummed observations, first/last validation, semantic class, material-gain decision and quarantine. It stores bounded whitelisted numeric measurements and sample provenance. `observed-request` is a distinct semantic status: it means an alternate model matched the paired request that was actually tested, not that it has a provider-wide strict-equivalence certificate. Unsupported/corrupt stores produce a volatile safe fallback without rewriting the original file. Failure cooldowns grow with repeated failures and remain bounded. Explicit invalidation is a refusal marker, not source deletion.

| Evidence | Measured scope | Limit |
| --- | --- | --- |
| Passive request | Real queue entry to completed result; amortized process CPU and stage clocks | Workload observations do not by themselves prove a better alternative |
| Vector replay | Cached query vector, actual source index and complete retrieval/packing, plus an observed encode-cost floor | Encode cost is an explicit estimate; not a fresh encoder benchmark |
| Model replay | Fresh encoding, scoring, ranking and packing inside the isolated worker | Semantic evidence is observed-request-only; it does not globally certify an alternate embedding implementation |
| SDK fixture | Public-call shape, lifecycle, receipts, identity/failure behavior | No hardware speed, operator placement or license acceptance |
| Prior bb16760 retest | Exact historical source/compiled/runtime receipts | Not performance evidence for this new implementation |

The replay order alternates baseline and candidate; it performs one warmup and five bounded repetitions. Every pair must pass the semantic comparison. Samples remain explicitly classified in persisted evidence. Semantic admission is limited to observed requests; aggregate memory quality and agent outcomes remain separate.

## Material gain gate

The default gate requires at least five measurements, a 5% relative improvement and a 0.25 ms absolute improvement. Median absolute deviation estimates a deterministic dispersion envelope. The conservative improvement must exceed the material threshold and uncertainty envelope. This is not a statistical confidence interval.

The receipt includes measured-faster, relative/absolute gain, noise floor, conservative gain, sample count, resource tradeoff and decision/reason. A small observed difference such as 26.08 versus 25.63 ms is retained as noise or trivial gain. RAM is constrained; paired CPU regression is bounded by 25% or 1 ms when CPU evidence exists. A GPU model candidate must have a usable memory observation to satisfy a GPU memory constraint. Unknown constrained resources fail admission.

Cooldown and hysteresis prevent repeated switching. Candidate exploration itself does not switch the serving path. Session choices use a logical anchor so discovering another device cannot promote a new provider during an existing session. Driver/generation changes may force a reference fallback immediately for correctness.

## Pareto and workload policies

Pareto comparison separates workload and semantic class. It includes p50/p95/p99, throughput, CPU/GPU time, RAM/VRAM, transfer/I/O, startup, compile, energy and failures. An unknown value is not a zero-cost advantage. The planner keeps a small bounded candidate set based on fit, prior evidence, update/rebuild cost, allocation-relative scale and native backend capabilities; it does not enumerate a Cartesian grid.

| Policy / workload | Selection |
| --- | --- |
| reference | Fixed explicit reference; no automatic exploration |
| auto-safe | FP32 exact vector-index candidates with strict structural/numeric admission; observed-request alternate-model evidence cannot activate |
| auto-throughput | Strict eligible vector-index execution candidates; throughput preference does not admit ANN/low precision or observed-request alternate-model promotion |
| approximate-performance | Explicit ANN/approximate candidates; observed-request alternate-model points may activate only here and retain their limited evidence scope |
| interactive | Predicted completion/p95 within SLO, including queue and measured cold staging |
| bulk | Throughput within semantic/resource constraints |
| background | Measured energy/CPU efficiency where available, then throughput |

The selector reads actual resident-handle state and queue depth. Unknown cold staging prevents a candidate from claiming a warm-path latency. Startup/compile/staging values are explicit, and the joint planner can amortize known staging over expected reuse. There is no universal fastest backend or model-name based device choice.

## Online batching and failure

Compatible scope/workload/settings share a FIFO queue. A singleton is served immediately at low arrival. Real arrivals and queue depth increase batch size within deadline, wait and pending-count bounds. Expired requests do not execute. Receipts separate queue wait, compute, actual batch, fill ratio, arrival estimate and deadline misses.

Strict online vector retrieval keeps singleton query encoding. Once an exact provider/profile/generation is admitted, a known FP32 accumulation contract permits a bounded top-k plus cutoff-witness check. Separated numeric intervals require only k+1 host row scores; ambiguous ties/order, exceeded numeric bounds or unknown accumulation use the full stable singleton fallback. Guard cost is included in shadow candidate timings before performance admission. An unadmitted profile cannot use the certificate.

Model workers currently serve singleton query-embedding chunks. A one-query paired model replay remains `observed-request` evidence even when all repeated outputs match. It cannot be promoted by `reference`, `auto-safe` or `auto-throughput`; only explicit `approximate-performance` may activate such a point at a later session boundary. A future provider-wide equivalence certificate would require a separate evidence contract rather than silently widening the scope of one observed query.

Execution failure quarantines the relevant provider and regenerates a reference execution plan/receipt. A concurrent source or placement change triggers one replan; repeated change fails explicitly. Source data, activity, hits and retrieval feature settings never change as a side effect of optimization. The retrieval-budget advisor emits shadow recommendations only.

## Retrieval engineering ledger

Whole-prefix token counts use only the public tokenizer callable, an exact-input LRU and bounded bytes. There is no private regex/BPE API dependency and no assumption that block counts are additive. Compatibility CI explicitly exercises cache hits for tiktoken 0.7.0, 0.8.0, 0.9.0, 0.10.0, 0.11.0, 0.12.0, 0.13.0 and 0.14.0 using in-memory vocabularies. The final packed output is counted independently. SQL query counts, tokenizer call/cache counts and k+1-versus-full-scan counters are engineering evidence, separate from fabric lifecycle correctness and real-hardware performance.

## 1.5 implementation and evidence contract

[1.5 implementation surface](24-full-power-implementation.md) defines the executable configured provider/storage lifecycle, allocation and joint-planning APIs, explicit actuator, five benchmark/environment/outcome interfaces, independent CE bridge, and LangGraph/Deep Agents lifecycle. Automatic memory mutation remains false and rejected features remain default-off. Hardware, full-research and real task evidence are separately recorded in the [completion ledger](../reports/2026-09-12-thm-full-power-completion.md).
