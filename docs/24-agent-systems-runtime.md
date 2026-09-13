# Agent systems runtime

THM is a local-first agent memory and systems runtime spanning retrieval, residency, heterogeneous compute/storage, dynamic topology, native OS/hardware control, reliability and evaluation. Version 1.6 extends the 1.5 implementation. Logical T0–T3, compute/runtime and physical placement remain orthogonal. Topology, temperature/power, QoS and reliability are control/observation dimensions.

“Hot” originally meant memory hotness. The 1.6 architecture also covers execution hot paths, hotplug lifecycle and literal thermal state. This is an evolution of the project. `HotnessVector` retains distinct demand, semantics, latency, residency, reuse, thermal pressure and economic value inputs; high thermal pressure cannot become an unexplained promotion score.

## Product entry points

```python
from thm.harness import HarnessConfig, THMHarnessAdapter

config = HarnessConfig(db="memory.sqlite", scope="personal", systems=True, long_tail=True)
with THMHarnessAdapter(config) as memory:
    result = memory.recall("What changed before 2026-09-01?")
    print(result["context"])
    print(result["systems_receipt"])
```

Both flags default to false. The existing 11 harness surfaces keep their accepted semantics. `AgentSystemsRuntime` wraps the current `RuntimeService`: read-only scoped retrieval, bounded admission, pressure observations, epoch invalidation and explicit new-session adoption. A topology change during a query discards its provider output, invalidates resident state and retries sparse reference retrieval. Native source memory is never rewritten. Hosts explicitly mark a useful output to measure TUFR; token emission alone cannot supply that marker.

```bash
python -m thm systems smoke --output systems-smoke.json
python -m thm systems reliability --events 128 --seed 0 --output reliability.json
python -m thm systems observe --output native-observations.json
python -m thm.evaluation --mode acceptance --ceiling --long-tail --wall-seconds 120 --output long-tail-acceptance
```

Long campaigns require `--full-research`. The default smoke uses deterministic inference timings and real bounded THM retrieval, publication rejection, process timeout/reaping and source-identity checks. A raw trace is replayed with `python -m thm systems replay --trace trace.json`. It contains `tasks` matching `AgentTaskTrace`, optional topology events, thermal service multipliers, concurrency and ablation number. Replay outputs are always simulated.

Replay publishes reusable prefix state conservatively at producer completion, scoped by user, session, prefix and topology epoch. Concurrent requests cannot borrow unfinished state. Events through completion invalidate device reuse; a fallback that restores prefill extends the simulated window, and all events in that extended window are accounted for. Durations remain trace scenarios, without an invented hardware fallback speedup.

## Native execution and evidence

| Surface | Executable boundary | Evidence interpretation |
| --- | --- | --- |
| Dynamic topology | ABSENT/PRESENT/PROBING/ONLINE/DRAINING/OFFLINE/LOST/RECOVERING/QUARANTINED; native graph diff observer; scoped session/handle lifecycle | Fixture flap/reset/drain is separate from actual device hotplug |
| Linux | PSI snapshot/threshold poll, delegated cgroup v2 rollback, affinity/mbind, RAPL/hwmon/thermal/cpufreq, io_uring | Permission/API absence yields unavailable/fallback; no root requirement |
| Windows | Existing process-tree Job Objects and accounting, thread EcoQoS, IOCP | ETW collection uses owned, bounded logman/tracerpt sessions behind explicit S2 gates |
| macOS | Existing libproc/sysctl observations, pthread QoS, public thermal-state signal when available, AIO/kqueue, Accelerate CBLAS | Temperature/ANE/AMX are not invented from availability or marketing labels |
| GPU observations | Direct NVML, AMD SMI, Level Zero Sysman energy/temperature | Each sample identifies its public API and units; missing sensors stay null |
| CUDA VMM | CUDA Driver reserve/map/unmap/remap/release, source/index identity, allocation generation | Experimental S2 opt-in; remapping requires content rebuild and does not restore memory by itself |
| Apple inference | Existing executable CoreML adapter; MPSGraph public matrix binding; Accelerate matrix/scoring primitive | CoreML allowed compute units do not prove ANE operator placement; MPSGraph fixture does not certify a particular PyObjC/OS build |
| Registered buffers | Owned page-aligned host buffers, public mlock/VirtualLock and registration lifecycle | Explicit copy path; no automatic zero-copy claim |
| eBPF / ETW / userfaultfd | Public libbpf ELF-bytes load/attach/ring lifecycle; userfaultfd register/poll/copy/unregister; ETW native command lifecycle | Caller-approved BPF object and trace provider; native APIs/permissions may be absent; all research paths default off |

