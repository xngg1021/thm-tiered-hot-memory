# THM PR #14 post-merge local runtime acceptance — Z6 G4

Status: **CODE MERGED / REAL LOCAL HARDWARE ACCEPTANCE PENDING**

Date: 2026-09-08

Repository: `xngg1021/thm-tiered-hot-memory`

PR: `#14` — `Unreleased zero-LLM heterogeneous runtime and local acceptance package`

Source head: `0b90efe54de3a39d2021540575fcb012753cceed`

Source tree: `85867f7cc81e321680238fba1e6d904f998bc9db`

Merge commit: `e6227cc5f6308bc2903222adfdbb1ee814053938`

Predecessor main: `9eb904c21fd25aa0a77d2420ed080702fac17e59`

Stable archive remains unchanged: `archive/v1.4.0-stable@e6e4dda5835e3cb345207457d5491131c6959b2c`

Package line remains `1.4.0`; the heterogeneous runtime and retrieval successors remain **Unreleased** until separate release/acceptance work says otherwise.

## 1. What the merge establishes — and what it does not

The PR source head completed 393 local regression tests. Exact-head correctness was green on Ubuntu/Python 3.10, macOS/Python 3.13 and Windows/Python 3.13, including the unit suite, numeric audit, documentation checks, version-history checks, whitespace checks and core-only headless ignition. The exact-head PR correctness run is `34200520158`; the corresponding push run is `34200514166`.

Across the completed review history before merge, 45 actionable findings were forward-fixed and resolved: 1 P1 and 44 P2. The final source-head corrections calibrate scorer work using the configured query chunks and accept Hermes-style ISO datetime source timestamps before explicit English/date grammar fallback.

The merge establishes the code path and its software contracts. It **does not** establish any of the following:

- a speedup on the local Xeon Gold 6254 or RTX 3080;
- actual AVX2, AVX-512, VNNI, CUDA, ORT or OpenVINO dispatch on this machine;
- strict CPU/GPU semantic equivalence beyond what a generated parity receipt measures;
- safety/equivalence of an approximate-performance profile;
- quality gain from temporal, alias, segment or association retrieval successors;
- default admission of any new retrieval successor;
- a new stable archive pointer or release version.

Those claims require the real local measurements below.

The earlier `reports/2026-09-08-local-runtime-verification-plan.md` is retained as the historical pre-merge contract. Its dataset pins, clean-tree requirement, fresh-output rule, no-download boundary and evidence semantics remain useful. Its statements requiring PR #14 to remain unmerged are superseded by the user-authorized merge above.

## 2. Target machine

The intended first local acceptance machine is:

- HP Z6 G4;
- Intel Xeon Gold 6254, Cascade Lake, 18 physical cores / 36 logical threads;
- NVIDIA RTX 3080 10 GB;
- hardware family expected to support AVX2, AVX-512 and VNNI;
- native BF16 and AMX are not expected on this CPU generation.

These labels are **expectations, not runtime evidence**. `thm runtime probe`, the installed libraries and any imported profiler evidence are authoritative for the execution actually observed. THM must not modify BIOS settings, Windows power plans or other machine-global policy as part of this verification.

## 3. Dataset pins

Use the exact local dataset bytes already used by the THM machine-test lineage.

| Dataset | Required SHA-256 |
| --- | --- |
| LoCoMo `locomo10.json` | `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4` |
| LongMemEval-S JSON | `08d8dad4be43ee2049a22ff5674eb86725d0ce5ff434cde2627e5e8e7e117894` |

A filename match is not enough. A digest mismatch is a different experiment.

## 4. Obtain the merged code

For a new checkout:

```powershell
$ErrorActionPreference = 'Stop'
git clone https://github.com/xngg1021/thm-tiered-hot-memory.git
cd thm-tiered-hot-memory
git checkout main
git pull --ff-only

git merge-base --is-ancestor e6227cc5f6308bc2903222adfdbb1ee814053938 HEAD
if ($LASTEXITCODE -ne 0) { throw 'PR #14 merge is not present in this checkout' }

if (git status --porcelain) { throw 'Checkout must be clean before verification' }
git rev-parse HEAD
```

For an existing checkout, use `git fetch origin`, switch to `main`, and `git pull --ff-only`. Do not reset, rebase or force the local branch merely to run this acceptance.

