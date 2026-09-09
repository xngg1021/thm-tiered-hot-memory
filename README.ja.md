# THM — Tiered Hot Memory

**AI Agent 向けの local-first・deterministic な階層型 memory infrastructure。** THM は「何を hot に常駐させるべきか」と「何を必要時に取り戻せばよいか」を分離し、その判断を観測可能な cost と evidence で評価します。別の LLM に memory の再生成を常時依存する設計ではありません。

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | 日本語 | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

作者: Junfu Shi (SJF, xngg1021) · License: [MIT](LICENSE)

<!-- section:architecture -->
## 三つのプレーンによるアーキテクチャ

THM は論理メモリ、計算実行、物理ストレージを分離します。Evaluation Fabric は新しいメモリアルゴリズムを追加せず、三つのプレーンを計測します。どの表現でも元のソース識別子と scope が基準です。

アーキテクチャと証拠の契約

安定 package と archive は 1.4.0 を維持します。Runtime、Physical Storage Fabric、Evaluation Fabric は Unreleased です。既存の測定は元の protocol、source SHA、範囲を保持し、未実行の benchmark やハードウェアを accepted evidence に含めません。

<!-- section:machine-corrective -->
## Z6 実機証拠と修正ポリシー

Z6 G4 の検証対象 `b1f8119` では CPU reference、RTX 3080 CUDA、auto-throughput が実行され、ローカル NTFS/NVMe StorageProfile のコストが測定された。GPU 文書埋め込みは大幅に高速化し、限定 LME サブセットの全体時間も改善した。LoCoMo の集計品質は同等だが、CUDA には厳密不一致が 23 行あり、3 行で選択集合が変化した。過去の auto-safe は失敗した。修正後の許可判定は FP32 数値上限と検索構造の完全一致を分離し、加速を主張せず明示的な reference フォールバックを許可する。修正後の実機検証、AVX/VNNI の実行観測、完全 LME は未検証。

[2026-09-09 evidence](reports/2026-09-09-local-acceptance-b1f8119.md) · [Corrective contract / short retest](docs/19-post-local-corrective.md)

<!-- section:philosophy -->
## Design philosophy

### 1. Source authority を守る

Native memory file、session transcript、external source が authoritative source です。SQLite/FTS、local embedding、locator などは**derived index / projection** にすぎません。Retrieval のために source を暗黙に書き換えません。

### 2. Residency・relevance・activity を混同しない

THM は次を別々に扱います。

- **tier** — どこに resident し、どう access されるか
- **activity** — Agent が実際に使ったか
- **validity** — まだ正しく有効か
- **pinning** — operator による明示的 constraint
- **retrieval evidence** — ある task で検索経路がその item を提示したか

Mention は hit ではなく、retrieval は usefulness の証明ではありません。Prefetch は demand ではなく、write は activity event ではありません。

### 3. Cold memory は安く保つ

Hot prompt は希少です。THM は locator と bounded retrieval により、cold material を必要になるまで resident context の外に置きます。短い locator は常駐する価値があっても、full source はそうでない場合があります。

### 4. Fixed budget も correctness の一部

大きな candidate pool に gold が存在するだけでは不十分です。最終 evidence slice に固定 token budget 内で実際に pack されたかを測ります。Oversized source、duplicate evidence、packing waste も retrieval loss の一部です。

### 5. Self-reinforcing retrieval を作らない

System が自分で prefetch / retrieve した item を、それだけの理由で将来さらに重要と扱うことを禁止します。Control plane は explicit demand evidence からのみ学習し、anti-self-training boundary を維持します。

### 6. Automation は evidence の後

THM は residency / prefetch / budget の shadow recommendation を出せますが、automatic promote/demote と automatic budget write-back は、held-out task evidence が quality・cost・latency・reacquisition の改善を示すまで無効です。

### 7. One core, multiple harness surfaces

Retrieval semantics は THM core に集約します。Hermes は最も深い lifecycle integration、OpenAI Agents と LangChain は native SDK adapter、MCP は複数 CLI/harness が共有できる protocol surface です。

<!-- section:logical -->
## 論理メモリプレーン