Native evidence levels are documented, discoverable, callable-fixture, native-executed, hardware-observed, performance-accepted and task-outcome-accepted. Capability discovery, adapter implementation and measured speed are separate assertions.

## SysCore

`native/thm-syscore` is a dependency-free Rust executable with a checked-in lockfile and optional C native I/O shim. It does not replace Python policy/memory/evaluation. Build with `cargo build --locked --offline --features native-io`. The native CI builds and tests Linux, Windows and macOS. Its framed protocol carries a version, operation and bounded request/response; one process owns one request and its buffers. The Python supervisor provides deadlines, process-tree cleanup and checked output bytes. Without the executable, a contained Python worker supplies portable I/O.

Native read failures can fall back. Source checksum mismatch cannot be accepted as success. Both native and portable paths verify the consumed output bytes against the expected SHA. Process termination/reaping completes before buffer ownership ends. The native I/O path is a bounded batch interface with per-request completion ownership; it does not claim a persistent shared ring or zero-copy transport.

## Thermal, power and concurrency

`ThermalSample` distinguishes design power, configured limits, instantaneous/average observed power and energy counters. Effective clocks are separated from requested P-states. `SustainablePerformanceEnvelope` reports p50/p90/p95/p99/p99.9/max, queue wait, thermal state and observable energy/bandwidth. Cold, warm and thermally soaked samples are never pooled silently. Named operating points include throughput knee, latency cliff, thermal cliff, power plateau, bandwidth saturation and queueing collapse. A plateau alone does not prove a hardware power wall.

Thermal backpressure uses bounded temperature slope and headroom. Stale/unknown information conservatively reduces background work. PSI stall time and latency tails constrain admission alongside utilization. `interactive`, `bulk`, `background`, `research` and `maintenance` remain independent QoS classes. Expired work remains in a cancelling state and occupies its slot until the worker owner acknowledges reaping or completion. A positive background share retains one idle slot when no foreground work contends; a zero share still blocks background dispatch. Operating-point comparisons require the same declared power state. The controller bounds worker/concurrency/batch/queue state; it does not promise throughput gains on unmeasured machines.

The existing RuntimeService keeps its three compatible execution/profile workloads. The agent wrapper routes research and maintenance execution through its background workload while retaining the original QoS queue and reporting both requested QoS and execution workload in the systems receipt.

The controller tracks the caller's absolute deadline, with a 30-second default when none is supplied. Search receipts leave native-path evidence unavailable unless a SysCore operation is owned by that request; shared SysCore history is not attributed to a new trajectory. Verified I/O reports per-operation fallback counts separately from the SysCore object's cumulative failure counter.

S0 observes. S1 applies reversible process/domain hints when supported. S2 power/clock/fan/quota/allocation changes require explicit capability, permission, opt-in, accepted evidence and rollback. The default executes none of those changes. No BIOS edits, driver installation, SDK downloading or global power-plan change occurs automatically.

## Agent program / KV / tools

AgentProgram, trajectory, session, turn, LLM/tool/subagent calls and environment steps provide shared scheduling identity. The vLLM, SGLang, TensorRT-LLM, llama.cpp, Dynamo, LMCache and Mooncake boundaries are integration contracts, not new inference engines. The KV bridge supports HBM/DRAM/SSD/remote/recompute and active/tool-wait/subagent-wait/reuse/expired states. It defaults to advice; applying a command rechecks the current provider record. KV persistence never establishes semantic memory persistence.

