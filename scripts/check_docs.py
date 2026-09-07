#!/usr/bin/env python3
"""Offline checks for published documents, source manifests and Python syntax."""
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
REQUIRED = {'README.md', 'docs/01-研究综述.md', 'docs/02-架构设计.md', REPORT,
            'docs/03-validation-contract.md', 'docs/04-related-work.md',
            'docs/05-hermes-upstream.md', 'docs/README.md', 'docs/06-engine-guide.md',
            'docs/07-implementation-status.md', 'docs/08-testing-and-release.md'}
LOCALIZED_READMES = {
    'README.zh-CN.md', 'README.zh-TW.md', 'README.ja.md', 'README.ko.md',
    'README.es.md', 'README.fr.md', 'README.de.md',
}
LOCALE_CODES = {
    'README.zh-CN.md': 'zh-CN', 'README.zh-TW.md': 'zh-TW',
    'README.ja.md': 'ja', 'README.ko.md': 'ko', 'README.es.md': 'es',
    'README.fr.md': 'fr', 'README.de.md': 'de',
}


def check(root: Path) -> dict:
    root = Path(root).resolve()
    errors, texts = [], {}
    try:
        paths = sorted(p for p in root.rglob('*') if p.is_file()
                       and not any(part in ('.git', '.venv', 'venv', '__pycache__') for part in p.relative_to(root).parts))
    except OSError as exc:
        return {'status': 'FAIL', 'errors': [f'Cannot enumerate documents: {exc}']}
    markdown = [p for p in paths if p.suffix == '.md']
    actual = {p.relative_to(root).as_posix() for p in markdown}
    missing = sorted(REQUIRED - actual)
    if missing:
        errors.append('Missing required documents: ' + ', '.join(missing))
    links = fences = json_files = python_files = 0
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if path.suffix not in ('.md', '.json', '.py'):
            continue
        try:
            if path.is_symlink():
                raise OSError('symlink is not a publishable source')
            raw = path.read_bytes()
            text = raw.decode('utf-8')
            texts[relative] = text
        except (OSError, UnicodeError) as exc:
            errors.append(f'{relative}: unavailable/invalid UTF-8 ({type(exc).__name__})')
            continue
        if not raw.endswith(b'\n') or b'\r' in raw:
            errors.append(f'{relative}: require LF and final newline')
        if path.suffix == '.md':
            if any(line != line.rstrip() for line in text.splitlines()):
                errors.append(f'{relative}: trailing whitespace')
            if text.count('```') % 2:
                errors.append(f'{relative}: unpaired triple-backtick fence')
            if relative.startswith('README') and re.search(r'\*\*[^*\n]+\*\*[\u3400-\u9fff]', text):
                errors.append(f'{relative}: strong emphasis closes directly before CJK text')
            for target in re.findall(r'\[[^\]\n]+\]\(([^\s)]+)\)', text):
                try:
                    parsed = urlsplit(target)
                    if parsed.scheme or parsed.netloc or not parsed.path:
                        continue
                    links += 1
                    destination = (path.parent / unquote(parsed.path)).resolve()
                    if not destination.is_relative_to(root) or not destination.is_file():
                        errors.append(f'{relative}: missing/outside relative link {target}')
                except (ValueError, OSError):
                    errors.append(f'{relative}: invalid link {target}')
            for block in re.findall(r'^```json\s*\n(.*?)^```\s*$', text, re.M | re.S):
                fences += 1
                try:
                    json.loads(block)
                except ValueError as exc:
                    errors.append(f'{relative}: JSON fence: {exc}')
        elif path.suffix == '.json':
            try:
                value = json.loads(text)
                json_files += 1
                if relative == 'docs/related-work-sources.json':
                    systems = value.get('systems') if isinstance(value, dict) else None
                    if not isinstance(systems, list):
                        raise ValueError('sources.systems must be a list')
                    ids = [s.get('id') for s in systems if isinstance(s, dict)]
                    if len(ids) != len(systems) or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
                        raise ValueError('source system IDs must be unique strings')
                    for system in systems:
                        for source in system.get('sources', []):
                            if not isinstance(source, dict) or urlsplit(source.get('url', '')).scheme not in ('https', 'http'):
                                raise ValueError('invalid source URL')
            except (ValueError, TypeError, AttributeError) as exc:
                errors.append(f'{relative}: invalid JSON/schema: {exc}')
        else:
            try:
                ast.parse(text, filename=relative)
                python_files += 1
            except (SyntaxError, ValueError) as exc:
                errors.append(f'{relative}: invalid Python syntax: {exc}')
    report = texts.get(REPORT, '')
    preserved = False
    if report.count(START) != 1 or report.count(END) != 1:
        errors.append('Missing or duplicated historical-report delimiters')
    else:
        original = report.split(START, 1)[1].split(END, 1)[0].encode('utf-8')
        preserved = hashlib.sha1(f'blob {len(original)}\0'.encode() + original).hexdigest() == ORIGINAL_BLOB
        if not preserved:
            errors.append('Historical report bytes changed')
    if 'docs/related-work-sources.json' not in texts:
        errors.append('Source manifest missing or unreadable')
    if LOCALIZED_READMES & actual:
        missing_localized = sorted(LOCALIZED_READMES - actual)
        if missing_localized:
            errors.append('Missing localized README files: ' + ', '.join(missing_localized))
        for localized in sorted(LOCALIZED_READMES & actual):
            text = texts.get(localized, '')
            for marker in ('1.4.0', 'archive/v1.4.0-stable', 'Claude Code',
                           'Codex CLI', 'Gemini CLI', 'MCP v2', 'accepted/stable'):
                if marker not in text:
                    errors.append(f'{localized}: missing localized release parity marker {marker}')
            headings = len(re.findall(r'^## ', text, re.M))
            if headings < 5:
                errors.append(f'{localized}: incomplete section parity ({headings} sections)')
            code = LOCALE_CODES[localized]
            expected_body = '\n'.join(text.splitlines()[4:]).strip()
            homepage = texts.get('README.md', '')
            match = re.search(
                rf'<!-- locale:{re.escape(code)}:start -->\n(.*?)\n'
                rf'<!-- locale:{re.escape(code)}:end -->', homepage, re.S)
            if not match or match.group(1).strip() != expected_body:
                errors.append(f'{localized}: homepage language panel is missing or stale')
        homepage = texts.get('README.md', '')
        for marker in ('1.4.0 accepted/stable implementation milestone',
                       'archive/v1.4.0-stable',
                       'docs/14-residency-control-plane.md',
                       'docs/15-hermes-warm-directory.md'):
            if marker not in homepage:
                errors.append(f'README.md: missing current 1.4 homepage marker {marker}')
    return {'status': 'FAIL' if errors else 'PASS', 'markdown_files': len(markdown),
            'relative_links_checked': links, 'json_fences_parsed': fences,
            'json_files_parsed': json_files, 'python_files_parsed': python_files,
            'historical_report_preserved': preserved, 'historical_git_blob_sha': ORIGINAL_BLOB,
            'errors': errors, 'scope': 'Mechanical document checks; external facts and engine behavior require separate tests'}


if __name__ == '__main__':
    result = check(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result['status'] == 'PASS' else 1)
