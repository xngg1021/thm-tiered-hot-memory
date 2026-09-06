# THM 1.2: retrieval, observation, decay and measurement

This is a THM-only extension. The tested 1.1.1 index-maintenance CLI remains in `scripts/thm.py`; its source files, pin protection and migration semantics are not rewritten. The `thm` package adds source retrieval and measurement. There is no second implementation of its index-maintenance engine.

## Commands

Run from the repository root with Python 3.10+:

```bash
python -m thm --help
python -m thm import-files ./example-notes --db ./test-state/recall.sqlite3 --scope demo
python -m thm import-hermes ./test-profile/state.db --db ./test-state/recall.sqlite3 --scope demo
python -m thm search --db ./test-state/recall.sqlite3 --scope demo 'Which database port?' --budget 600
python -m thm curves
python -m thm index --mem-dir ./test-profile/memories audit
python -m thm plan --mem-dir ./test-profile/memories --date 2026-09-06 --budget 600 --kernel bounded_power
```

File and Hermes imports refresh their own source kind without removing the other kind. JSONL import explicitly replaces one complete scope. All imports write a separate derived SQLite index, never the native memory files or source `state.db`. Refresh an imported source after changes; this version does not claim automatic upstream deletion propagation. Do not use a stale exported copy as current truth.

The Hermes adapter checks the observed schema, reads conversational active rows, excludes compressed-summary rows and hidden sessions, rejects a database containing multiple profile names, and returns explicit partial-read metadata. Partial imports are refused. No installed SessionDB code, migration or repair routine is invoked. Legacy schemas lacking these required fields need a separately tested adapter or a normalized JSONL export.

## Recall modes and budget

`literal` uses an unstemmed OR query over raw question terms as a reproducible baseline. It is not an oracle and does not reproduce an unavailable user script. `sparse` uses FTS5 Porter stemming, stopword removal for candidate generation, speaker-aware content queries, light adjacent-turn indexing and reciprocal-rank fusion. Chinese text also has a simple character-bigram channel. None of these are a trained semantic encoder.

`dense` and `hybrid` use an explicitly selected on-disk sentence-transformer. Hybrid combines lexical and dense candidate ranks. Model downloads are never performed by the sentence-encoder class; the benchmark workflow has a separate, explicit download step. Every embedding is tied to source and model identity, and query vectors are cached in bounded process memory. A missing/stale vector index fails rather than pretending to have run semantic search.

```bash
python -m pip install -e '.[tokenizer,semantic]'
python -m thm embed --db ./test-state/recall.sqlite3 --scope demo --model-path ./models/encoder --model-id local-encoder-revision
python -m thm search --db ./test-state/recall.sqlite3 --scope demo 'database port' --mode hybrid --counter cl100k_base --budget 600 --model-path ./models/encoder --model-id local-encoder-revision
```

The default `utf8_bytes` counter measures bytes, NOT estimated model tokens. Explicit `cl100k_base` uses that reference tokenizer; it is not a claim about any other model's tokenizer. Tiktoken can populate its vocabulary cache on first use. Header/speaker/date/separator text counts toward the same context budget. Whole source turns are packed; an oversized turn is skipped without terminating the remaining search. A candidate ID is never counted as observed evidence unless its complete text is actually included. `--neighbors 1` explicitly budgets adjacent text rather than receiving free evidence credit.

Returned timings separate lexical retrieval, query encoding, combined retrieval and context packing. They exclude source ingestion and model loading, which are measured separately. These values do not establish user-perceived latency or time to first answer token. Full model-request budgeting still belongs to the host; the caller allocates this bounded evidence slice.

## Scan without feedback fabrication

`scan` generates `mention_observed` records with weight zero. It never calls `hit` or `confirm`, never extends validity, and does not write `index.json`. An anchor file is a JSON list containing `id`, `version`, `aliases`, optionally `valid_from`, `valid_until`, `min_anchors` and `case_insensitive`.

```bash
python -m thm scan --state-db ./test-profile/state.db --scope demo --anchors ./anchors.json --now 2026-09-06T12:00:00+00:00 --save-observations ./test-state/observations.sqlite3
```

Matches have session/message identity, timestamp, source-text fingerprint, filtered-text coordinates and rule version. A match is not proof of use. An unavailable historical memory snapshot is reported as exposure unknown. No mention is not evidence of uselessness. Duplicate copied messages are not new observations; weekly candidates require distinct days and sessions. Code/quotes and recognizable review echoes are excluded conservatively, but this is not a full semantic negation, attribution or prompt-injection detector. The default report contains counts rather than memory text. Observation storage is local and may still contain sensitive anchors/metadata.

## Decay and residency

Available alternatives include the historical power curve, half-life-calibrated power and exponential curves, a two-timescale mixture, bounded-window/day-capped power, LRU and LFU. Mention, display, retrieval and relocation carry zero activity weight. Validity and explicit pinning precede score. A pinned over-budget set returns an explicit conflict. Ranking uses a deterministic value-per-unit greedy rule, not a claimed optimal knapsack solution.

```bash
python research/recall/decay_replay.py --sweep --output ./test-state/decay.json
```

The default workload is explicitly synthetic. Selection occurs on the first half of chronological requests and is reported on the second half; requests are scored before their use event is observed. LoCoMo question order is never treated as a history of actual uses. No selected curve is auto-installed. Better decay on one synthetic workload does not establish an optimum for a user.

## Optional Hermes integration

Install the package editable from this repository, and copy `plugins/thm` into the active profile's plugin directory. Set `THM_RECALL_SCOPE` to a scope already imported into `<hermes_home>/memories/.thm/recall.sqlite3`. Select the external provider according to the installed Hermes version. No installer or configuration switch runs automatically in this project.

The adapter implements the public MemoryProvider surface. `prefetch` retrieves for the current query; session switching clears prior recall status; `on_memory_write` is not a hit. It does not run a second generation model, auto-export conversations, or claim the v2 pre-compression checkpoint contract. It occupies the host's external-provider slot. Unit tests use a contract double; actual installed-host lifecycle and real-model behavior require a separately recorded integration run.

## Generation evaluation

`thm.answer_eval.local_answer` optionally invokes an explicit loopback-IP chat-completions endpoint. Remote hosts, proxies and redirects are refused. There is no default call and no cloud credential requirement. `exact_f1` provides transparent lexical answer metrics, not semantic judgment. The repository does not claim an LLM judge is necessary for every evaluation or promise a price for an unspecified model.

## Public technical sources

- SQLite FTS5 query syntax, Porter tokenizer and BM25: https://www.sqlite.org/fts5.html
- SQLite read-only URI semantics: https://sqlite.org/uri.html
- Cormack, Clarke and Buettcher, SIGIR 2009, reciprocal rank fusion: https://doi.org/10.1145/1571941.1572114
- Sentence Transformers local loading options: https://sbert.net/docs/package_reference/sentence_transformer/model.html
- Hermes interface/schema reviewed at `089bb32886c8c18f7fa20182c7bf8826d6935ac5`: `agent/memory_provider.py`, `hermes_state_common.py` in NousResearch/hermes-agent.

These are public interface and method references; no other private project implementation is an input to this extension.
