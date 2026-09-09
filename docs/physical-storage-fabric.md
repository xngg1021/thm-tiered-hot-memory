# Unreleased physical storage fabric and bounded verification

## Evaluation receipt integration

[Evaluation Fabric](18-evaluation-fabric.md) carries serialized StorageProfile, profile ID, representation placement and extent I/O PhysicalTelemetry in a separate systems-runtime physical_probe. The probe uses bounded scratch with existing verify/read adapters. SQLite query I/O is unavailable and cannot inherit these microbenchmark counters. Logical T0–T3, compute profile and physical placement remain orthogonal; unknown capability observations and specialized hardware remain unvalidated.

Package identity remains 1.4.0. This successor has no stable/release designation.

## Independent planes

T0–T3 retain their logical residency/access meaning. T0 is not DRAM and T3 is not HDD or tape. Compute profiles choose encoders/scorers and batching. Physical placement chooses representations and transport; it cannot change source validity, activity, ownership or tier. Hardware/storage speedup does not establish memory-quality improvement.

| Plane | Production modules | Authority |
| --- | --- | --- |
| Logical evidence | `retrieval.py`, `features.py`, existing memory policy | Source identity, scope, complete/partial evidence |
| Compute | `runtime/scheduler.py`, existing complete RuntimeProfiles | Explicit profile, precision, semantic gates |
| Physical | `physical/contracts.py`, `probe.py`, `planner.py` | Observations and shadow recommendations only |
| Immutable data | `physical/segments.py`, `adapters.py` | Derived representations; source remains authoritative |
| Exchange | `physical/migration.py` | Explicit verified manifest change; no logical promotion |
| Joint execution | `physical/execution.py` | Receipt-bound explicit execution through RuntimeScheduler |

## Granularity

`LogicalObjectRef` and `GenerationRef` bind source/parent/scope. `RepresentationRef` cannot acquire authority. `SegmentRef` carries parent, locator, character offsets and `complete=false`; existing default-off segment retrieval now emits that typed relation. Vector row identity contains source document ID and hash, while a shard packs many rows contiguously. `VectorShardRef`, `TransferExtent` and `AllocationExtent` represent independent vector, transfer and allocation units. A memory item is not an I/O unit. No allocator, physical prefetch or automatic residency controller is enabled.

## Observations and storage identity

`StorageTarget` retains a private root for execution. Public receipts omit roots and serial numbers; logical target/mount identities are hashes. Filesystem, bus, NUMA node, PCIe relation, capacity, block geometry, readonly, mmap/direct-I/O/DAX/zoned/remote/GPU-direct observations can be absent. Product names do not establish capabilities. Linux reads mountinfo, block sysfs, NUMA distances, CPU sockets/core groups, and presence of NIC/PMem/DAX/CXL nodes. Windows uses public Get-Volume/Get-Partition/Get-Disk CIM output. macOS uses diskutil plist. Missing disk/NUMA relationships, HMAT/CDAT metrics and measured transport costs remain unknown. Processor-group and detailed accelerator relationships remain extension observations, not validated placement capabilities.

Storage fingerprints bind stable target/mount fields and hashes of probe/adapter/benchmark/contracts implementations. Free capacity and sampled network RTT do not churn identity. Capacity is still checked at planning time. Cost profiles are exact operation/size/concurrency samples, with no interpolation or device-name ranking.

## Backend evidence boundary

