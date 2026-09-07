# THM × Context Economics — machine-test v2r1 canonical closeout

## Identity

Repository: xngg1021/thm-tiered-hot-memory

Base main: `11b79c127164feae9b6e621e542f54a22e9dd1ca`; base tree: `149b2c83b54a9e10de3380a40895ae5e023ebe4e`; base parent: `bdaa6cc031fabf04242d51ccc6647c2532f38126`.

Predecessor: merged PR #11, merge `7ae6f1a7a1841c54bff2f16c079b83a1b3d4735e`. Successor branch: `work/machine-test-evidence-v2-final-closeout-20260908`. Archive stable remains `e6e4dda5835e3cb345207457d5491131c6959b2c`.

Final branch HEAD/tree/parents, merge identity and exact-head validation are recorded in the PR closeout comment after the last commit (a committed file cannot contain its own final commit/tree hash). This file is the evidence entry point, not an assertion of an as-yet unobserved merge or CI result.

Context Economics commit: `2aef1e7043273637adff1453d22dafc83d5e0e94`; model.py SHA: `8a80417468f138268db99784420f414add0fc1c213f6511de99142da0742affd` (original CRLF bytes; see regeneration notes).

Source retrieval artifact SHA: `05c321bd758ff6743843898fcc1aa040d0cf75090f498525ab6ea7fb57eae1c8`.

Dataset SHA: `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`; upstream commit: `3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376`.

## Accepted retrieval evidence

LoCoMo main categories 1–4: 1540 attempted/config, 1532 canonical scorable/config, 18480 config-query executions, 18384 scorable executions. No-gold and unresolved rows are excluded from scoring. Runtime-measured retrieval coverage only; generation_calls=0, judge_calls=0.

| Hybrid budget | Any-gold hits | Coverage |
|---|---:|---:|
| 300 | 903 | 58.9426% |
| 600 | 1093 | 71.3446% |
| 1200 | 1239 | 80.8747% |

LME GPU v2 contains selected_ids and selected_sources for 500 instances across the recorded grid. Gold uses official answer_session_ids: session-level coverage, not LoCoMo turn-level accuracy. CPU v2 is pending-real-local-runtime; neither positive nor negative LME strict parity is established.

## Economics

All costs are model-proxy, not observed provider bills. Packed and full-history compare the same attempted queries. The 12-arm suite costs $8.347215 at the primary offpeak rho=0 scenario; it is an experiment total, not one deployed policy. Delta audit verifies unchanged packed tokens, full-history tokens, pricing, ratios and absolute any-gold hit counts in every configuration.

| Hybrid budget | Full/packed cost ratio, rho=0 |
|---|---:|
| 300 | 64.6978x |
| 600 | 31.5277x |
| 1200 | 15.5744x |

| Interval | Any-gold gain | USD / +1pp |
|---|---:|---:|
| 300->600 | 12.4021pp | $0.024613 |
| 600->1200 | 9.53pp | $0.063994 |

Late/early marginal ratio: 2.6000x. 600 is a tested-grid knee candidate only; no global optimum or chronological O(N²) claim.

## Hardware parity

Aggregate semantic metrics equivalent: **true** (1680 explicit retrieval-quality and budget-use summary fields compared, excluding timing and environment). Strict selected-document semantics equivalent: **false**. All 23832 CPU/GPU rows compared at float tolerance 0; maximum checked numeric delta 0.0.

| Measured quantity | Count |
|---|---:|
| Mismatch entries | 25 |
| Mismatching rows | 22 |
| Rank-only rows | 19 |
| Selected-set substitution rows | 3 |
| Main categories 1–4 mismatch rows | 16 |
| Diagnostic category 5 mismatch rows | 6 |

The canonical parity receipt is now `2026-09-08-locomo-cpu-gpu-parity-v2r6.json`, generated after the review corrections. It includes mean_budget_used, validates complete summary schema and binds hashes to the exact parsed buffers. The v2r1 through v2r5 receipts are preserved as prior attempts. The new preview limit is 50; all 25 entries fit, so it is not truncated. The older cap of 25 did not prove the total even though the complete scan now happens to find exactly 25. Per-mode/budget/category counts are in the successor JSON. Near-tie floating-point drift is an inference only: no candidate score/delta trace proves causality. No ranking/tie-breaking/embedding semantics changed.