Read-only or explicitly safe idempotent tools may be proposed for speculation; execution is opt-in and the host owns its deadline worker. Side-effecting tools cannot automatically speculate. Overlap receipts use interval overlap, exposed tool latency and wasted work. Critical-path analysis uses dependency spans; it does not multiply microbenchmark speedups.

The A0–A11 harness keeps an identical task denominator. Trace-supplied or unavailable components are explicitly named, so an unchanged stage is retained as a negative/neutral result. Simulated timing does not establish task success. Measured TUFR requires a useful-output marker; absent markers remain null.

## Reliability and evidence storage

The reliability module separates wall time, requests, sessions, mutations, migrations, topology events and provider executions. It preserves right-censored runs and calculates Kaplan–Meier survival with pointwise intervals. Lifetime quantiles are withheld without the declared sample/failure minimum; unobserved quantiles stay null. Recurrent MTBF requires a repair-process exposure record. A conditional zero-failure Poisson bound names its assumption. No Weibull fit or small-sample hardware B10 is invented.

Request/session/mutation/topology/soak/release self-checks verify integrity. Deep-check cadence can respond to a sufficiently populated hazard history. Bounded fault campaigns exercise source replacement/corruption/disappearance, short writes, disk full, contained crash/hang, stale profiles, clock reversal, out-of-order events and topology churn.

New raw artifacts above 1 MiB use a manifest plus local CAS, GitHub artifact reference, S3-compatible storage or LFS. Manifests retain SHA, size, MIME/schema, producer commit, dataset, workload and command. Historical raw Git artifacts remain unchanged; the two non-newline BEAM JSON blobs have exact-SHA document-check exceptions. A changed byte loses that exception.

The admission check includes compressed raw formats such as `.json.gz`, `.jsonl.zst`, `.csv.bz2` and `.tar.xz`. CI compares the complete PR against its merge base, or the complete push against its previous ref; a new branch uses its merge base with `origin/main`. Local checks can supply `--base` explicitly. A missing comparison ref fails the check.

## CE and acceptance

`thm.systems.economics` provides THM/CE v2 evidence/advice for the 1.6 runtime. It requires matching commit/task denominators and source receipts; byte counters are not token measurements. Energy, thermal, topology, queue, reliability and task metrics carry units and evidence classes. Incoming budget/provider/concurrency/energy/residency advice is optional, epoch-bound and expiring. CE L0–L6 remains independent of THM T0–T3; neither repository imports the other.

See the [completion ledger](../reports/2026-09-13-thm-1.6-full-power-completion.md), [Apple audit correction](../reports/2026-09-13-apple-audit-forward-correction.md) and [ceiling/long-tail evaluation](25-long-tail-ceiling.md). Implementation stability requires the release gates; hardware performance, actual hotplug, long thermal soak, full BEAM/V2/MemoryArena and real Hermes outcomes remain separately attributable evidence.

## Public source contracts

The native boundaries were checked against [Linux PSI](https://www.kernel.org/doc/html/latest/accounting/psi.html), [cgroup v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html), [Windows QoS](https://learn.microsoft.com/en-us/windows/win32/procthread/quality-of-service), [Windows thread information](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/ne-processthreadsapi-thread_information_class), [Apple XNU AIO](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/kern_aio.c), [MPSGraph](https://developer.apple.com/documentation/metalperformanceshadersgraph/mpsgraph), [CUDA Driver VMM](https://docs.nvidia.com/cuda/cuda-driver-api/group__CUDA__VA.html) and [Level Zero Sysman](https://oneapi-src.github.io/level-zero-spec/level-zero/latest/index.html). These sources document APIs; they do not constitute THM machine-performance evidence.

Additional native references: [userfaultfd](https://docs.kernel.org/admin-guide/mm/userfaultfd.html), [libbpf API](https://libbpf.readthedocs.io/en/latest/api.html), [ETW collection](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/logman-create-trace), [ETW export](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/tracerpt). ETW timeout denotes the collection window; bounded startup, stop and conversion overhead are additional.
