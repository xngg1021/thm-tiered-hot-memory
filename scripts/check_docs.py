#!/usr/bin/env python3
"""Offline checks for published documents, source manifests and Python syntax."""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]

# Historical raw evidence is byte-immutable. These exact blobs predate 1.6 and
# were published without a final newline; any byte change removes the exception.
IMMUTABLE_RAW_JSON = {
    'reports/local-verification-20260913/beam/beam-10m-sample.json': '00e4451f4f21e10edf7b830a2066503c76ed350371ec9f3b657cc9203dec80f8',
    'reports/local-verification-20260913/beam/beam-all-results.json': '2bdeababeed33a0210d6417a931e98105ad41f86a40c3b56521577ed966672f6',
}


def _without_shell_comment(command, *, shell='bash', mask_substitutions=False):
    """Return the first command, excluding comments and outer separators."""
    quote = None
    escaped = False
    in_word = False
    substitutions = []
    ranges = []
    substitution_start = None

    def finish(end):
        result = command[:end]
        if mask_substitutions:
            for start, stop in ranges:
                result = result[:start] + 'x' * (stop - start) + result[stop:]
            if substitutions:
                result = result[:substitution_start] + 'x' * (end - substitution_start)
        return result

    index = 0
    while index < len(command):
        char = command[index]
        if escaped:
            escaped = False
            in_word = True
        elif char == ('`' if shell == 'powershell' else '\\') and quote != "'":
            escaped = True
            in_word = True
        elif char == '`' and shell == 'bash' and quote != "'":
            if substitutions and substitutions[-1][1] is None:
                quote, _ = substitutions.pop()
                in_word = True
                if not substitutions:
                    ranges.append((substitution_start, index + 1))
            else:
                if not substitutions:
                    substitution_start = index
                substitutions.append([quote, None])
                quote = None
                in_word = False
        elif ((command.startswith('$(', index) and quote != "'") or
              (command.startswith(('<(', '>('), index) and quote is None)):
            if not substitutions:
                substitution_start = index
            substitutions.append([quote, 1])
            quote = None
            in_word = False
            index += 1
        elif quote:
            if char == quote:
                quote = None
        elif char in ('"', "'"):
            quote = char
            in_word = True
        elif char == '#' and not in_word:
            return finish(index)
        elif not substitutions and char in ';|&':
            return finish(index)
        elif substitutions and substitutions[-1][1] is not None and char in '()':
            substitutions[-1][1] += 1 if char == '(' else -1
            if substitutions[-1][1] == 0:
                quote, _ = substitutions.pop()
                in_word = True
                if not substitutions:
                    ranges.append((substitution_start, index + 1))
            else:
                in_word = False
        else:
            in_word = not (char.isspace() or char in ';|&()<>')
        index += 1
    return finish(len(command))


def _native_commands(text):
    pattern = re.compile(r'^[ \t]*(?:(?:[$%>]|PS(?:[ \t]+[^>\n]*)?>)[ \t]+)?python(?:3)?[ \t]+research/(?:recall/(?:benchmark|lme_retrieval)|economics/run_suite)\.py\b')
    lines = iter(text.splitlines())
    fence = None
    for line in lines:
        match = re.match(r'^\s*```([\w-]*)\s*$', line)
        if match:
            fence = match.group(1).lower() if fence is None else None
            continue
        if not pattern.match(line):
            continue
        command = line
        shell = fence
        if shell not in ('powershell', 'pwsh', 'ps1', 'bash', 'sh', 'zsh', 'shell'):
            shell = 'powershell' if re.match(r'^\s*PS(?:[ \t]+[^>\n]*)?>[ \t]+', line) else 'bash'
        shell = 'powershell' if shell in ('powershell', 'pwsh', 'ps1') else 'bash'
        marker = '`' if shell == 'powershell' else '\\'
        while command.endswith(marker) and _without_shell_comment(command, shell=shell) == command:
            count = len(command) - len(command.rstrip(marker))
            if count % 2 == 0:
                break
            following = next(lines, None)
            if following is None:
                break
            command = command[:-1] + following
        yield command, shell


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


