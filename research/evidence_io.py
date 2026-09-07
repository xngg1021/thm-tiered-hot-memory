"""Read-and-bind evidence bytes and exclusively create successor outputs."""
import hashlib
import json
from pathlib import Path


def read_json_bound(path):
    raw = Path(path).read_bytes()
    return json.loads(raw.decode('utf-8')), hashlib.sha256(raw).hexdigest()


def require_new_output(path):
    if Path(path).exists():
        raise FileExistsError(f'refusing to overwrite evidence: {Path(path).name}; choose a fresh successor filename')


def write_new_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects against a writer racing the initial preflight.
    # A partial file from an interrupted write remains consumed, never reused.
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(text)
