#!/usr/bin/env python3
"""Export a privacy-minimized real-use chronology from a THM v2 index.

Only current entry IDs, unit costs and explicit hit dates are emitted. Memory text,
summaries, keys and evidence strings are not written to the output. The resulting
JSON can be passed to decay_replay.py --input for user-local calibration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import thm as legacy
from thm.retrieval import TokenCounter


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(index_path: Path, mem_dir: Path | None, counter_name: str) -> dict:
    index_path = index_path.resolve()
    data = legacy.decode(legacy.read_bytes(index_path))
    if not isinstance(data, dict) or data.get('version') != 2:
        raise ValueError('THM v2 index required')
    configured = legacy.normal_path(data.get('mem_dir', ''))
    if mem_dir is not None and legacy.normal_path(mem_dir) != configured:
        raise ValueError('mem-dir does not match index identity')
    mem_dir = configured
    counter = TokenCounter(counter_name)

    source_text = {}
    for store in legacy.STORES:
        for text, _line in legacy.parse_store(mem_dir / store):
            source_text[legacy.source_hash(store, text)] = text

    entries = []
    events = []
    ignored = {'nonactive': 0, 'source_unavailable': 0, 'nonhit_events': 0}
    seen_event_ids = set()
    for entry in data.get('entries', []):
        if entry.get('status') != 'active':
            ignored['nonactive'] += 1
            continue
        text = source_text.get(entry.get('source_hash'))
        if text is None:
            ignored['source_unavailable'] += 1
            continue
        units = counter(text + '\n§\n')
        if type(units) is not int or units <= 0:
            raise ValueError('counter must return positive integer units')
        entries.append({
            'id': entry['id'], 'status': 'active',
            'pinned': bool(entry.get('pinned', False)),
            'cost_class': entry.get('cost_class', 'med'),
            'units': units, 'events': [],
        })
        for event in entry.get('events', []):
            if event.get('type') != 'hit':
                ignored['nonhit_events'] += 1
                continue
            event_id = event.get('event_id')
            if not isinstance(event_id, str) or not event_id or event_id in seen_event_ids:
                raise ValueError('invalid or duplicate hit event id')
            legacy.day(event.get('t'), future=False)
            seen_event_ids.add(event_id)
            events.append({'id': entry['id'], 't': event['t'], 'event_id': event_id})

    events.sort(key=lambda row: (row['t'], row['event_id']))
    entries.sort(key=lambda row: row['id'])
    return {
        'entries': entries,
        'events': [{'id': row['id'], 't': row['t']} for row in events],
        'source': 'thm-index-explicit-hit-events-v1',
        'input_index_sha256': file_sha256(index_path),
        'units_counter': counter.name,
        'entry_count': len(entries),
        'hit_event_count': len(events),
        'ignored': ignored,
        'contains_memory_text': False,
        'notes': [
            'Only explicit THM hit events are treated as observed uses.',
            'mention_observed, retrieve, display, confirm and movement events are not uses here.',
            'This export stays local unless the user explicitly publishes it.',
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', required=True)
    parser.add_argument('--mem-dir')
    parser.add_argument('--counter', default='utf8_bytes')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = export(Path(args.index), Path(args.mem_dir) if args.mem_dir else None, args.counter)
    Path(args.output).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('source','entry_count','hit_event_count','units_counter')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