def _strong_closes_before_cjk(text: str) -> bool:
    """Detect only real closing ** delimiters followed immediately by CJK.

    A single regex can falsely span from one closing delimiter to the next
    opening delimiter on the same line. Splitting alternating strong-emphasis
    segments keeps this mechanical typography check localization-safe.
    """
    for line in text.splitlines():
        parts = line.split('**')
        for outside_after_close in parts[2::2]:
            if outside_after_close and '\u3400' <= outside_after_close[0] <= '\u9fff':
                return True
    return False


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
        historical_raw = IMMUTABLE_RAW_JSON.get(relative) == hashlib.sha256(raw).hexdigest()
        if (not raw.endswith(b'\n') or b'\r' in raw) and not historical_raw:
            errors.append(f'{relative}: require LF and final newline')
        if path.suffix == '.md':
            if any(line != line.rstrip() for line in text.splitlines()):
                errors.append(f'{relative}: trailing whitespace')
            for command, shell in _native_commands(text):
                lexer = shlex.shlex(_without_shell_comment(command, shell=shell, mask_substitutions=True), posix=False)
                lexer.whitespace_split = True
                lexer.commenters = ''
                try:
                    arguments = list(lexer)
                except ValueError:
                    arguments = []
                if not any(arg in ('--full-research', '"--full-research"', "'--full-research'") for arg in arguments):
                    errors.append(f'{relative}: native dataset command requires explicit --full-research')
            if text.count('```') % 2:
                errors.append(f'{relative}: unpaired triple-backtick fence')
            if relative.startswith('README') and _strong_closes_before_cjk(text):
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

    if 'thm/runtime/fabric/catalog.py' in texts:
        required_fabric = {'docs/20-zero-touch-runtime.md','docs/21-provider-fabric.md',
                           'docs/22-runtime-optimizer.md','docs/23-vector-index-providers.md',
                           'docs/provider-matrix.md','docs/provider-sources.json'}
        for name in sorted(required_fabric - texts.keys()):
            errors.append('Provider Fabric documentation missing: '+name)
        try:
            provenance = json.loads(texts['docs/provider-sources.json'])
            rows = provenance['providers']
            sys.path.insert(0, str(root))
            try:
                from thm.runtime.fabric.catalog import BUILTINS
            finally:
                sys.path.pop(0)
            catalog = {s.provider_id:s for s in BUILTINS}
            if len(rows) != len(catalog) or {r['provider_id'] for r in rows} != set(catalog):
                raise ValueError('provider audit and catalog identities differ')
            for row in rows:
                spec = catalog[row['provider_id']]
                if row['factory'] != spec.factory or row['maturity'] != 'L'+str(spec.maturity):
                    raise ValueError('provider audit maturity/factory differs from executable catalog')
                if urlsplit(row['official_url']).scheme != 'https' or not row['license_audit']:
                    raise ValueError('provider source URL or license audit missing')
                if row['hardware_validation'] != 'unvalidated' and spec.maturity < 5:
                    raise ValueError('provider audit overstates hardware evidence')
        except (KeyError, ValueError, TypeError, ImportError) as exc:
            errors.append('Provider Fabric source audit: '+str(exc))

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

    # Product-homepage parity applies only when this source tree publishes the
    # localized README family. Isolated checker fixtures intentionally contain
    # only the REQUIRED synthetic documents and must remain valid test inputs.
    if LOCALIZED_READMES & actual:
        missing_localized = sorted(LOCALIZED_READMES - actual)
        if missing_localized:
            errors.append('Missing localized README files: ' + ', '.join(missing_localized))

        homepage = texts.get('README.md', '')
        if '<!-- in-page-locales:start -->' in homepage or '<!-- locale:' in homepage:
            errors.append('README.md: embedded localized copies are not allowed; use standalone README files')

        # Shared markers are identities/protocol names and measured values that
        # intentionally remain language-neutral. Do not require English prose
        # vocabulary such as "cost" in translated homepages.
        common_markers = (
            '1.4.0', '1.5.0', '1.6.0', 'T0', 'T1', 'T2', 'T3', '72.52%', '69.39%',
            'Claude Code', 'Codex CLI', 'Gemini CLI', 'MCP v2', 'CHANGELOG.md',
            'docs/12-version-history.md', 'docs/16-zero-llm-retrieval-frontier.md',
            'Evaluation Fabric', 'LongMemEval-V2', 'BEAM', 'MemoryArena', 'StorageProfile',
            'docs/18-evaluation-fabric.md', '--wall-seconds 3300',
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

        expected_sections = ('architecture', 'philosophy', 'logical', 'tiers', 'compute',
            'physical', 'evaluation', 'evidence', 'harness', 'quickstart', 'acceptance',
            'invariants', 'boundary', 'documentation')
        def structure(text):
            chunks = re.split(r'<!-- section:([a-z]+) -->\n', text)
            ids = tuple(chunks[1::2])
            shapes = []
            for chunk in chunks[2::2]:
                headings = tuple(len(x) for x in re.findall(r'^(#{2,6}) ', chunk, re.M))
                fences = tuple(re.findall(r'^```[^\n]*\n.*?^```', chunk, re.M | re.S))
                tables = tuple(line.count('|') for line in chunk.splitlines() if line.startswith('|'))
                shapes.append((headings, fences, tables))
            return ids, shapes
        canonical_ids, canonical_shapes = structure(homepage)
        if canonical_ids != expected_sections:
            errors.append('README.md: invalid canonical section identities/order')
        for name in ALL_READMES:
            ids, shapes = structure(texts.get(name, ''))
            if ids != expected_sections or shapes != canonical_shapes:
                errors.append(f'{name}: README structural parity mismatch (sections/headings/fences/tables)')

    return {'status': 'FAIL' if errors else 'PASS', 'markdown_files': len(markdown),
            'relative_links_checked': links, 'json_fences_parsed': fences,
            'json_files_parsed': json_files, 'python_files_parsed': python_files,
            'historical_report_preserved': preserved, 'historical_git_blob_sha': ORIGINAL_BLOB,
            'errors': errors, 'scope': 'Mechanical document checks; external facts and engine behavior require separate tests'}


if __name__ == '__main__':
    result = check(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result['status'] == 'PASS' else 1)
