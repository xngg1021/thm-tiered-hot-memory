"""Label-free candidate reranking and exact budget packing experiments.

This module deliberately consumes only the query, retrieved source rows and the
base candidate order. QA answers, benchmark evidence IDs and generated
summaries are not inputs. It stays separate from :mod:`thm.retrieval` until
held-out evaluation demonstrates that a reranker improves the existing default.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Callable, Iterable, Mapping, Sequence

from .retrieval import CJK, STOP, TokenCounter, terms


@dataclass(frozen=True)
class RerankConfig:
    """Deterministic weights for the label-free lexical reranker."""

    coverage_weight: float = 0.75
    all_focus_bonus: float = 0.15
    exact_bonus: float = 0.10
    metadata_match_factor: float = 0.25
    rank_exponent: float = 0.5

    def validate(self) -> None:
        values = (
            self.coverage_weight,
            self.all_focus_bonus,
            self.exact_bonus,
            self.metadata_match_factor,
            self.rank_exponent,
        )
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
            raise ValueError("rerank weights must be finite numbers")
        if self.coverage_weight < 0 or self.all_focus_bonus < 0 or self.exact_bonus < 0:
            raise ValueError("rerank bonuses cannot be negative")
        if not 0 <= self.metadata_match_factor <= 1:
            raise ValueError("metadata_match_factor must be from 0 to 1")
        if not 0 < self.rank_exponent <= 2:
            raise ValueError("rank_exponent must be in (0, 2]")


def _focus_terms(query: str) -> list[str]:
    tokens = terms(query)[:64]
    focus = [token for token in tokens if token not in STOP]
    return focus or tokens


def _specificity(token: str) -> float:
    """Prefer exact numbers/technical identifiers without corpus labels."""
    if any(char.isdigit() for char in token):
        return 1.8
    if any(char in "-_/\." for char in token):
        return 1.6
    if CJK.fullmatch(token):
        return 1.3
    return 1.0 + min(0.5, max(0, len(token) - 4) * 0.08)


def _normalise_for_phrase(text: str) -> str:
    return " ".join(re.findall(r"[\w\u3400-\u9fff]+", text.casefold(), flags=re.UNICODE))


def lexical_features(query: str, row: Mapping[str, object]) -> dict[str, float]:
    """Return body/meta match mass without benchmark or answer information."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("nonempty query required")
    text = row.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("source row requires text")
    speaker = row.get("speaker", "")
    timestamp = row.get("timestamp", "")
    if not isinstance(speaker, str) or not isinstance(timestamp, str):
        raise ValueError("speaker/timestamp must be strings")

    focus = _focus_terms(query)
    body = set(terms(text))
    meta = set(terms(f"{speaker} {timestamp}"))
    total = sum(_specificity(token) for token in focus) or 1.0
    body_mass = 0.0
    meta_mass = 0.0
    any_matches = 0
    body_matches = 0
    for token in focus:
        weight = _specificity(token)
        if token in body:
            body_mass += weight
            body_matches += 1
            any_matches += 1
        elif token in meta:
            meta_mass += weight
            any_matches += 1
    query_phrase = _normalise_for_phrase(query)
    return {
        "body_coverage": body_mass / total,
        "meta_coverage": meta_mass / total,
        "all_focus": 1.0 if focus and any_matches == len(focus) else 0.0,
        "body_fraction": body_matches / len(focus) if focus else 0.0,
        "exact": 1.0 if len(query_phrase) >= 8 and query_phrase in _normalise_for_phrase(text) else 0.0,
    }


def rerank_rows(
    query: str,
    rows: Sequence[Mapping[str, object]],
    config: RerankConfig = RerankConfig(),
) -> list[dict]:
    """Rerank base-ordered rows using rank prior plus direct lexical coverage.

    The original candidate order remains the prior and final tie-break. No
    candidate can appear unless the upstream retriever already returned it.
    """
    config.validate()
    ranked: list[tuple[float, int, str, dict]] = []
    for rank, source in enumerate(rows, 1):
        row = dict(source)
        row_id = row.get("id")
        if not isinstance(row_id, str) or not row_id:
            raise ValueError("candidate row requires string id")
        features = lexical_features(query, row)
        coverage = min(
            1.0,
            features["body_coverage"] + config.metadata_match_factor * features["meta_coverage"],
        )
        rank_prior = rank ** (-config.rank_exponent)
        score = (
            rank_prior
            + config.coverage_weight * coverage
            + config.all_focus_bonus * features["all_focus"]
            + config.exact_bonus * features["exact"]
        )
        row["_thm_base_rank"] = rank
        row["_thm_rerank_score"] = score
        row["_thm_rerank_features"] = dict(features, coverage=coverage)
        ranked.append((-score, rank, row_id, row))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in ranked]


def source_block(row: Mapping[str, object], *, compact: bool) -> str:
    """Serialize one complete source span with explicit provenance metadata."""
    row_id = row.get("id")
    text = row.get("text")
    speaker = row.get("speaker", "")
    timestamp = row.get("timestamp", "")
    if not isinstance(row_id, str) or not row_id or not isinstance(text, str) or not text:
        raise ValueError("source row requires id and text")
    if not isinstance(speaker, str) or not isinstance(timestamp, str):
        raise ValueError("speaker/timestamp must be strings")
    meta = {"id": row_id, "speaker": speaker, "date": timestamp}
    if compact:
        # Same named fields as the baseline format; only insignificant JSON
        # whitespace is removed, so no provenance field is sacrificed for budget.
        label = json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
    else:
        label = json.dumps(meta, ensure_ascii=False)
    return f"[source {label}]\n{text}"


def pack_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    budget: int,
    counter: Callable[[str], int],
    compact_headers: bool = True,
) -> dict:
    """First-fit whole-source packing with an exact final budget check."""
    if type(budget) is not int or not 0 <= budget <= 32768:
        raise ValueError("budget must be an integer from 0 to 32768")
    blocks: list[str] = []
    selected: list[dict] = []
    used = 0
    byte_counter = type(counter) is TokenCounter and counter.encode is None

    for source in rows:
        row = dict(source)
        block = source_block(row, compact=compact_headers)
        if byte_counter:
            units = used + len(block.encode("utf-8")) + (2 if blocks else 0)
        else:
            candidate_context = "\n\n".join(blocks + [block])
            units = counter(candidate_context)
            if type(units) is not int or units < 0 or (candidate_context and units == 0):
                raise ValueError("counter must return a positive integer for nonempty context")
        if units <= budget:
            used = units
            blocks.append(block)
            selected.append(
                {
                    "id": row["id"],
                    "hash": row.get("hash", ""),
                    "source": row.get("source", ""),
                    "complete": True,
                    "text": row["text"],
                }
            )

    context = "\n\n".join(blocks)
    final_units = counter(context)
    if type(final_units) is not int or final_units < 0 or (context and final_units == 0):
        raise ValueError("counter must return a positive integer for nonempty context")
    if final_units > budget:
        raise ValueError("counter changed while packing; final context exceeds budget")
    return {
        "context": context,
        "selected": selected,
        "budget": budget,
        "budget_used": final_units,
        "compact_headers": compact_headers,
    }
