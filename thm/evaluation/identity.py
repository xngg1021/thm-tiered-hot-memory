"""Implementation identity, independent of runtime probe imports."""
from pathlib import Path
from .contracts import digest


def implementation_identity():
    root = Path(__file__).resolve().parents[1]
    return digest({p.relative_to(root).as_posix(): digest(p.read_text(encoding='utf-8'))
                   for p in sorted(root.rglob('*.py'))})

