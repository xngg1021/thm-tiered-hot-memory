# Runtime optimizer — Unreleased

The optimizer seeks a material execution improvement within semantic and resource constraints. It can retain the current/reference path indefinitely when evidence is noisy, incomplete or incompatible. Normal use collects observations; a user benchmark is not a prerequisite.

## Evidence before selection

A `ProfileKey` binds hardware/allocation, OS build, driver/runtime, provider versions, source/compiled model identities, embedding dimension/precision, index implementation/generation, corpus scale, index configuration, physical placement, workload, semantic policy and implementation identity. Placement changes and source-generation changes invalidate reuse. Unknown native driver identity restricts reuse to the current process. Corrupt, stale, future-clock or unsupported-schema evidence cannot become a selected point.

The SQLite profile store preserves checksummed observations, first/last validation, semantic class, material-gain decision and quarantine. It stores bounded whitelisted numeric measurements and sample provenance. Unsupported/corrupt stores produce a volatile safe fallback without rewriting the original file. Failure cooldowns grow with repeated failures and remain bounded. Explicit invalidation is a refusal marker, not source deletion.

| Evidence | Measured scope | Limit |
| --- | --- | --- |
| Passive request | Real queue entry to completed result; amortized process CPU and stage clocks | Workload observations do not by themselves prove a better alternative |
| Vector replay | Cached query vector, actual source index and complete retrieval/packing, plus an observed encode-cost floor | Encode cost is an explicit estimate; not a fresh encoder benchmark |
| Model replay | Fresh encoding, scoring, ranking and packing inside the isolated worker | Queue/IPC and long-run workload behavior require passive validation |
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
| auto-safe | FP32 exact candidates with observed strict structural/numeric parity |
| auto-throughput | Strict eligible execution candidates; throughput preference does not admit ANN/low precision |
| approximate-performance | Explicit ANN/approximate candidates with separate quality deltas |
| interactive | Predicted completion/p95 within SLO, including queue and measured cold staging |
| bulk | Throughput within semantic/resource constraints |
| background | Measured energy/CPU efficiency where available, then throughput |

The selector reads actual resident-handle state and queue depth. Unknown cold staging prevents a candidate from claiming a warm-path latency. Startup/compile/staging values are explicit, and the joint planner can amortize known staging over expected reuse. There is no universal fastest backend or model-name based device choice.

## Online batching and failure

Compatible scope/workload/settings share a FIFO queue. A singleton is served immediately at low arrival. Real arrivals and queue depth increase batch size within deadline, wait and pending-count bounds. Expired requests do not execute. Receipts separate queue wait, compute, actual batch, fill ratio, arrival estimate and deadline misses.

Strict online retrieval keeps singleton query encoding and verifies vector-batch scores/ranking against the fixed singleton reference before accepting the batched result. Per-row drift falls back to that reference. Model workers currently serve singleton query-embedding chunks; their inference acceleration is independent of request coalescing.

Execution failure quarantines the relevant provider and regenerates a reference execution plan/receipt. A concurrent source or placement change triggers one replan; repeated change fails explicitly. Source data, activity, hits and retrieval feature settings never change as a side effect of optimization. The retrieval-budget advisor emits shadow recommendations only.
