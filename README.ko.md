# THM — Tiered Hot Memory

**AI Agent를 위한 local-first, deterministic 계층형 memory infrastructure.** THM은 무엇을 hot 상태로 상주시킬지와 무엇을 필요할 때 다시 가져올지를 분리하고, 그 판단을 관측 가능한 cost와 evidence로 평가합니다. 또 하나의 LLM이 memory를 계속 다시 쓰도록 의존하는 구조가 아닙니다.

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | 한국어 | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

작성자: Junfu Shi (SJF, xngg1021) · License: [MIT](LICENSE)

<!-- section:architecture -->
## 세 평면 아키텍처

THM은 논리 메모리, 계산 실행, 물리 저장소를 분리합니다. 1.5.0은 이 계층들과 Evaluation Fabric, 명시적 상주 실행기, 독립적인 Context Economics bridge를 하나의 구현 범위로 제공합니다. 소스 식별자와 범위가 계속 권위를 가집니다. 과거 1.4.0 증거는 원래 프로토콜과 SHA를 유지하며, 구현 안정성이 하드웨어나 작업 검증을 뜻하지는 않습니다.

1.6.0은 동적 토폴로지 epoch, 열과 전력 관측, 제한된 동시성, 네이티브 I/O, 신뢰성 분석, 결정적 장기 기억 검색, CE v2 증거를 갖춘 선택적 Agent 시스템 런타임을 추가합니다. “Hot”은 논리·연산·물리·열·경제·수요·신뢰성 상태를 포함하며 새로운 계층을 만들지 않습니다. 네이티브 실행, 지속 성능, Agent 결과는 각각 검증합니다.

[1.6 runtime](docs/24-agent-systems-runtime.md) · [0-LLM ceiling](docs/25-long-tail-ceiling.md) · [1.6 completion](reports/2026-09-13-thm-1.6-full-power-completion.md)

<!-- section:philosophy -->
## Design philosophy

### 1. Source authority를 유지한다

Native memory file, session transcript, external source가 authoritative source입니다. SQLite/FTS, local embedding, locator 등은 **derived index / projection**입니다. Retrieval을 위해 원본 memory를 암묵적으로 다시 쓰지 않습니다.

### 2. Residency, relevance, activity를 섞지 않는다

THM은 다음을 분리합니다.

- **tier** — 어디에 resident하며 어떻게 access되는가
- **activity** — Agent가 실제로 사용했는가
- **validity** — 아직 유효하고 신뢰할 수 있는가
- **pinning** — operator가 명시적으로 고정했는가
- **retrieval evidence** — 특정 task에서 retrieval path가 해당 item을 노출했는가

Mention은 hit이 아니고, retrieval은 usefulness의 증거가 아닙니다. Prefetch는 demand가 아니며, write도 activity event가 아닙니다.

### 3. Cold memory는 싸게 유지한다

Hot prompt는 희소합니다. THM은 locator와 bounded retrieval을 사용해 cold material을 실제로 필요해질 때까지 resident context 밖에 둡니다. 짧은 locator는 상주할 가치가 있어도 full source는 그렇지 않을 수 있습니다.

### 4. Fixed budget도 correctness의 일부다

큰 candidate pool 어딘가에 gold가 있다는 것만으로 충분하지 않습니다. 최종 evidence slice에 실제로 고정 token budget 안에서 pack되었는지를 측정합니다. Oversized source, duplicate evidence, packing waste도 실제 retrieval loss입니다.

### 5. Self-reinforcing retrieval을 만들지 않는다

System이 스스로 prefetch/retrieve한 item이라는 이유만으로 앞으로 더 중요해지게 만들지 않습니다. Control plane은 explicit demand evidence에서만 학습하며 anti-self-training boundary를 유지합니다.

### 6. Automation은 evidence 이후에 온다

THM은 residency, prefetch, budget에 대한 shadow recommendation을 만들 수 있지만 automatic promote/demote와 automatic budget write-back은 held-out task evidence가 quality, cost, latency, reacquisition 개선을 입증하기 전까지 비활성화됩니다.

### 7. 하나의 memory core, 여러 Harness surface

Retrieval semantics는 THM core에 둡니다. Hermes는 가장 깊은 lifecycle integration을 가지며, OpenAI Agents와 LangChain은 native SDK adapter를 사용하고, MCP는 여러 CLI/harness가 공유하는 protocol surface를 제공합니다.

<!-- section:logical -->
## 논리 메모리 평면

scope 기반 SearchIndex, 예산 내 증거 패킹, shadow 상주 제어는 같은 코어를 사용합니다. T0–T3는 논리적 상주 및 접근 방식을 나타냅니다. 활동, 유효성, 고정, 검색은 각각 기록하며 자동 승격과 예산 쓰기 반영은 꺼져 있습니다.

