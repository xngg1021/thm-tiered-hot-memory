"""Bounded exact candidate projection; no inferred identities or label input.

This read-only projection changes packing order, not candidate membership,
canonical identity, activity or tier residency. Fixed RRF bonus: 0.25.
Over-complex queries fail soft; oversized source bodies get no identifier bonus.
"""
import re
import unicodedata

GENERIC = {'python', 'windows', 'model', 'project'}
MAX_IDENTIFIERS = 16
MAX_IDENTIFIER_CHARS = 256
MAX_SPEAKERS = 64
MAX_SPEAKER_CHARS = 128
MAX_BODY_CHARS = 8192
MAX_CANDIDATES = 3000  # three existing channels, each capped at 1000
IDENTIFIER = re.compile(r'https?://[^\s<>]+|\b[0-9a-f]{7,40}\b|\b[A-Z]+-\d+\b|\bv?\d+(?:\.\d+)+\b|`([^`]+)`')
# Punctuation that continues a name/path/URL is not a whole-identifier boundary.
# Terminal sentence punctuation is allowed; '.old' and '?revision' continue it.
LEFT = r'(?<![\w./\\:@#%&=~+?\-])'
RIGHT = r'(?!(?:[\w/\\:@#%&=~+\-]|[.?][\w/]))'
TOKEN_START = re.compile(LEFT)
TOKEN_END = re.compile(RIGHT)
URL_WRAPPERS = ('()', '[]', '{}', '（）', '【】', '《》', '〈〉', '「」',
                '『』', '〔〕', '〖〗', '〘〙', '〚〛', '｟｠', '｢｣', '“”', '‘’', '«»', '‹›')


def exact_pattern(values):
    return re.compile(LEFT + '(?:' + '|'.join(re.escape(v) for v in sorted(values, key=lambda value: (-len(value), value))) + ')' + RIGHT)


def present(value, text):
    """Exact, case-sensitive identifier occurrence, including compound boundaries."""
    return bool(exact_pattern([value]).search(text))


def reorder(rows, query, weight=0.25):
    if len(rows) > MAX_CANDIDATES or len(query) > 16000:
        return rows
    identifiers = set()
    for match in IDENTIFIER.finditer(query):
        value = match[0].strip('`')
        quoted = match[0].startswith('`')
        start, end = match.start() + int(quoted), match.end() - int(quoted)
        if not quoted and value.startswith(('https://', 'http://')):
            # Prose punctuation is outside unquoted URLs. Preserve balanced
            # path parentheses; count once so long wrapper tails stay linear.
            excess = {close: value.count(close) - value.count(opening)
                      for opening, close in URL_WRAPPERS}
            while end > start:
                char = query[end - 1]
                if char in '.,;!?:\"\'':
                    end -= 1
                elif excess.get(char, 0) > 0:
                    excess[char] -= 1
                    end -= 1
                elif ord(char) > 127 and char not in excess and unicodedata.category(char) in {'Po', 'Pe', 'Pf'}:
                    end -= 1
                else:
                    break
            value = query[start:end]
        if TOKEN_START.match(query, start) is None or TOKEN_END.match(query, end) is None:
            continue
        if value.lower() in GENERIC:
            continue
        if len(value) > MAX_IDENTIFIER_CHARS:
            return rows
        identifiers.add(value)
        if len(identifiers) > MAX_IDENTIFIERS:
            return rows
    # Compile at most two bounded patterns per projection, never inside a scan.
    names = {r['speaker'] for r in rows if r['speaker'] and len(r['speaker']) <= MAX_SPEAKER_CHARS
             and r['speaker'].lower() not in GENERIC}
    speakers = set()
    if names and len(names) <= MAX_SPEAKERS:
        speakers = {m[0] for m in exact_pattern(names).finditer(query)}
    pattern = exact_pattern(identifiers) if identifiers else None
    if not speakers and pattern is None:
        return rows
    matched = [r['rowid'] for r in rows if r['speaker'] in speakers or
               (pattern is not None and len(r['text']) <= MAX_BODY_CHARS and pattern.search(r['text']))]
    if not matched:
        return rows
    ranks = {rid: n for n, rid in enumerate(matched, 1)}
    scored = [(1 / (60 + n) + (weight / (60 + ranks[r['rowid']]) if r['rowid'] in ranks else 0), n, r)
              for n, r in enumerate(rows, 1)]
    return [r for _, _, r in sorted(scored, key=lambda x: (-x[0], x[1]))]