The local `HEAD` may be newer than `e6227cc...` because documentation-only successors can follow the merge. The required condition is that `e6227cc...` is an ancestor and the checkout is clean.

## 5. Create an isolated Python environment and install optional local runtimes

Example using a normal virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[tokenizer,semantic-torch,semantic-onnx,semantic-openvino]"
```

This does not guarantee CUDA execution. If CUDA is part of the test, the Python environment must already contain a PyTorch build compatible with the installed NVIDIA driver/runtime. THM does not own system CUDA installation and this runbook intentionally does not prescribe a global CUDA or driver change.

Check what PyTorch actually sees:

```powershell
python -c "import torch; print('torch', torch.__version__); print('cuda build', torch.version.cuda); print('cuda available', torch.cuda.is_available()); print('device', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO CUDA')"
```

A missing optional backend should be recorded as missing/failed capability, not silently converted into evidence for another backend.

## 6. Bind the local inputs and verify their hashes

Use paths outside the Git checkout for datasets, the local model and output artifacts.

```powershell
$ErrorActionPreference = 'Stop'

$model  = (Read-Host 'Existing local SentenceTransformer model directory').Trim('"')
$locomo = (Read-Host 'Pinned locomo10.json full path').Trim('"')
$lme    = (Read-Host 'Pinned LongMemEval-S JSON full path').Trim('"')
$output = (Read-Host 'Fresh baseline output directory OUTSIDE the checkout').Trim('"')

$locomoHash = (Get-FileHash $locomo -Algorithm SHA256).Hash.ToLower()
$lmeHash = (Get-FileHash $lme -Algorithm SHA256).Hash.ToLower()

if ($locomoHash -ne '79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4') {
    throw "LoCoMo SHA mismatch: $locomoHash"
}
if ($lmeHash -ne '08d8dad4be43ee2049a22ff5674eb86725d0ce5ff434cde2627e5e8e7e117894') {
    throw "LongMemEval-S SHA mismatch: $lmeHash"
}
if (Test-Path $output) {
    throw 'Baseline output directory already exists; choose a fresh namespace'
}
```

The verification package intentionally refuses to reuse an output directory. A failed run is evidence and should be preserved; retry into a new namespace rather than overwriting it.

## 7. Preflight the merged software before the expensive run

```powershell
python -S scripts/runtime_headless_probe.py
python -m unittest discover -s tests -v
python -m thm runtime doctor
python -m thm runtime probe
```

Record the output. Do not treat an ISA reported by the CPU model name as proof that a selected backend actually dispatched that ISA. The runtime doctor/probe distinguishes observed capabilities where the installed stack can report them; actual kernel dispatch remains unknown unless a profiler/dispatcher receipt observes it.

The verification run requires a clean source checkout. Keep receipts and experimental outputs outside the repository tree.

## 8. Optional plan-only pass

`research/runtime/verify.py` reserves its output directory even in plan-only mode, so use a separate fresh namespace:

```powershell
$planOut = "$output-plan"
if (Test-Path $planOut) { throw 'Plan output already exists; choose a fresh namespace' }

python research/runtime/verify.py `
  --model-path "$model" `
  --model-id "sentence-transformers/all-MiniLM-L6-v2" `
  --locomo-dataset "$locomo" `
  --lme-dataset "$lme" `
  --output-dir "$planOut" `
  --retrieval-ab `
  --max-candidates 12 `
  --plan-only
```

Use the plan to inspect candidate generation and expected outputs. A plan-only result is not performance evidence.

## 9. Recommended first full acceptance run

Do **not** require approximate-performance in the first baseline. `--include-approximate` makes an approximate winner part of run completeness; a machine where the optional low-precision path is unsupported should not invalidate otherwise complete reference/auto-safe/auto-throughput evidence.

Run the reference, strict auto-safe, throughput and independent retrieval A/B package first:

```powershell
python research/runtime/verify.py `
  --model-path "$model" `
  --model-id "sentence-transformers/all-MiniLM-L6-v2" `
  --locomo-dataset "$locomo" `
  --lme-dataset "$lme" `
  --output-dir "$output" `
  --retrieval-ab `
  --max-candidates 12

if ($LASTEXITCODE -ne 0) {
    throw 'Baseline verification incomplete; preserve this output and retry only into a NEW fresh directory'
}
```

