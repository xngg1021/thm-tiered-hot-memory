#!/usr/bin/env python3
"""Compatibility CLI for THM shadow miss/prefetch telemetry.

The authoritative validation/aggregation implementation lives in
``thm.residency`` so the package CLI and research scripts cannot silently drift.
This program remains read-only: it does not mutate THM residency, activity,
validity, or native memory files.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from thm.residency import (
    ResidencyError as TelemetryError,
    aggregate_telemetry as aggregate,
    load_telemetry_jsonl as load_jsonl,
    validate_telemetry_event as validate_event,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="JSONL telemetry trace")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    report = aggregate(load_jsonl(args.trace))
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None,
                     sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