명시적 실행기는 dry-run, 재생, 정확한 계획 승인, 트랜잭션 배치 갱신, 롤백, 감사를 지원합니다. 자동 변경 기본값은 false이며 소스 유효성, pin, 수요, 용량, 증거 검사를 유지합니다.

<!-- section:tiers -->
## T0–T3 memory Tiers

| Tier | 역할 | 대표 사용처 |
| --- | --- | --- |
| **T0 — Hot** | Host가 이미 들고 있는 resident memory | 반복적으로 residency 가치를 증명하는 작고 중요한 context |
| **T1 — Warm** | 필요할 때 펼치는 locator-oriented memory | topic/file/source locator와 bounded warm reference |
| **T2 — Cold** | 검색 가능한 local history/archive | 고정 evidence budget 아래 scoped FTS/dense retrieval |
| **T3 — External** | 다시 접근 가능한 source location | file, URL, 외부 시스템 |

T0–T3는 **THM memory Tier**입니다. 별도 프로젝트인 Context Economics의 L0–L6 Layer와는 독립된 taxonomy입니다.

<!-- section:compute -->
## 계산 실행 평면

제로 터치 런타임은 안전하게 사용할 수 있는 경로로 시작하고 실제 요청을 관찰하며 백그라운드 자원 한도 안에서 설치된 공급자를 탐색합니다. Provider Fabric은 CPU·GPU·NPU의 추론, 상주 벡터 인덱스, 전송을 분리합니다. 의미적 일치, 실질적인 개선, 설정의 유효성, 세션 경계를 확인한 후 적용하므로 사용자가 먼저 benchmark를 실행할 필요가 없습니다. 프로필과 실행 기록은 실제 처리와 대체 경로를 보여 줍니다. SDK와 모델은 자동 다운로드하지 않으며 구현 성숙도와 실제 하드웨어 검증은 구분합니다.

[Zero-touch runtime](docs/20-zero-touch-runtime.md) · [Provider Fabric](docs/21-provider-fabric.md) · [Runtime](docs/17-zero-llm-heterogeneous-runtime.md)

<!-- section:physical -->
## 물리 저장소 평면

StorageProfile은 측정된 접근 비용을, placement는 표현과 대상의 연결을, PhysicalTelemetry는 구간 I/O를 기록합니다. 버퍼/mmap 파일, 트랜잭션 방식의 구성된 전송, S3, 할당 소유권, 공동 배치에 실행 경로와 fixture가 있습니다. CXL, DAX, SPDK, GDS와 원격 계열은 제한된 수명주기 계약을 공유하며, 네이티브 전송 실행과 실제 하드웨어 성능은 별도 증거가 필요합니다.

[Physical Storage Fabric](docs/physical-storage-fabric.md)

<!-- section:evaluation -->
## Evaluation Fabric

Adapter는 원시 입력을 Task, 평가기 전용 GroundTruth, Result, SHA 기반 Receipt로 변환합니다. LoCoMo Protocol 2와 LongMemEval-S는 dataplane 지표를 공유하며 문서 및 세션 단위 차이를 유지합니다. LongMemEval-V2는 공개 trajectory states와 insert/query, BEAM은 batches/turns와 probing questions, MemoryArena는 하위 작업 및 세션 간 add/wrap_user_prompt를 지원합니다.

Fixture는 인터페이스와 결정론적 검색만 검증합니다. V2는 텍스트 전용이며 이미지 질의를 거부합니다. gold locator가 없으면 recall은 null입니다. MemoryArena 작업 파싱은 환경 실행을 뜻하지 않습니다. 정답과 rubric은 검색 문서에 들어가지 않습니다.

| 증거 계층 | Receipt 계약 |
| --- | --- |
| memory-dataplane | any/all-gold, macro/micro recall, 부모 위치 커버리지, 예산, 지연 |
| systems-runtime | 계산 프로필, StorageProfile, placement, I/O 측정 |
| LLM-agent-outcome | 생성/judge 호출, 정답률, 환경 성공률; 기본 not-run |

[Evaluation Fabric](docs/18-evaluation-fabric.md)

EnvironmentRunner는 제한된 환경 수명주기를 제공하고 OfficialScorerBridge는 평가기 전용 정답을 분리합니다. Outcome 첨부는 실행된 작업 ID와 trace SHA에 연결되며, 부분 결과, 누락 점수, 매크로/마이크로 집계, 관측된 지연/비용을 지원합니다. THM은 단위와 분모가 있는 증거를 Context Economics에 내보내고 명시적 예산 및 제약 조언을 받습니다. THM T0–T3와 CE L0–L6는 독립적입니다.

<!-- section:evidence -->
## Measured retrieval evidence

THM은 retrieval evidence와 answer-generation claim을 분리합니다.

