# THM — Tiered Hot Memory

**AI Agent 向けの local-first・deterministic な階層型 memory infrastructure。** THM は「何を hot に常駐させるべきか」と「何を必要時に取り戻せばよいか」を分離し、その判断を観測可能な cost と evidence で評価します。別の LLM に memory の再生成を常時依存する設計ではありません。

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | 日本語 | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

作者: Junfu Shi (SJF, xngg1021) · License: [MIT](LICENSE)

<!-- section:architecture -->
## 三つのプレーンによるアーキテクチャ

THM は論理メモリ、計算実行、物理ストレージを分離します。1.5.0 は各プレーン、Evaluation Fabric、明示的な常駐アクチュエータ、独立した Context Economics bridge を実装範囲に統合します。ソースの識別子とスコープが常に権威を持ちます。1.4.0 の過去の証拠は元のプロトコルと SHA を保持し、実装の安定性はハードウェアやタスクの検証を意味しません。

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

明示的アクチュエータは dry-run、リプレイ、厳密な計画承認、トランザクション配置更新、ロールバック、監査に対応します。自動変更は既定で false。ソースの有効性、pin、需要、容量、証拠のゲートを維持します。

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

ゼロタッチ実行環境は安全な利用可能経路で開始し、実際の要求を観測しながら、バックグラウンドの資源上限内でインストール済みプロバイダーを探索します。Provider Fabric は CPU・GPU・NPU の推論、常駐ベクトル索引、転送を分離します。意味的一致、実質的な改善、設定の有効性、セッション境界を確認して採用し、利用者による benchmark は不要です。プロファイルと実行記録は実際の処理とフォールバックを示します。SDK やモデルは自動取得せず、実装成熟度と実機検証を区別します。

[Zero-touch runtime](docs/20-zero-touch-runtime.md) · [Provider Fabric](docs/21-provider-fabric.md) · [Runtime](docs/17-zero-llm-heterogeneous-runtime.md)

<!-- section:physical -->
## 物理ストレージプレーン

StorageProfile は実測アクセスコスト、placement は表現と配置先の対応、PhysicalTelemetry は区間 I/O を記録します。バッファ/mmap ファイル、トランザクション対応の設定済み転送、S3、割り当て所有権、共同配置には実行経路と fixture があります。CXL、DAX、SPDK、GDS、リモート系は有界ライフサイクル契約を共有し、ネイティブ転送実行と実機性能の証拠は別途扱います。

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

EnvironmentRunner は有界の環境ライフサイクルを提供し、OfficialScorerBridge は評価器専用の回答を分離します。Outcome の添付は実行済みタスク ID と trace SHA に結び付き、部分的な結果、欠損スコア、マクロ/マイクロ集計、観測済み遅延/コストを扱います。THM は単位と分母を持つ証拠を Context Economics に渡し、明示的な予算・制約の助言を受け取ります。THM T0–T3 と CE L0–L6 は独立です。

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
| **LangChain / LangGraph / Deep Agents** | ネイティブ BaseRetriever、実行可能な LangGraph ノード、Deep Agents recall/status ツールとグラフ構築 |
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
# Deep Agents: Python >= 3.11
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

THM 1.5.0 は実装のマイルストーンです。統合、ハードウェア、benchmark、タスクの証拠は個別に記録します。却下された検索実験も再現可能な形で保持し、既定では無効です。
