"""THM retrieval/scan/policy CLI; existing index commands delegate unchanged."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import date
import importlib.util
import json
from pathlib import Path
import sys

from . import __version__
from .retrieval import SearchIndex, SentenceEncoder, TokenCounter
from .sources import jsonl_documents, file_documents, read_hermes, hermes_documents
from .observations import scan, summarize, store_observations
from .policy import Policy, plan, curve_report


def legacy_engine():
    path = Path(__file__).resolve().parents[1]/'scripts/thm.py'
    spec = importlib.util.spec_from_file_location('_thm_legacy_cli', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['index']:
        # Delegate before parsing: the original CLI owns its options and errors.
        return legacy_engine().main(argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=__version__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('import-jsonl', 'import-files', 'import-hermes'):
        p = sub.add_parser(name)
        p.add_argument('source'); p.add_argument('--db', required=True); p.add_argument('--scope', required=True)
    for name in ('search', 'embed'):
        p = sub.add_parser(name)
        p.add_argument('--db', required=True); p.add_argument('--scope', required=True)
        p.add_argument('--model-path'); p.add_argument('--model-id')
        if name == 'search':
            p.add_argument('query'); p.add_argument('--budget', type=int, default=600)
            p.add_argument('--counter', default='utf8_bytes')
            p.add_argument('--mode', choices=['literal','sparse','hybrid','dense'], default='sparse')
            p.add_argument('--neighbors', type=int, choices=[0,1,2], default=0)
    p = sub.add_parser('scan')
    p.add_argument('--state-db', required=True); p.add_argument('--scope', required=True)
    p.add_argument('--anchors', required=True); p.add_argument('--now', required=True)
    p.add_argument('--days', type=int, default=7); p.add_argument('--save-observations')
    p = sub.add_parser('curves')
    p = sub.add_parser('plan')
    p.add_argument('--mem-dir', required=True); p.add_argument('--state-dir')
    p.add_argument('--date', required=True); p.add_argument('--budget', type=int, required=True)
    p.add_argument('--counter', default='utf8_bytes'); p.add_argument('--kernel', default='bounded_power')
    p.add_argument('--half-life', type=float, default=30)
    p = sub.add_parser('index', help='pass arguments to the existing scripts/thm.py CLI')
    p.add_argument('args', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    index = None
    try:
        if args.command == 'index':
            return legacy_engine().main(args.args)
        if args.command.startswith('import-'):
            extra = {}
            if args.command == 'import-jsonl':
                docs = list(jsonl_documents(args.source, args.scope))
            elif args.command == 'import-files':
                docs = list(file_documents(args.source, args.scope))
            else:
                records, extra = read_hermes(args.source, args.scope)
                if extra['partial']:
                    raise ValueError('partial import refused; export a bounded scope explicitly')
                docs = list(hermes_documents(records, args.scope))
            index = SearchIndex(args.db)
            result = index.replace_scope(args.scope, docs) if args.command == 'import-jsonl' else index.sync_kind(
                args.scope, docs, 'file:' if args.command == 'import-files' else 'hermes-message:')
            out = {**result, 'source_read': extra}
        elif args.command in ('search','embed'):
            if not Path(args.db).is_file():
                raise ValueError('search index does not exist; import sources first')
            encoder = SentenceEncoder(args.model_path, args.model_id) if args.model_path else None
            index = SearchIndex(args.db, TokenCounter(getattr(args,'counter','utf8_bytes')))
            if args.command == 'embed':
                if not encoder: raise ValueError('embed requires a local model')
                out = index.embed(args.scope, encoder, args.model_id)
            else:
                out = index.search(args.scope, args.query, budget=args.budget, mode=args.mode,
                                   neighbor_turns=args.neighbors, encoder=encoder, model_id=args.model_id)
        elif args.command == 'scan':
            from datetime import timedelta
            from .sources import epoch
            since = (epoch(args.now)-timedelta(days=args.days)).isoformat()
            records, read_meta = read_hermes(args.state_db, args.scope, since=since)
            anchors = json.loads(Path(args.anchors).read_text(encoding='utf-8'))
            observed, meta = scan(records, anchors, scope=args.scope, now=args.now, days=args.days)
            out = {'summary': summarize(observed), 'scan': meta, 'read': read_meta,
                   'activity_change': 0, 'confidence': 'mentions_only'}
            if args.save_observations:
                out['new_observations'] = store_observations(args.save_observations, observed)
        elif args.command == 'curves':
            out = curve_report()
        else:
            legacy = legacy_engine()
            engine = legacy.Engine(args.mem_dir, args.state_dir)
            rows = engine.load().data['entries']
            # Use complete currently matching T0 text, not truncated summary length.
            sources = {legacy.source_hash(store, text): text for store, entries in engine.stores().items() for text, _ in entries}
            current = [e for e in rows if e['tier']=='T0' and e.get('source_hash') in sources]
            count = TokenCounter(args.counter)
            out = plan(current, date.fromisoformat(args.date), args.budget,
                       Policy(kernel=args.kernel, half_life=args.half_life),
                       lambda e: max(1, count(sources[e['source_hash']]+'\n§\n')))
            out['counter'] = count.name
        print(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except Exception as exc:
        print(json.dumps({'status':'ERROR','error':str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        if index is not None: index.close()


if __name__ == '__main__':
    sys.exit(main())