Canonical LoCoMo Protocol 2는 1,532 fully resolved non-adversarial questions와 고정 600 `cl100k_base` evidence-token slice를 사용합니다.

| Retrieval mode | Any-gold packed evidence | All-gold packed evidence | p95 retrieval + packing |
| --- | ---: | ---: | ---: |
| Literal | 56.79% | 46.61% | — |
| Sparse | **69.39%** | **56.53%** | **34.55 ms** |
| Local dense | 51.11% | 40.01% | — |
| Hybrid | **71.34%** | **57.64%** | **57.88 ms** |

현재 opt-in deterministic entity projection은 full-set sparse any-gold를 **69.39% → 72.52%**, frozen 1,301-question holdout을 **69.56% → 72.33%**로 높이며 candidate coverage는 바꾸지 않습니다. 즉 추가 모델로 candidate pool을 키운 것이 아니라 **이미 존재하는 candidate를 600-token slice 안에 더 잘 배치한 결과**입니다.

이 수치는 final answer accuracy, user satisfaction, universal superiority가 아니라 **packed retrieval evidence**를 측정합니다. [Protocol 2](reports/2026-09-06-recall-protocol2.md)와 [zero-LLM frontier](docs/16-zero-llm-retrieval-frontier.md)를 참고하십시오.

<!-- section:harness -->
## Harness integration

| Surface | Integration depth |
| --- | --- |
| **Hermes Agent** | Native `MemoryProvider`; setup/config, prefetch, optional live-turn sync, session boundary hooks, memory-write refresh semantics |
| **OpenAI Agents SDK** | Native read-only `FunctionTool` |
| **LangChain / LangGraph / Deep Agents** | 네이티브 BaseRetriever, 실행 가능한 LangGraph 노드, Deep Agents recall/status 도구 및 그래프 구성 |
| **MCP v2** | stdio 기반 typed read-only `thm_recall` / `thm_status` |
| **OpenClaw** | legacy MCP bridge를 통한 pinned compatibility probe |
| **Claude Code / Codex CLI / Gemini CLI** | pinned real-CLI discovery/call lifecycle, 동일 read-only recall core 사용 |

Multi-harness support가 universal memory database를 의미하지는 않습니다. Lifecycle integration의 깊이는 host마다 다르고 Hermes가 가장 깊은 native integration입니다.

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
## 시간 제한 로컬 검증

저장소 루트에서 Python 3.10 이상으로 실행합니다. 모델이나 데이터셋 다운로드, provider key가 필요하지 않습니다. 프로세스 트리 제한은 3300초이며 60분 내 종료 정리 시간을 남깁니다. 시간 초과나 실패는 미완료 receipt와 0이 아닌 종료 코드로 기록됩니다.

```powershell
python -m thm.evaluation --mode acceptance --wall-seconds 3300 --output .thm-evaluation/acceptance-01
```

전체 campaign은 --mode full-research --full-research --benchmark NAME --dataset FILE로 별도 활성화합니다. 외부에서 준비한 원시 입력과 별도로 설정한 agent, 환경, judge가 필요합니다. 이 명령은 검색만 측정하며 실제 agent를 실행하거나 benchmark를 자동 승인하지 않습니다.

<!-- section:invariants -->
## 반드시 지켜야 할 invariants

- read-only retrieval은 native memory를 mutate하지 않는다
- retrieval/display/scan은 usage activity를 만들어내지 않는다
- `planned_retrieval`은 miss가 아니다
- prefetch는 demand / hit / renewal / promotion evidence를 만들지 않는다
- residency benefit에는 explicit `avoidable=true` miss만 사용한다
- T1 `pinned`은 automatic promotion을 뜻하지 않는다
- locator projection은 locator-only이며 올바른 scope 내부에 resolve되어야 한다
- ordinary mid-session memory write는 frozen Hermes prompt snapshot을 암묵적으로 rebuild하지 않는다
- held-out task evidence가 없으면 automatic tier movement와 budget write-back은 disabled 상태를 유지한다

<!-- section:boundary -->
## Evidence boundary

THM은 deterministic/local retrieval과 shadow-control experiment를 제공하지만 universal answer-quality improvement, universal optimal decay curve, production-ready automatic T0–T3 movement, 안전한 automatic delete propagation, retrieval metric에서 자동으로 추론한 prompt-cache/user-latency 개선, retrieved evidence의 실제 model usage를 주장하지 않습니다.

Unit/invariant evidence, retrieval benchmark, harness lifecycle, real task outcome은 서로 다른 evidence class입니다.

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

THM 1.5.0은 구현 마일스톤이며 통합, 하드웨어, benchmark, 작업 증거를 별도로 기록합니다. 기각된 검색 실험은 재현 가능하게 보존되며 기본적으로 꺼져 있습니다.