The one-shot package probes actual hardware, prepares only installed local backends, calibrates bounded candidates, runs isolated LoCoMo and LongMemEval-S matrices, compares required runtime profiles, emits score/parity diagnostics, and executes the default-off retrieval successor A/B separately from the runtime-performance comparison.

No provider/generative LLM call is part of the intended verification path.

## 10. Optional approximate-performance run

Run approximation as a separate experiment after the baseline has been preserved:

```powershell
$approxOutput = (Read-Host 'Fresh approximate output directory OUTSIDE the checkout').Trim('"')
if (Test-Path $approxOutput) { throw 'Approximate output already exists; choose a fresh namespace' }

python research/runtime/verify.py `
  --model-path "$model" `
  --model-id "sentence-transformers/all-MiniLM-L6-v2" `
  --locomo-dataset "$locomo" `
  --lme-dataset "$lme" `
  --output-dir "$approxOutput" `
  --include-approximate `
  --max-candidates 12
```

Do not label an approximate profile equivalent to the reference merely because aggregate retrieval metrics happen to match. Its precision/backend/profile identity remains distinct.

## 11. Acceptance reading rule

Start with `comparison.json` in the baseline output directory.

A complete measured package should have:

- `status` equal to `measured-needs-acceptance`;
- `missing_required_winners` empty;
- required execution return codes equal to zero;
- reference artifacts present;
- strict auto-safe full-matrix semantic/parity gates passing before it is considered a safe automatic candidate.

The verification runner may retain a historical field such as `merge_authorized: false`. After `e6227cc...`, that field is an experiment-package guard inherited from the pre-merge contract; it is **not** the repository's current merge state. The repository merge identity is the Git history above.

Interpret policies separately:

- `reference`: fixed reference execution identity for reproducibility;
- `auto-safe`: fastest calibrated candidate satisfying the strict semantic gate used by the package;
- `auto-throughput`: throughput-oriented profile; any measured semantic/identity drift must remain explicit and it must not be relabeled as reference execution;
- `approximate-performance`: separate low-precision/performance experiment, never silently equivalent to the baseline.

For the default-off retrieval successors, compare only the same Protocol 2 denominators/budgets and preserve their conservative evidence-credit semantics. A feature remains default-off unless its own held-out evidence justifies a later admission decision.

## 12. What to inspect after the run

At minimum review:

1. `hardware.json` — observed machine/runtime capability facts;
2. `comparison.json` — completeness, required winners and top-level acceptance state;
3. every `*-autotune.json` — candidates, admitted/rejected status and selected metric;
4. every `*-execution.json` — exact execution/profile/backend identity and timing receipts;
5. every `*-parity.json` — semantic identity/parity comparison;
6. every `*-score-deltas.json` — aligned score/rank/cutoff drift evidence;
7. retrieval feature A/B artifacts — default-off quality experiment only;
8. stderr/stdout logs — backend failures, missing capability and fallback evidence.

Speed alone is not acceptance. Record both latency/throughput and semantic identity.

## 13. Artifacts that can be returned for audit

After a manual privacy review, the following generated artifacts are normally the useful audit set:

- `hardware.json`;
- `comparison.json`;
- `*-autotune.json`;
- `*-execution.json`;
- `*-parity.json`;
- `*-score-deltas.json`;
- relevant text logs.

Do **not** upload by default:

- the private/local dataset files themselves;
- `derived-models/`;
- `embedding-cache.sqlite`;
- the original local model directory;
- any artifact that still contains a private absolute path, source text or other material not manually reviewed.

If a run fails, keep its entire output directory immutable. A second run should use a new directory such as `...-r2`; never overwrite the failed evidence to make the later run look like the first attempt succeeded.

## 14. What a successful local run is allowed to change

A successful run may support measured statements such as:

- this machine selected profile X under policy Y;
- backend/device/profile X measured p50/p95 or throughput Z under the pinned workload;
- CPU/GPU/profile parity did or did not satisfy the specified gate;
- a default-off retrieval successor improved, regressed or did not change a pinned metric under Protocol 2.

It still does not automatically authorize:

- moving `archive/v1.4.0-stable`;
- claiming a universal CPU/GPU speedup;
- claiming actual AVX/VNNI dispatch without observed dispatch evidence;
- enabling an approximate profile as the safe default;
- enabling a retrieval successor by default;
- claiming generated-answer accuracy from retrieval coverage.

Any of those is a separate evidence/admission decision.