## Superseded artifacts

| Preserved prior artifact | Canonical successor |
|---|---|
| 2026-09-08-economics-bridge.json | 2026-09-08-economics-bridge-v2r1.json |
| 2026-09-08-suite-report.md | 2026-09-08-suite-report-v2r1.md |
| 2026-09-08-economics-bridge-v2.json (1536 denominator) | 2026-09-08-economics-bridge-v2r1.json (1532) |
| 2026-09-08-suite-report-v2.md (mixed denominator) | 2026-09-08-suite-report-v2r1.md |
| 2026-09-08-locomo-cpu-gpu-parity.json (capped preview) | 2026-09-08-locomo-cpu-gpu-parity-v2r6.json |
| 2026-09-08-locomo-cpu-gpu-parity-v2r1.json (before review hardening) | 2026-09-08-locomo-cpu-gpu-parity-v2r6.json |
| 2026-09-08-locomo-cpu-gpu-parity-v2r2.json (omits mean_budget_used) | 2026-09-08-locomo-cpu-gpu-parity-v2r6.json |
| 2026-09-08-locomo-cpu-gpu-parity-v2r3.json (before strict-row coverage hardening) | 2026-09-08-locomo-cpu-gpu-parity-v2r6.json |
| 2026-09-08-locomo-cpu-gpu-parity-v2r4.json (before range validation) | 2026-09-08-locomo-cpu-gpu-parity-v2r6.json |
| 2026-09-08-locomo-cpu-gpu-parity-v2r5.json (before canonical aggregate-count binding) | 2026-09-08-locomo-cpu-gpu-parity-v2r6.json |

Additional evidence: `2026-09-08-economics-v2r1-delta-audit.json`; LME GPU evidence remains `2026-09-08-lme-retrieval-gpu-v2.json`. Historical artifact bytes remain unchanged. Regeneration notes are forward-corrected with retained defect history.

## Review corrections

