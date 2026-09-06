# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

작성자: Junfu Shi (SJF, xngg1021) · 라이선스: [MIT](LICENSE) · 안정 버전: **1.3.0**

THM은 agent harness용 로컬 우선 4계층 메모리입니다. 1.3은 Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever`, MCP v2 stdio와 OpenClaw 2026.9.x용 별도 legacy MCP bridge를 포함한 harness-neutral 읽기 전용 recall 계층을 제공합니다. Claude Code, Codex CLI, Gemini CLI는 고정 버전의 실제 CLI 구성과 동일 server command lifecycle E2E로 검증됩니다. 원본 메모리를 수정하거나 모델을 추가 호출하지 않습니다.

LoCoMo Protocol 2는 10개 대화, 1,986개 질문 전체와 주 분모 1,532개 질문을 사용합니다. 600 evidence token에서 literal / sparse / dense / hybrid의 any-gold coverage는 **56.79% / 69.39% / 51.11% / 71.34%**입니다. 답변 정확도가 아닌 증거 검색 지표입니다. [전체 보고서](reports/2026-09-06-recall-protocol2.md)

```bash
python -m pip install -e .
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

1.3.0 accepted/stable은 correctness, Hermes, harness 전체 matrix를 통과한 정확한 Git SHA를 가리키는 공식 version ref로만 확정됩니다. 실제 사용자 E2E 답변 정확도, 보편적 최적 decay, 자동 tier 이동/삭제 전파, 체감 latency 개선은 주장하지 않습니다.

문서: [목차](docs/README.md) · [Harness](docs/11-harness-adapters.md) · [버전 기록](docs/12-version-history.md) · [변경 기록](CHANGELOG.md)
