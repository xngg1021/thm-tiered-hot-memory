# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | 한국어 | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

작성자: Junfu Shi (SJF, xngg1021) · 라이선스: [MIT](LICENSE)

## 4개 계층

THM은 agent harness용 로컬 우선 4계층 메모리입니다. T0는 호스트가 주입한 영구 컨텍스트, T1은 필요할 때 읽는 주제 자료, T2는 명시적 증거 예산으로 검색하는 기록, T3는 다시 방문할 수 있는 외부 소스입니다. 활동성, 유효성, 작업 관련성, pin을 분리하며 mention·retrieval·write를 유용한 hit로 간주하지 않습니다.

## 구현 범위

1.1.1은 강화된 index CLI를, 1.2는 scope 분리 FTS5, 선택적 로컬 embedding, RRF, 예산 기반 packing, 가중치 0 mention observation, decay 비교와 재현 가능한 평가를 제공합니다. **1.3은 harness-neutral 읽기 전용 recall 계층**으로 Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever`, MCP v2 stdio를 추가합니다. OpenClaw 2026.9.x, Claude Code, Codex CLI, Gemini CLI는 별도 읽기 전용 MCP compatibility bridge와 고정된 실제 CLI로 검증합니다. 원본 메모리를 수정하거나 모델을 추가 호출하지 않습니다.

## LoCoMo 측정

Protocol 2는 10개 대화와 1,986개 질문 전체, 주 분모 1,532개 질문을 사용합니다. 600 `cl100k_base` evidence token에서 any-gold는 **literal 56.79% / sparse 69.39% / dense 51.11% / hybrid 71.34%**, all-gold는 **46.61% / 56.53% / 40.01% / 57.64%**입니다. 답변 정확도가 아닌 증거 검색 지표입니다. p95 retrieval+packing은 **sparse 34.55 ms / hybrid 57.88 ms**입니다. 300/600/1200 token sparse 결과는 **60.57/69.39/76.17%**, p95는 **20.39/34.55/61.78 ms**입니다. [보고서](reports/2026-09-06-recall-protocol2.md) · [JSON](reports/2026-09-06-recall-protocol2-summary.json).

## 통합

| Surface | THM 1.3 |
| --- | --- |
| Hermes | pip provider, setup/config, prefetch, 선택적 `sync_turn`, session hooks, write≠hit |
| OpenAI Agents | 읽기 전용 `OpenAIAgentsTHM.tool` |
| LangChain/LangGraph | `THMLangChainRetriever` |
| MCP v2 | `thm-mcp`, typed `thm_recall` / `thm_status` |
| OpenClaw | `thm-mcp-legacy`, 실제 runtime probe |
| Claude/Codex/Gemini | 고정 실제 CLI, 정확한 command, discovery/call lifecycle, 모델 호출 0 |

이전 Hermes E2E는 `NousResearch/hermes-agent@77915e...`에 고정되며 1.3 CI는 검토된 최신 snapshot도 검사합니다. 근거는 항상 같은 commit의 workflow입니다.

## 설치

```bash
python -m pip install -e .
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

Extras는 `.[tokenizer,semantic]`, `.[openai]`, `.[langchain]`, `.[mcp]`, `.[harnesses]`이며 compatibility bridge는 `thm-mcp-legacy`입니다.

## Hermes lifecycle

`sync_turns`는 기본 비활성입니다. 명시적으로 활성화하면 user/assistant 텍스트만 session별 파생 T2 scope에 동기화하고 system row와 compression summary는 제외합니다. `on_memory_write`는 refresh 신호이며 hit가 아닙니다. 파생 cache는 canonical transcript owner가 아니므로 THM은 fail-closed checkpoint-v2 durability를 주장하지 않고 pre-compress API v1을 유지합니다.

## Decay calibration

`decay_from_index.py`는 ID, unit cost, 명시적 hit 날짜만 내보내고 본문, summary, key, confirmation evidence를 제외합니다. `decay_replay.py`로 비공개 replay할 수 있습니다. 실제 hit chronology 없이는 개인 최적 half-life를 주장하지 않습니다.

## 증거 경계

실제 사용자 E2E 답변 정확도, 보편적 최적 decay, 자동 tier 이동, 삭제 전파, prompt-cache 또는 체감 latency 개선은 주장하지 않습니다. Coverage, host plumbing, 모델의 증거 사용, 최종 답변 품질은 독립된 증거 계층입니다. Correctness CI는 Linux, macOS, Windows에서 실행하며 LoCoMo와 integration job은 분리합니다.

[목차](docs/README.md) · [가이드](docs/06-engine-guide.md) · [Recall](docs/09-retrieval-and-measurement.md) · [Harness](docs/11-harness-adapters.md) · [버전 기록](docs/12-version-history.md) · [Changelog](CHANGELOG.md)

## THM 1.4 현재 안정 상태

THM 1.4는 **accepted/stable implementation milestone**로 완료되어 고정되었습니다. 안정 코드/콘텐츠 마일스톤은 `e6e4dda5835e3cb345207457d5491131c6959b2c`, 복구 포인터는 `archive/v1.4.0-stable`입니다. T0–T3 4계층 모델은 그대로 유지됩니다.

1.4는 기존 1.3 harness-neutral recall 위에 명시적 resident/hard miss 및 planned retrieval telemetry, 엄격한 locator-only T1 warm directory, avoidable-miss penalty와 resident carry cost 기반 shadow T0 recommendation, 경계가 있는 정확한 0/1 packing, 실제 demand co-occurrence만 학습하는 bounded prefetch, 예산을 자동 변경하지 않는 resident-budget feedback을 추가합니다. Hermes에는 기본 비활성화된 session-frozen T1 locator snapshot도 있습니다.

이 기능들은 1.4 correctness, Hermes, multi-harness 승인 검증을 통과했습니다. 1.4는 retrieval path를 변경하지 않았으므로 새로운 LoCoMo/Protocol 2 수치를 주장하지 않습니다. 자동 T0–T3 이동과 자동 예산 변경은 held-out runtime/task A/B가 품질·비용·지연·reacquisition 개선을 입증할 때까지 비활성화 상태입니다. 자세한 내용은 [1.4 control plane](docs/14-residency-control-plane.md), [Hermes T1 directory](docs/15-hermes-warm-directory.md), [1.4 closeout](reports/2026-09-07-v1.4-closeout.md)을 참조하십시오.

Version identity: **1.4.0 accepted/stable implementation milestone**.
