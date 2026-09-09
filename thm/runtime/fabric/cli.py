"""Fast zero-touch diagnostics. Native discovery is an explicit bounded option."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from .hardware import HostDeviceProvider
from .registry import builtin_registry


def inspect_store(path, *, limit=256):
    if not path:
        return {'state': 'not-specified', 'observations': [], 'freshness': 'unverified'}
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError('existing regular profile store required')
    db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)
    try:
        if db.execute('PRAGMA user_version').fetchone()[0] != 2:
            raise ValueError('unsupported profile store schema')
        rows = db.execute('SELECT key,payload,checksum,first_seen,validated FROM observations ORDER BY validated DESC LIMIT ?', (limit,)).fetchall()
        from .contracts import identity
        values = []
        for key, raw, checksum, first, validated in rows:
            try:
                value = json.loads(raw)
                if identity(value) != checksum:
                    continue
                invalid = bool(db.execute('SELECT 1 FROM invalidated WHERE key=?', (key,)).fetchone())
                values.append({'profile_key': key, **value, 'first_seen': first, 'last_validated': validated,
                               'freshness': 'invalidated' if invalid else 'requires-live-fingerprint-match'})
            except (ValueError, TypeError):
                continue
        return {'state': 'available', 'observations': values, 'truncated_at': limit, 'freshness': 'requires-live-fingerprint-match'}
    finally:
        db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('status','doctor','explain','providers','profile','invalidate-profile'))
    parser.add_argument('--store'); parser.add_argument('--key')
    parser.add_argument('--probe-provider'); parser.add_argument('--json', dest='output')
    args = parser.parse_args(argv)
    registry = builtin_registry()
    try:
        if args.command == 'invalidate-profile':
            if not args.store or not args.key or len(args.key) != 64 or any(c not in '0123456789abcdef' for c in args.key):
                raise ValueError('existing --store and SHA256 --key required')
            inspect_store(args.store)
            from .store import ProfileStore
            store = ProfileStore(args.store)
            try:
                with store.db:
                    store.db.execute('INSERT OR IGNORE INTO invalidated VALUES(?)', (args.key,))
            finally:
                store.close()
            result = {'status': 'invalidated', 'profile_key': args.key}
        else:
            graph = HostDeviceProvider().discover()
            result = {'schema': 2, 'mode': 'zero-touch', 'core_only_available': True,
                'hardware': {**graph.public(), 'observed_kernel_dispatch': None},
                'hardware_fingerprint': graph.fingerprint, 'semantic_policy': 'auto-safe',
                'bootstrap': 'sparse-or-explicit-fp32-reference', 'profile_source': 'bootstrap',
                'profile_freshness': 'requires-live-model-and-source-fingerprint',
                'profile_store': inspect_store(args.store), 'generation_calls': 0, 'model_downloads': 0,
                'user_benchmark_required': False, 'background': 'bounded-idle-request-replay',
                'promotion': 'numeric-and-structural-parity-plus-material-gain',
                'session_pinning': True, 'fallback': 'validated-reference'}
            if args.command in ('doctor','providers','explain'):
                result['providers'] = registry.list()
            if args.probe_provider:
                result['probe'] = registry.probe(args.probe_provider, timeout=3)
            if args.command == 'explain':
                result['selection'] = {'workloads': ['interactive','bulk','background'],
                    'objectives': ['p95','cpu_seconds','throughput','transfer','startup','memory','energy'],
                    'unknown_energy': None, 'material_min_relative_gain': .05,
                    'material_min_absolute_ms': .25, 'noise_estimator': 'median-and-MAD',
                    'candidate_limit_per_idle_window': 2, 'unready_local_model': 'sparse-safe',
                    'ann_and_low_precision': 'explicit-approximate-policy-with-separate-receipts'}
        if args.output:
            from ..receipts import write_receipt
            write_receipt(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'error', 'error_type': type(exc).__name__,
                          'message': str(exc) if isinstance(exc, ValueError) else 'runtime diagnostic failed'}), file=sys.stderr)
        return 1
    finally:
        registry.close()