scope 付き SearchIndex、予算内の証拠パッキング、シャドー常駐制御は同じコアを使います。T0–T3 は論理的な常駐とアクセスを表します。活動、有効性、固定、検索は別々に記録し、自動昇格と予算書き戻しは無効のままです。

<!-- section:tiers -->
## T0–T3 memory Tiers

| Tier | 役割 | 典型例 |
| --- | --- | --- |
| **T0 — Hot** | Host がすでに携帯する resident memory | 繰り返し resident value を生む小さな high-value context |
| **T1 — Warm** | 必要時に展開する locator-oriented memory | topic/file/source locator、bounded warm reference |
| **T2 — Cold** | 検索可能な local history/archive | 固定 evidence budget 内の scoped FTS/dense retrieval |
| **T3 — External** | 再取得可能な source location | file、URL、external system |

T0–T3 は **THM の memory Tier** です。別プロジェクト Context Economics の L0–L6 Layer とは独立した taxonomy です。

<!-- section:compute -->
## 計算実行プレーン

RuntimeProfile は encoder/backend、精度、デバイス、scorer、バッチサイズ、スレッドを固定します。任意のスケジューラーと有界 AutoTune が実行設定を選びます。CPU/CUDA などの記述には別途 runtime 証拠が必要で、fixture の成功は dispatch や高速化の証明にはなりません。

[Runtime](docs/17-zero-llm-heterogeneous-runtime.md)

<!-- section:physical -->
## 物理ストレージプレーン

StorageProfile は実測アクセスコスト、placement は表現とターゲットの対応、PhysicalTelemetry は実際の extent I/O を記録します。検証済みローカルファイルシステムの buffered/mmap を実装しています。CXL、DAX、SPDK、GDS、リモート転送は拡張記述であり、ハードウェア性能は未検証です。

[Physical Storage Fabric](docs/physical-storage-fabric.md)

<!-- section:evaluation -->
## Evaluation Fabric

Adapter はネイティブ入力を Task、評価器専用の GroundTruth、Result、SHA に結び付く Receipt に変換します。LoCoMo Protocol 2 と LongMemEval-S は dataplane 指標を共有し、文書単位とセッション単位の違いを保持します。LongMemEval-V2 は公開 trajectory states と insert/query、BEAM は batches/turns と probing questions、MemoryArena はサブタスクとセッション間の add/wrap_user_prompt に対応します。

Fixture はインターフェースと決定論的検索だけを検証します。V2 はテキスト専用で画像クエリを拒否します。gold locator がなければ recall は null です。MemoryArena のタスク解析は環境実行ではありません。回答と rubric は検索文書に入りません。

| 証拠レイヤー | Receipt 契約 |
| --- | --- |
| memory-dataplane | any/all-gold、macro/micro recall、親ロケータ、予算、遅延 |
| systems-runtime | 計算設定、StorageProfile、placement、I/O 計測 |
| LLM-agent-outcome | 生成・judge 呼び出し、回答精度、環境成功率；既定は not-run |

[Evaluation Fabric](docs/18-evaluation-fabric.md)

<!-- section:evidence -->
## Measured retrieval evidence

THM は retrieval evidence と answer-generation claim を分離します。

Canonical LoCoMo Protocol 2 は 1,532 fully resolved non-adversarial questions と固定 600 `cl100k_base` evidence-token slice を使います。

| Retrieval mode | Any-gold packed evidence | All-gold packed evidence | p95 retrieval + packing |
| --- | ---: | ---: | ---: |
| Literal | 56.79% | 46.61% | — |
| Sparse | **69.39%** | **56.53%** | **34.55 ms** |
| Local dense | 51.11% | 40.01% | — |
| Hybrid | **71.34%** | **57.64%** | **57.88 ms** |

現在の opt-in deterministic entity projection は full-set sparse any-gold を **69.39% → 72.52%**、frozen 1,301-question holdout を **69.56% → 72.33%** に改善し、candidate coverage は変えていません。つまり追加モデルで candidate pool を広げたのではなく、**既存 candidate を 600-token slice により良く配置した** 結果です。

これは final answer accuracy、user satisfaction、universal superiority の指標ではありません。[Protocol 2](reports/2026-09-06-recall-protocol2.md) と [zero-LLM frontier](docs/16-zero-llm-retrieval-frontier.md) を参照してください。

