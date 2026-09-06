# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

작성자: Junfu Shi (SJF, xngg1021) · 라이선스: [MIT](LICENSE)

THM은 Hermes Agent용 로컬 우선 4계층 메모리 도구입니다. T0는 세션 snapshot의 `MEMORY.md` / `USER.md`, T1은 필요할 때 읽는 주제별 Markdown, T2는 명시된 예산 안의 과거 기록 검색, T3는 외부 소스 참조입니다.

activity, validity, task relevance, 명시적 pin을 분리합니다. 언급은 hit가 아니고 retrieval은 유용성의 증명이 아니며 write도 사용 이벤트가 아닙니다. 1.2는 FTS5 sparse retrieval, 선택적 로컬 semantic vector, RRF, budget packing, 가중치 0의 `mention_observed`, decay 비교, read-only Hermes provider를 구현합니다.

과거 LoCoMo protocol 1에서 600 `cl100k_base` evidence-token, 완전히 해석 가능한 비대항 질문 1,532개의 any-gold coverage는 **literal 56.85% / sparse 69.58% / dense 51.11% / hybrid 70.04%**였습니다. 이는 답변 정확도가 아닙니다. Protocol 2는 카테고리를 수정하고 대화별로 IDF를 격리하며 MRR / nDCG / p99를 추가합니다.

```bash
python -m pip install -e .
python -m thm --help
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
```

설치 후 THM은 Hermes의 `hermes_agent.memory_providers` entry-point를 통해 `thm` provider로 노출됩니다. 고정 upstream을 사용하는 E2E workflow가 실제 Hermes discovery와 provider lifecycle을 검증합니다.

THM은 현재 실제 사용자 end-to-end 답변 정확도, 보편적 최적 decay, 자동 tier 이동/삭제 전파, 체감 latency 개선을 입증했다고 주장하지 않습니다. 사용자별 decay 보정에는 실제 시간순 hit 기록이 필요합니다.

문서: [프로젝트 인덱스](docs/README.md) · [엔진 가이드](docs/06-engine-guide.md) · [retrieval / scan / decay](docs/09-retrieval-and-measurement.md) · [benchmark](research/recall/README.md)
