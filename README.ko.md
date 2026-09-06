# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

작성자: Junfu Shi (SJF, xngg1021) · 라이선스: [MIT](LICENSE)

THM은 Hermes Agent를 위한 로컬 우선 4계층 메모리 도구입니다. 항상 컨텍스트를 차지할 정보, 필요할 때만 읽을 정보, 고정된 예산 안에서 과거 기록을 회수하는 방식, 그리고 “사용” 신호를 만들어내지 않고 이러한 결정을 측정하는 방법에 집중합니다.

## 네 계층

- **T0 — hot:** 세션 시작 스냅샷에 주입되는 기본 `MEMORY.md` / `USER.md`.
- **T1 — warm:** 주제별 Markdown을 필요할 때 로드합니다.
- **T2 — cold:** 명시적인 evidence budget 안에서 과거 세션과 아카이브를 검색합니다.
- **T3 — external:** 필요할 때 다시 방문할 외부 소스 위치와 참조입니다.

THM은 activity, validity, 현재 작업 관련성, 명시적 pin을 구분합니다. 언급은 hit가 아니고, retrieval은 유용성의 증명이 아니며, write 역시 사용 이벤트가 아닙니다.

## 구현된 기능

1.1.1 인덱스 CLI는 profile-bound 인덱스, 엄격한 이벤트 ID, 마이그레이션 미리보기, pin/unpin, 실패 안전 쓰기를 제공합니다. 1.2 패키지는 범위가 지정된 FTS5 검색, 선택적 로컬 sentence embedding, RRF fusion, 예산을 계산하는 context packing, 가중치 0의 `mention_observed`, 여러 decay 정책 비교, read-only Hermes provider adapter, 재현 가능한 평가 스크립트를 추가합니다.

검색 및 scan 경로는 기본 메모리 파일이나 Hermes `state.db`를 수정하지 않습니다. 파생 SQLite DB는 THM 테이블을 만들기 전에 관련 없는 DB 또는 기본 DB 대상을 거부합니다.

## 측정된 근거

과거 protocol 1 LoCoMo 실행은 10개 대화와 1,986개 질문을 사용했습니다. 600 `cl100k_base` evidence-token 예산과 완전히 해석 가능한 비대항 질문 1,532개에서 any-gold coverage는 **literal 56.85%**, **sparse 69.58%**, **MiniLM dense 51.11%**, **hybrid 70.04%**였습니다. 이는 evidence retrieval 지표이며 답변 정확도나 경쟁 제품 순위가 아닙니다.

Protocol 2는 카테고리 라벨을 수정하고 대화별로 FTS5 IDF 통계를 격리하며 MRR, nDCG, p99를 추가합니다. 전체 protocol 2는 저장소 benchmark workflow에서 독립적으로 실행됩니다.

## 설치 및 실행

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
python -m thm curves
```

선택적 tokenizer / semantic 의존성: `python -m pip install -e '.[tokenizer,semantic]'`.

설치 후 THM은 Hermes의 `hermes_agent.memory_providers` entry-point를 통해 `thm` provider로 노출됩니다. 고정된 Hermes upstream checkout을 사용하는 통합 workflow가 실제 discovery와 provider lifecycle을 검증합니다.

## 근거의 경계

THM은 현재 실제 사용자 end-to-end 답변 정확도, 보편적으로 최적인 decay curve, 자동 tier 이동, 자동 삭제 전파, prompt-cache 또는 체감 지연 개선을 입증했다고 주장하지 않습니다. `scan`은 activity weight가 0인 약한 `mention_observed`만 기록합니다. 사용자별 decay 보정에는 실제 시간순 사용 기록이 필요합니다.

문서: [프로젝트 인덱스](docs/README.md) · [엔진 가이드](docs/06-engine-guide.md) · [retrieval / scan / decay](docs/09-retrieval-and-measurement.md) · [통합 검토](docs/10-recall-integration-review.md) · [benchmark protocol](research/recall/README.md)