First exact-head Codex review raised four P2 items: legacy README commands could overwrite evidence; aggregate summary completeness was not required; aggregate numeric differences were absent from the maximum delta; parity hashing reread source paths after parsing. All were forward-fixed with regression coverage. Standalone outputs now use exclusive creation, reads hash and parse one buffer, complete known runner schemas are checked, and aggregate deltas update the maximum. The new parity receipt retains the measured counts above, with no coverage errors. Economics/report were regenerated into temporary fresh files using the hardened readers and are byte-identical to the committed v2r1 artifacts. CPU optimization follow-up: [issue #13](https://github.com/xngg1021/thm-tiered-hot-memory/issues/13).

Second-round review identified one additional P2: mean_budget_used was missing from the non-timing aggregate schema. It is now required and compared, with missing-field and aggregate-delta tests. The v2r3 receipt compares 1680 fields, including budget use, and retains all measured mismatch counts.

Third completed review raised three further P2 items: ranked identities must be mandatory for Protocol 2; every measured row must belong to the declared aggregate grid; rank-only must exclude mixed semantic changes. These are forward-fixed with protocol-specific required row fields/valid values, grid coverage and disjoint rank-only/selected-set/other-semantic classification tests. The v2r4 receipt has complete row and aggregate coverage, retains 25 entries / 22 rows (19 rank-only, 3 selected-set), and reports 0 other-semantic rows. Synthetic LME tests require its ordered IDs and aligned source list without inventing a real CPU result.

Fourth completed review raised two P2 items: normalized score ranges and the local LME output race. Row reciprocal-rank/nDCG and aggregate normalized metrics now require [0,1], with typed nonnegative aggregate counts. Both LoCoMo and LME standalone runners perform output preflight and exclusive final creation; a race regression creates another writer's artifact after preflight and confirms preservation. Retrieval/embedding/ranking logic is unchanged. The v2r5 receipt is regenerated under these checks and retains the measured results.

Fifth completed review identified one P2: any_gold_hits must be bounded by the scorable cohort. Aggregate availability now binds questions/scorable/no-gold/partial-unresolved/any-gold counts directly to each cohort's rows using the shared canonical scoring predicate, and checks the corresponding any-gold rate. This enforces both the scorable upper bound and cohort partition relationships. Malformed 10-attempt/1-scorable/10-hit summaries and related count/rate changes are regression-gated. v2r6 retains all real measured results.

## Validation contract

Real TokenCounter + synthetic LoCoMo conversation path and bridge smoke; canonical no-gold/unresolved predicates; bridge/report denominator and suite totals; parity preview vs total, rank-only vs set substitution, aggregate vs strict, missing selected IDs, numeric differences; portable input preflight. Full correctness: unit discovery, numeric audit, docs, version history, whitespace, Ubuntu/macOS/Windows CI. Exact final CI/review receipts belong to the PR closeout; merge requires both green CI and clean exact-head Codex review.

## Remaining blockers

Only hardware evidence blocker: **LME CPU v2 pending-real-local-runtime** on the user's HP Z6 G4 / Xeon Gold 6254 / RTX 3080 10GB. No cloud CPU run is represented as this machine. The local run must use the same model directory that produced GPU v2; the historical artifact records a model ID, not a file-manifest hash, so model weight identity cannot be independently reconstructed from that ID alone.

From the final merged checkout on that Z6, paste this PowerShell block. It prompts for the existing dataset file and the same model directory, verifies dataset bytes and uses the repository's recorded model ID and grid. It atomically reserves the output tag before running; both the LME runner and parity CLI additionally create their actual outputs exclusively, refusing pre-existing or concurrently created artifacts. Interrupted runs retain the reservation; select a fresh suffix for a retry.

```powershell
$ErrorActionPreference = 'Stop'
$datasetFile = (Read-Host 'Full path of the existing longmemeval_s JSON file').Trim('"')
$modelDir = (Read-Host 'Full path of the same model directory used for GPU v2').Trim('"')
if (!(Test-Path -LiteralPath $modelDir -PathType Container)) { throw 'Model directory missing' }
$gpuFile = 'reports/2026-09-08-lme-retrieval-gpu-v2.json'
$gpu = Get-Content -Raw $gpuFile | ConvertFrom-Json
if ((Get-FileHash -LiteralPath $datasetFile -Algorithm SHA256).Hash.ToLower() -ne $gpu.dataset_sha256) { throw 'Dataset SHA mismatch' }
$cpuFile = 'reports/2026-09-08-lme-retrieval-cpu-v2.json'
$parityFile = 'reports/2026-09-08-lme-cpu-gpu-parity-v2r1.json'
if ((Test-Path $cpuFile) -or (Test-Path $parityFile)) { throw 'Output already exists; choose a fresh suffix' }
$reservation = [System.IO.File]::Open("$cpuFile.reserved", 'CreateNew', 'Write', 'None')
$reservation.Dispose()
python research/recall/lme_retrieval.py --dataset "$datasetFile" --counter cl100k_base --modes $gpu.modes --budgets $gpu.budgets --model-path "$modelDir" --model-id $gpu.model_id --threads 16 --device cpu --batch-size 64 --output $cpuFile
if ($LASTEXITCODE -ne 0) { throw 'LME CPU run failed; reservation retained' }
python research/recall/hardware_parity.py --cpu $cpuFile --gpu $gpuFile --output $parityFile
if ($LASTEXITCODE -gt 1) { throw 'Parity command failed' }
# Exit 1 with a written parity receipt means strict parity false, not a successful equivalence.
Get-Content -Raw $parityFile
```

Record `git rev-parse HEAD`, `git status --porcelain`, Python/package versions, model file manifest and actual machine identity alongside the new CPU run. Any model/runtime/source mismatch must be reported before interpreting parity. CPU embedding optimization belongs in the separate follow-up planning issue; no performance improvement is claimed here.