<!-- section:harness -->
## Harness integration

| Surface | Integration depth |
| --- | --- |
| **Hermes Agent** | Native `MemoryProvider`; setup/config, prefetch, optional live-turn sync, session boundary hooks, memory-write refresh semantics |
| **OpenAI Agents SDK** | Native read-only `FunctionTool` |
| **LangChain / LangGraph / Deep Agents** | Native `BaseRetriever` surface |
| **MCP v2** | Typed read-only `thm_recall` / `thm_status` over stdio |
| **OpenClaw** | Legacy MCP bridge を使う pinned compatibility probe |
| **Claude Code / Codex CLI / Gemini CLI** | Pinned real-CLI discovery/call lifecycle、同一 read-only recall core を利用 |

Multi-harness support は universal memory database を意味しません。Lifecycle integration の深さは host ごとに異なり、Hermes が最も深い native integration です。

<!-- section:quickstart -->
## Quick start

```bash
python -m pip install -e .
python -m thm --help

python -m thm import-files ./notes \
  --db ./state/recall.sqlite3 \
  --scope demo

python -m thm search \
  --db ./state/recall.sqlite3 \
  --scope demo \
  "Which database port?" \
  --budget 600
```

Optional dependencies:

```bash
python -m pip install -e '.[tokenizer,semantic]'
python -m pip install -e '.[openai]'
python -m pip install -e '.[langchain]'
python -m pip install -e '.[mcp]'
python -m pip install -e '.[harnesses]'
```

MCP:

```bash
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
thm-mcp-legacy --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

<!-- section:acceptance -->
## 有界ローカル受け入れ検証

リポジトリのルートで Python 3.10 以降を使います。モデル、データセットのダウンロードや provider key は不要です。プロセスツリーの期限は 3300 秒で、60 分以内の終了処理に余裕を残します。タイムアウトや失敗は未完了の receipt と非ゼロ終了コードになり、成功証拠にはなりません。

```powershell
python -m thm.evaluation --mode acceptance --wall-seconds 3300 --output .thm-evaluation/acceptance-01
```

完全な campaign は --mode full-research --full-research --benchmark NAME --dataset FILE で独立して有効化します。外部で準備したネイティブ入力と、別途設定した agent、環境、judge が必要です。このコマンドは検索だけを測り、実際の agent 実行や benchmark の受け入れを行いません。

<!-- section:invariants -->
## 守るべき invariants

- read-only retrieval は native memory を mutation しない
- retrieval/display/scan は usage activity を捏造しない
- `planned_retrieval` は miss ではない
- prefetch は demand / hit / renewal / promotion evidence を作らない
- residency benefit に使えるのは explicit `avoidable=true` miss だけ
- T1 `pinned` は automatic promotion を意味しない
- locator projection は locator-only で scope 内に解決される
- ordinary mid-session memory write は frozen Hermes prompt snapshot を暗黙に rebuild しない
- held-out task evidence がない限り automatic tier movement / budget write-back は disabled

<!-- section:boundary -->
## Evidence boundary

THM は deterministic/local retrieval と shadow-control experiment を提供しますが、universal answer-quality improvement、universal optimal decay curve、production-ready automatic T0–T3 movement、安全な automatic delete propagation、retrieval metric からの prompt-cache / user-latency 改善、retrieved evidence の model usage を主張しません。

Unit/invariant evidence、retrieval benchmark、harness lifecycle、real task outcome は別々の evidence class です。

<!-- section:documentation -->
## Documentation

- [Documentation index](docs/README.md)
- [Engine guide](docs/06-engine-guide.md)
- [Retrieval and measurement](docs/09-retrieval-and-measurement.md)
- [Harness adapters](docs/11-harness-adapters.md)
- [Version history and recovery](docs/12-version-history.md)
- [1.4 residency control plane](docs/14-residency-control-plane.md)
- [Hermes warm directory](docs/15-hermes-warm-directory.md)
- [Zero-LLM retrieval frontier](docs/16-zero-llm-retrieval-frontier.md)
- [Changelog](CHANGELOG.md)

THM は research software です。1.4.0 は accepted/stable implementation milestone、後続 retrieval frontier は明示的に unreleased です。Version identity は evidence class の代わりにはなりません。
