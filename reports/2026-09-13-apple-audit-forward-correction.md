# Apple audit forward correction

This addendum preserves `reports/2026-09-13-apple-adaptation-audit.md` and the original machine observations unchanged. It corrects code interpretation and the parity gate, not the historical raw measurements.

`thm/runtime/fabric/inference.py` already implemented `CoreMLInference.load()` and `encode_many()` on the 1.5 main tree `241c0b02067c47c54a0e85622d429fc18af22c50`. The audit's sections 2.3 and 2.4 incorrectly classified CoreML as a catalog-only seam. Correct classification: **CoreML executable adapter implemented; actual hardware/ANE placement unvalidated**. `CPU_AND_NE` is a requested compute-unit constraint; it does not prove ANE operator execution.

The old `research/recall/mps_parity.py` used `min_cosine >= parity_tol`. At `parity_tol=0.0001`, that did not test near-unit cosine agreement. The corrected gate requires `1-min_cosine <= cosine_tolerance`, bounded absolute error, finite values, and identical top-k ordering. Receipt schema 2 binds model manifest, before/after load identities, dependency versions, platform and batch size. Both encoders load a validated private snapshot instead of reopening the mutable model input.

The reported minimum cosine **0.9999998808**, maximum absolute error **1.825e-7**, identical top-five order, CPU **61.0 ms**, MPS **26.1 ms** and **2.34×** embedding speedup remain historical observations for MiniLM/fp32/batch64 on that machine. Those summary values satisfy the corrected arithmetic thresholds. This addendum is a recomputation from reported values, **not a new hardware run**, sustained-performance admission, or end-to-end retrieval speedup.

The BEAM **28.5%** result used zero-generative-model sparse retrieval followed by external answer generation and a judge. It is an agent answer/judge baseline; it is not a fully zero-LLM campaign or direct evidence-recall measurement. The original LoCoMo, LME-S and BEAM reports retain their identities and denominators.
