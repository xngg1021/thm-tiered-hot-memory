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
ALL_READMES = ('README.md', *sorted(LOCALIZED_READMES))
LANGUAGE_LINKS = {
    'README.md', 'README.zh-CN.md', 'README.zh-TW.md', 'README.ja.md',
    'README.ko.md', 'README.es.md', 'README.fr.md', 'README.de.md',
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

    missing_localized = sorted(LOCALIZED_READMES - actual)
    if missing_localized:
        errors.append('Missing localized README files: ' + ', '.join(missing_localized))

    homepage = texts.get('README.md', '')
    if '<!-- in-page-locales:start -->' in homepage or '<!-- locale:' in homepage:
        errors.append('README.md: embedded localized copies are not allowed; use standalone README files')

    common_markers = (
        '1.4.0', 'T0', 'T1', 'T2', 'T3', '72.52%', '69.39%', 'cost',
        'Claude Code', 'Codex CLI', 'Gemini CLI', 'MCP v2', 'CHANGELOG.md',
        'docs/12-version-history.md', 'docs/16-zero-llm-retrieval-frontier.md',
    )
    for name in ALL_READMES:
        text = texts.get(name, '')
        if not text:
            errors.append(f'{name}: missing or unreadable')
            continue
        if len(text) < 4500:
            errors.append(f'{name}: product homepage is unexpectedly short')
        if len(re.findall(r'^## ', text, re.M)) < 8:
            errors.append(f'{name}: incomplete product homepage section parity')
        for marker in common_markers:
            if marker not in text:
                errors.append(f'{name}: missing current product/evidence marker {marker}')
        for link in LANGUAGE_LINKS - {name}:
            if link not in text:
                errors.append(f'{name}: missing language switch link {link}')
        for transient in ('in-page-locales:start', 'locale:zh-CN:start',
                          'current release status —', 'Feature PR #', 'CI is running'):
            if transient in text:
                errors.append(f'{name}: transient/development chronology leaked onto product homepage: {transient}')

    for marker in ('Design philosophy', 'How far can agent memory go without another LLM call?',
                   '1.4.0', '72.52%', 'Version history and recovery'):
        if marker not in homepage:
            errors.append(f'README.md: missing productized homepage marker {marker}')

    return {'status': 'FAIL' if errors else 'PASS', 'markdown_files': len(markdown),
            'relative_links_checked': links, 'json_fences_parsed': fences,
            'json_files_parsed': json_files, 'python_files_parsed': python_files,
            'historical_report_preserved': preserved, 'historical_git_blob_sha': ORIGINAL_BLOB,
            'errors': errors, 'scope': 'Mechanical document checks; external facts and engine behavior require separate tests'}


if __name__ == '__main__':
    result = check(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result['status'] == 'PASS' else 1)
