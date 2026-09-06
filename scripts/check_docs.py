#!/usr/bin/env python3
"""Offline documentation checks; no private memory or external services are used."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REPORT = 'reports/2026-09-06-学术工具复审.md'
ORIGINAL_BLOB = 'a5cb344275050c16d12f5c3b42db9e0203c60cdd'
START = '<!-- original-report:start -->\n'
END = '<!-- original-report:end -->'


def check(root: Path) -> dict:
    errors: list[str] = []
    md_paths = sorted(root.rglob('*.md'))
    expected = {'README.md', 'docs/01-研究综述.md', 'docs/02-架构设计.md', REPORT}
    actual = {p.relative_to(root).as_posix() for p in md_paths}
    if actual != expected:
        errors.append('Expected the four scoped Markdown documents')
    link_count = json_fences = 0
    for path in md_paths:
        raw = path.read_bytes()
        try:
            text = raw.decode('utf-8')
        except UnicodeError:
            errors.append(f'{path.name}: invalid UTF-8')
            continue
        if not raw.endswith(b'\n') or b'\r' in raw:
            errors.append(f'{path.name}: require LF and final newline')
        if any(line != line.rstrip() for line in text.splitlines()):
            errors.append(f'{path.name}: trailing whitespace')
        if text.count('```') % 2:
            errors.append(f'{path.name}: unpaired triple-backtick fence')
        for target in re.findall(r'\[[^\]\n]+\]\(([^\s)]+)\)', text):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            link_count += 1
            dest = (path.parent / unquote(parsed.path)).resolve()
            if not dest.is_relative_to(root.resolve()) or not dest.is_file():
                errors.append(f'{path.name}: missing/outside relative link {target}')
        for block in re.findall(r'^```json\s*\n(.*?)^```\s*$', text, re.M | re.S):
            json_fences += 1
            try:
                json.loads(block)
            except ValueError as exc:
                errors.append(f'{path.name}: JSON fence: {exc}')
    if json_fences != 1:
        errors.append('Expected one retained architecture JSON example')
    report = (root / REPORT).read_text(encoding='utf-8')
    if report.count(START) != 1 or report.count(END) != 1:
        errors.append('Missing or duplicated historical-report delimiters')
        preserved = False
    else:
        original = report.split(START, 1)[1].split(END, 1)[0].encode('utf-8')
        digest = hashlib.sha1(f'blob {len(original)}\0'.encode() + original).hexdigest()
        preserved = digest == ORIGINAL_BLOB
        if not preserved:
            errors.append('Historical report bytes changed')
    architecture = (root / 'docs/02-架构设计.md').read_text(encoding='utf-8')
    for required in ('候选修订（未实施）', '原 v1.0 记录', '冻结', 'activity_score',
                     '第 22 天', '第 28 天', '单写入者', '不接入 HF'):
        if required not in architecture:
            errors.append(f'Missing scope/erratum label: {required}')
    compiled = 0
    for path in sorted((root / 'scripts').glob('*.py')):
        try:
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            compiled += 1
        except SyntaxError as exc:
            errors.append(str(exc))
    return {'status': 'FAIL' if errors else 'PASS', 'markdown_files': len(md_paths),
            'relative_links_checked': link_count, 'json_fences_parsed': json_fences,
            'python_files_parsed': compiled, 'historical_report_preserved': preserved,
            'historical_git_blob_sha': ORIGINAL_BLOB, 'errors': errors,
            'scope': 'Mechanical documentation checks only; no engine or benchmark validation'}


if __name__ == '__main__':
    result = check(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result['status'] == 'PASS' else 1)