Linux filesystem names alone do not establish local block storage: ext4/xfs/btrfs may sit on remote transports, and overlay backing remains unknown. Public sysfs NVMe transport, iSCSI/FC host/session relationships, and ATA/USB ancestry supply locality evidence. Stacked block devices require all observed backing devices to be local; any observed remote backing is remote, and incomplete evidence stays unknown. This follows the [distinction between PCIe and network NVMe transports](https://xnvme.io/tutorial/transports/index.html), without inferring speed from either.

| Backend family | Implementation | Performance status |
| --- | --- | --- |
| Portable local regular files | Immutable segments, buffered and mmap reads, extent adapter, explicit migration | Synthetic/local smoke only; target machine pending |
| SQLite vectors_v2 | Existing JSON/BLOB profile path preserved | Existing evidence remains separately scoped |
| PMem/DAX/CXL, NVMe/SATA/SAS, rotating/zoned media | Public observations where exposed; filesystem access only when mounted | Specialized access unvalidated |
| DRAM/unified memory/VRAM | Representation descriptors; existing compute runtime handles dense arrays | Dedicated allocation adapter unavailable |
| SMB/NFS/NAS, NVMe-oF, FC-NVMe, Ceph/RBD, Lustre, BeeGFS | Extension descriptors; mounted filesystem may be observed | Native fabric adapters unavailable |
| DAOS, S3, HSM/tape/archive | Extension descriptors | Unavailable |
| SPDK, NVIDIA GDS/cuFile | Extension descriptors | Unavailable; no direct-DMA claim |

No tensor, NumPy, enterprise storage package, GPU, network, installation hook or backend auto-install is added to core. Dense retrieval still imports NumPy lazily as before.

## Immutable vectors and publication

SQLite retains identities, scopes, generations, FTS, profile metadata and `physical_placements`. `storage export` materializes an existing complete vectors_v2 generation into one contiguous shard. It checks normalized finite nonzero vectors, dimension, profile, source generation and row order, writes a fresh temporary file, fsyncs, verifies the file, publishes an exclusive immutable content-addressed filename, then switches the SQLite manifest under `BEGIN IMMEDIATE`. Publication rechecks both source generation and the exact vector snapshot (completion, row keys, dimensions, encoding and bytes) under that write transaction. A same-generation re-embed cannot publish obsolete vectors over current rows or a newer placement. An orphan file may remain; it is never authoritative. Existing BLOB vectors remain present.

The format contains magic/version, profile ID, generation, dtype/dimension/row count, payload length, row-order hash, float32 payload and trailing payload checksum. The SQLite manifest also binds whole-file SHA-256. Readers validate both identities and content before use. Truncation, wrong dimension/profile/generation/order or invalid vectors fails closed. mmap and buffered modes share validation. This first implementation materializes validated vectors into a NumPy matrix for scoring; it does not claim zero-copy or GPU-direct execution.

External placement is optional and explicit. Re-embedding clears its pointer while retaining immutable files. Scope replacement transactionally clears all profile vectors, vector generations and physical placement pointers for the changed scope; no-op replacement and failed transactions preserve them, and other scopes and immutable files remain intact. A stale or corrupt placement fails closed unless the existing scheduler was explicitly configured for sparse fallback. No cross-profile dense fallback is introduced.

## Explicit migration and recovery

New export and migration roots are exclusively owned by one canonical database path, recorded through an atomically published ownership receipt before any index publishes objects there. Another database cannot export/migrate into the same owned root, even if an identical verified object exists. Loads and verification reject copied foreign placement pointers. Retirement rechecks source and target ownership as well as every same-index placement reference; this prevents deleting a different database's live object.

Legacy roots without an ownership receipt remain readable and support copy-to-fresh-owned-root migration, with their source retained. Existing unowned segment objects cannot be retroactively claimed as exclusive, and retirement of an unowned source is refused. A copied database must use its own physical root rather than silently inherit another database's ownership. Root ownership does not promote data to logical authority.

`storage migrate` creates a fresh private journal containing exact predecessor, target, profile, rows and retirement intent. Recovery checks the current SQLite manifest and source generation, copies to a fresh target temp, verifies bytes/schema/vectors, exclusively publishes the object and transactionally changes the manifest. Each checkpoint appends a physical receipt. Default copy/verify/publish keeps the old file. Source retirement requires `--retire-source` and the exact same flag on resume, verifies the new publication again, and refuses deletion while another placement references the old object. No global cleanup command exists.

Fault fixtures cover before copy, partial copy, copied-before-verification, verified-before-publication, published-before-cleanup and during cleanup. Reopening the database and resuming retains or recovers the verified generation. Process-crash recovery is tested; device power-loss behavior and filesystem durability on real Windows/macOS/storage fabrics remain unvalidated. POSIX directory fsync is used where available; files and SQLite are synchronized on all supported hosts. Interrupted scratch/orphan files are retained or scoped to the owned temporary attempt, never globally swept.

## Planning and telemetry

Roles cover control metadata, journal, FTS, locators, vectors, corpus, cache, telemetry, history, backup and archive. Role defaults distinguish random interactive reads from sequential background work. Placement admits only supported writable targets with known locality, sufficient capacity, requested durability/failure-domain and measured operation costs. Interactive minimizes measured p95; background/bulk maximizes measured throughput after constraints. Unknown durability, write amplification or archive capacity cost refuses the corresponding requirement. There is no blended score and no archive price invented from device class.

`ExecutionPlanner` binds scope/source generation, representation, target, CPU/GPU encoder, scorer, read mode, transfer bytes, workload and explicit fallback. Execution revalidates the plan, uses the existing complete-profile scheduler and checks returned generation. Reference stays pinned; auto-safe retains strict gates; throughput retains complete profiles and disclosed drift. An execution plan does not relocate data.

`PhysicalTelemetry` records requested/read/written bytes, read amplification, access mode, transfer/staging/cache observations and migration bytes. Unobserved write amplification and cache levels stay null. Physical reads, migration and cache replicas cannot create semantic hits or modify activity/validity/tier. Regression fixtures compare database contents before and after physical access.

## Operator surfaces

Use `python -m thm storage` (also installed as `thm storage`). Every command accepts `--json` and `--output`; output files are exclusive. `benchmark` and `profile` require an output file. `export`, `migrate` and `plan` accept `--dry-run`; planning is always advisory.

```sh
python -m thm storage probe --root /existing/storage --json
python -m thm storage doctor --root /existing/storage --json
python -m thm storage benchmark --root /existing/storage --seconds 5 --scratch-mib 8 --output /fresh/storage-cost.json --json
python -m thm storage profile --root /existing/storage --output /fresh/storage-profile.json --json
python -m thm storage plan --root /existing/storage --storage-profile /fresh/storage-cost.json --role vector_segment --capacity 1048576 --dry-run --json
python -m thm storage placements --db /existing/index.sqlite --json
python -m thm storage export --db /existing/index.sqlite --scope example --profile-id ep1-EXACT --root /existing/storage --read-mode mmap --json
python -m thm storage verify --db /existing/index.sqlite --scope example --profile-id ep1-EXACT --json
python -m thm storage migrate --db /existing/index.sqlite --scope example --profile-id ep1-EXACT --root /existing/target --journal /fresh/migration --json
```

Resume the last command with `--resume`, the same explicit target/scope/profile and retirement intent. A dry-run only describes intent; verification and publication gates run during execution.

Microbench defaults are 8 MiB and five seconds; hard admitted limits are 128 MiB, 60 seconds and concurrency 1/2/4. Reads cover 4/16/64/256 KiB and 1 MiB, random/sequential buffered and mmap. Only one bounded scratch file is written. Timing includes OS-managed cache; cold-cache measurements are unavailable. No page-cache dropping, remounting, drive cache changes, governor/power changes or endurance workloads are performed. An in-flight kernel I/O cannot be preempted by a Python loop; the microbench is not a real-time deadline guarantee.

## Bounded local verification

| Mode | LME | Other work | Default wall ceiling |
| --- | --- | --- | --- |
| smoke | First 2 pinned instances | Tiny synthetic retrieval/parity, probes, preparation, at most 2 autotune candidates, CPU reference and strict winner | 300 seconds |
| acceptance (default) | First 5 pinned instances | LoCoMo reference/winners, at most 6 autotune candidates, parity | 3,600 seconds |
| full-research | Full pinned dataset | Requested extended A/B, winners and diagnostics | Explicit budget; acknowledgement mandatory |

Fixed pilots measure throughput before matrices. LoCoMo uses one full conversation pilot; LME uses two/five instances. Projection extrapolates measured reference time conservatively to each arm; winner speed is explicitly unmeasured. It is an estimate, not a guarantee for heterogeneous inputs. A projection exceeding the remaining budget refuses the campaign. The CLI watchdog additionally bounds the entire owned process tree, including backend preparation and autotune. Interrupted artifacts remain; output namespaces cannot be reused. A subset always has `full_dataset_acceptance=false`.

Recommended short command (existing local model and pinned datasets required):

```sh
python research/runtime/verify.py --mode smoke --model-path /local/model --model-id sentence-transformers/all-MiniLM-L6-v2 --locomo-dataset /local/locomo10.json --lme-dataset /local/longmemeval_s.json --output-dir /fresh/thm-smoke
```

Omit `--mode smoke` for bounded acceptance. Full research is optional and is not run during this implementation:

```sh
python research/runtime/verify.py --full-campaign --acknowledge-multi-hour-run --wall-seconds 43200 --retrieval-ab --model-path /local/model --model-id sentence-transformers/all-MiniLM-L6-v2 --locomo-dataset /local/locomo10.json --lme-dataset /local/longmemeval_s.json --output-dir /fresh/thm-full
```

43,200 seconds is a ceiling, not a measured estimate. `runtime-estimate.json` provides measured throughput and projected reference/winner/LoCoMo/total seconds and matrix artifact count. No runtime number is claimed before that pilot exists.

Reference sidecars bind exact dataset bytes/subset, local model manifest, backend/device/precision/package settings, reference policy, semantic implementation closure, counter identity and protocol revision. `--reference-dir /previous/run` only reuses matching reference artifacts; stale keys/checksums fail. Receipts carry `reused=true`, source artifact SHA, complete key and provenance. Reference-reuse protocol 3 uses the deterministic path/SHA manifest in `research/runtime/reference_dependencies.py`: both runner roots, transitive local imports (including lazy imports and package initializers), and the isolated subprocess worker are covered. This includes document/source construction, evidence scoring, retrieval/ranking/packing, tokenizer implementation and the installed tiktoken version. New local imports are followed automatically; unresolved imports fail closed. Three explicitly documented worker calibration/conversion import edges are excluded from the reference serve path. Documentation, storage probes, physical microbenchmarks and unrelated scheduler changes do not invalidate the semantic key. Pilots and measured winners remain separate new evidence.

Windows locality uses the resolved disk's public [MSFT_Disk BusType](https://learn.microsoft.com/en-us/windows-hardware/drivers/storage/msft-disk), accepting both numeric CIM JSON values and enum names. NVMe, SATA, SAS and USB admit `local_only` placement when other constraints and measured costs pass. iSCSI/Fibre Channel are remote; SCSI, RAID, virtual, Storage Spaces, missing or multiply resolved disks remain unknown. Friendly names never prove locality.

macOS first resolves the containing mounted volume with `df -P` before calling `diskutil info -plist`; an ordinary descendant storage directory is not passed as diskutil's device operand. The parser preserves spaces in mount names and permits APFS mount paths outside the apparent directory ancestry. It uses explicit diskutil bus protocol evidence for local PCI-Express/NVMe/SATA/SAS/USB/Thunderbolt targets. Network protocols remain remote; unknown protocols, disk images and explicitly virtual devices stay unknown. Product names and the internal/external location alone do not establish local backing.

Real Z6 G4 performance, the full LME matrix, specialized storage transports and retrieval-feature quality gains remain post-merge measured evidence. They do not block correctness-safe Unreleased merges. See the [repository reconciliation receipt](../reports/2026-09-09-open-pr-reconciliation-closeout.md).


## Post-local corrective evidence

See the [current corrective contract and short retest](19-post-local-corrective.md). Z6 CPU/CUDA/auto-throughput and local NTFS/NVMe are machine-observed at b1f8119. Aggregate parity, strict parity, calibrated policy and post-fix acceptance remain separate claims. Auto-safe now allows a measured reference fallback; lack of acceleration does not itself fail correctness. No version/stable promotion or full-dataset acceptance is implied.
