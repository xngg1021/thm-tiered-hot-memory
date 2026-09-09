# Zero-touch runtime — Unreleased

THM serves with a safe available execution path, observes real requests and explores a small number of alternatives during idle opportunities. Users supply their local data and, for semantic retrieval, an existing local model. Normal operation does not require a benchmark, a calibration script, a cloud account or a generative model call.

Package/version remains **1.4.0**. The immutable stable archive remains `archive/v1.4.0-stable@e6e4dda5835e3cb345207457d5491131c6959b2c`. This successor starts at main `2d5c2adcf994edd8b7bb3c0546983ba9531af392`; its predecessor's actual post-fix hardware test is [bb16760](../reports/2026-09-09-post-fix-retest-bb16760.md). Those measurements are not measurements of this new runtime.

## Normal operation

1. Core startup reads standard-library hardware/allocation metadata and provider distribution metadata. It does not import native SDKs, initialize accelerators, convert models or execute a benchmark.
2. Sparse/literal requests run immediately. Dense/hybrid requests use an explicitly ready FP32 reference encoder; an unavailable reference produces an explicit sparse fallback receipt. Loading an explicitly configured local reference is separate from automatic candidate preparation.
3. The public `RuntimeService.submit` queue combines compatible concurrent requests when a real queue exists. Low arrival rates remain singleton requests. `search` provides a synchronous facade. Harnesses can also use their own concurrency/lifecycle policies.
4. Passive telemetry observes queue wait, request completion, stage clocks, actual batch, process CPU and fallback. Unsupported measurements stay null.
5. A disposable worker probes one installed provider or replays one candidate within wall/CPU/RAM/I/O limits. Foreground arrivals preempt background work without waiting for teardown. Battery/thermal observations and queue pressure can suppress exploration.
6. Semantic parity, resource limits, a material gain threshold and uncertainty checks control publication. Exact vector-index candidates may become eligible only under their policy and identity constraints. Alternate inference/model implementations are measured on observed requests in private replicas but are **not** globally certified by that sample: `reference`, `auto-safe` and `auto-throughput` retain the authority embedding path. Only explicit `approximate-performance` may activate an observed-request-only alternate model at a later session boundary. Failure or stale generation returns to the validated reference.

Runtime decisions change execution, not source ownership, scope, valid time, activity, explicit hits, truth, T0–T3 membership or retrieval policy. The budget advisor remains shadow-only.

## APIs and harness lifecycle

```python
from thm.runtime.fabric.service import RuntimeService

runtime = RuntimeService(index, encoder=local_encoder, model_id=local_encoder.model_id)
try:
    result = runtime.search("project", "query", mode="hybrid", budget=600)
    receipt = result["runtime_receipt"]
    runtime.new_session()
finally:
    runtime.close()
```

The example assumes an already indexed scope with matching reference vectors. `RuntimeService` owns its worker/queue/provider lifecycles; the caller still owns the source `SearchIndex` and reference encoder. The default policy is `auto-safe`; `reference` disables automatic exploration. `approximate-performance` is an explicit opt-in and retains quality/evidence-scope disclosures.

`THMHarnessAdapter` uses the runtime. Hermes initializes it lazily, forwards session changes and closes it on shutdown. Modern and legacy MCP status include the runtime state. Legacy MCP's declared output schema includes the added status field. Reference research runners continue to call `SearchIndex` with fixed explicit identities.

## Automatic local model preparation

For a local FP32 SentenceTransformer source, installed framework providers and the supported ORT/OpenVINO text-model bridges can be prepared in a bounded worker. The worker loads a reference, uses the actual tokenizer/pooling contract, copies the derived SQLite index into a private workspace and embeds documents under a new `EmbeddingProfile`. It then compares uncached query encoding, scoring, ranking and packing across paired repetitions.

The worker's comparison is an **observed-request-only** semantic check. It is valuable measurement evidence, but one sampled query cannot prove that an alternate embedding implementation is globally equivalent on unseen queries. Therefore the resulting point is recorded as `observed-request` evidence and is never automatically activated by `reference`, `auto-safe` or `auto-throughput`. Under explicit `approximate-performance`, a materially faster measured point may remain warm and serve after a session boundary with its evidence scope disclosed. Query vectors and document vectors always come from its own profile; the original index remains unchanged. A source-generation change invalidates the point. A timeout, incompatible model architecture, failed exporter, semantic mismatch or unknown constrained GPU memory retains the reference. Temporary model/index artifacts disappear when the worker closes. Durable compiled engine caches supplied by native adapters have their own content/dependency keys.

Arbitrary named-tensor models require explicit preprocessing/pooling from their caller. Core ML, native TensorRT-RTX, MIGraphX and other raw-tensor adapters do not invent a text model contract. Provider implementation availability and automatic text-bridge eligibility are separate facts.

## Bounds and privacy

| Resource | Default / rule |
| --- | --- |
| Vector replica budget | 256 MiB per runtime device executor |
| Background window | 2 seconds wall, 1 second CPU, at most once per 60 seconds |
| Background I/O | 16 MiB; estimated work is checked before launch |
| Shadow process RAM | Configured replica budget plus explicit 128 MiB runtime allowance |
| Online queues | At most 8 compatible groups, 256 pending per group, up to 32 requests per cohort |
| Online waiting | 2 ms batching opportunity; 100 ms default queue SLO; misses reported |
| Passive history | 128 samples per candidate/workload, at most 32 groups |
| Profile history | At most 4096 observations, 30-day freshness limit |
| Session choices | Bounded to 128 cached identities; incompatible generations cannot reuse a point |

Large imports/models/conversions may not fit the default background budget; they are deferred automatically. The core path continues to serve. Linux uses procfs accounting, Windows uses Job Objects and public accounting, and macOS uses `proc_pid_rusage`. Retained Windows warm workers renew their cumulative Job Object CPU ceiling rather than resetting it as a per-request allowance. Linux I/O includes cached file reads; macOS accounting reports physical disk I/O. These are explicitly different observations. Unsupported energy, GPU time, topology and dispatch remain unknown.

Only the private worker receives source paths and request text. Public profile keys hash private identifiers. Stored measurements and explain/status output contain no query text, model locator, source content, device serial or claimed kernel dispatch. No SDK/model download, privileged command, power-plan change or host thread-policy mutation is performed.

## Inspection

```bash
python -m thm runtime status
python -m thm runtime doctor
python -m thm runtime providers
python -m thm runtime explain
```

These commands inspect metadata by default. Explicit `--probe-provider` requests use a bounded process. `profile` and `invalidate-profile` expose the versioned local evidence store. The older explicit `prepare`/`autotune` commands remain research/diagnostic tools; they are not required product setup steps.

See [Provider Fabric](21-provider-fabric.md), [optimizer](22-runtime-optimizer.md), [vector indexes](23-vector-index-providers.md), [support matrix](provider-matrix.md) and [physical storage](physical-storage-fabric.md).
