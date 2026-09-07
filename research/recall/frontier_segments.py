"""Bounded exact source spans; no inherited parent gold credit."""
import json
import re
from thm.retrieval import terms, STOP


def spans(text, minimum=80, maximum=4):
    # Keep fenced code intact by refusing to segment it in this first experiment.
    if '```' in text: return []
    boundaries = [0] + [m.end() for m in re.finditer(r'\n\s*\n|[.!?。！？](?:\s+|$)', text)]
    if boundaries[-1] != len(text): boundaries.append(len(text))
    result, start = [], 0
    for end in boundaries[1:]:
        if end - start >= minimum:
            result.append((start, end));start = end
    if start < len(text):
        if result: result[-1] = (result[-1][0], len(text))
        elif len(text) >= minimum: result.append((0, len(text)))
    return result[:maximum]


def pack(index, rows, budget, query):
    blocks, selected = [], []
    focus = set(terms(query)) - STOP
    for row in rows:
        label = {'id': row['id'], 'speaker': row['speaker'], 'date': row['timestamp']}
        full = '[source ' + json.dumps(label, ensure_ascii=False) + ']\n' + row['text']
        if index._count('\n\n'.join(blocks + [full])) <= budget:
            blocks.append(full)
            selected.append({'id': row['id'], 'hash': row['hash'], 'source': row['source'],
                             'complete': True, 'text': row['text']})
            continue
        candidates = sorted(spans(row['text']), key=lambda span: (
            -len(focus & set(terms(row['text'][span[0]:span[1]]))), span[0]))
        for start, end in candidates:
            if not focus & set(terms(row['text'][start:end])): continue
            if start == 0 and end == len(row['text']): continue
            fragment_label = dict(label, span=[start, end], offsets='unicode_codepoints')
            fragment = '[source ' + json.dumps(fragment_label, ensure_ascii=False) + ']\n' + row['text'][start:end]
            if index._count('\n\n'.join(blocks + [fragment])) <= budget:
                blocks.append(fragment)
                selected.append({'id': row['id'], 'hash': row['hash'], 'source': row['source'],
                                 'complete': False, 'text': row['text'][start:end], 'span': [start, end]})
                break  # at most one fragment per source, no overlapping replicas
    context = '\n\n'.join(blocks)
    units = index._count(context)
    if units > budget: raise ValueError('budget exceeded')
    return context, selected, units
