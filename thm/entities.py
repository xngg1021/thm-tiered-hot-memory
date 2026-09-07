"""Exact candidate speaker/identifier projection; no inferred identities or label input.

This read-only derived projection changes packing order, not candidate membership,
canonical identity, activity or tier residency. Fixed RRF bonus: 0.25."""
import re

GENERIC = {'python', 'windows', 'model', 'project'}
IDENTIFIER = re.compile(r'https?://[^\s<>]+|\b[0-9a-f]{7,40}\b|\b[A-Z]+-\d+\b|\bv?\d+\.\d+(?:\.\d+)?\b|`([^`]+)`')


def present(value, text):
    # Preserve case for technical identifiers, URLs and paths.
    return bool(re.search(r'(?<![\w])' + re.escape(value) + r'(?![\w])', text))


def reorder(rows, query, weight=0.25):
    speakers = {r['speaker'] for r in rows if r['speaker'] and r['speaker'].lower() not in GENERIC
                and present(r['speaker'], query)}
    identifiers = {m[0].strip('`') for m in IDENTIFIER.finditer(query)}
    if not speakers and not identifiers: return rows
    matched = [r['rowid'] for r in rows if r['speaker'] in speakers
               or any(present(value, r['text']) for value in identifiers)]
    if not matched: return rows
    ranks = {rid: n for n, rid in enumerate(matched, 1)}
    scored = [(1 / (60 + n) + (weight / (60 + ranks[r['rowid']]) if r['rowid'] in ranks else 0), n, r)
              for n, r in enumerate(rows, 1)]
    return [r for _, _, r in sorted(scored, key=lambda x: (-x[0], x[1]))]
