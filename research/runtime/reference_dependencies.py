"""Auditable reference import closure, without importing optional ML libraries."""
import ast
import hashlib
from pathlib import Path

# IsolatedEncoder starts worker through `python -m`, not a Python import.
ROOTS = ('research.recall.benchmark', 'research.recall.lme_retrieval',
         'thm.runtime.worker', 'research.runtime.bounds',
         'research.runtime.reference_dependencies')

# Exact import edges outside the reference worker's `serve` execution path.
# New imports (including new symbols from these modules) are included by default.
NON_REFERENCE_IMPORTS = {
    ('thm.runtime.worker', 'thm.runtime.micro',
     ('DOCUMENTS', 'QUERIES', 'CORPUS_SHA', 'BUILD_DOCUMENTS', 'BUILD_WORKLOAD_SHA',
      'BULK_QUERIES', 'QUERY_WORKLOAD_SHA')): 'measure-only calibration corpus',
    ('thm.runtime.worker', 'thm.runtime.autotune',
     ('retrieval_signature',)): 'measure-only calibration comparison',
    ('thm.runtime.worker', 'thm.runtime.prepare', ('convert',)): 'prepare-only conversion',
}


def semantic_manifest(root=None):
    """Return a sorted path -> SHA-256 manifest of transitive local imports.

    Includes lazy imports, package initializers and the subprocess entrypoint.
    A new static local dependency is followed automatically. Unresolvable local
    imports fail closed instead of allowing reuse with an incomplete key.
    """
    root = Path(root) if root is not None else Path(__file__).resolve().parents[2]

    def locate(module):
        path = root.joinpath(*module.split('.'))
        for candidate in (path.with_suffix('.py'), path / '__init__.py'):
            if candidate.is_file():
                return candidate
        return None

    pending = list(ROOTS)
    seen = set()
    manifest = {}
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        seen.add(module)
        path = locate(module)
        if path is None:
            # PEP 420 namespace packages have no executable initializer.
            if root.joinpath(*module.split('.')).is_dir():
                continue
            raise ValueError('unresolved reference dependency: ' + module)
        raw = path.read_bytes()
        manifest[path.relative_to(root).as_posix()] = hashlib.sha256(raw).hexdigest()
        parts = module.split('.')
        pending.extend('.'.join(parts[:i]) for i in range(1, len(parts)))
        package = parts if path.name == '__init__.py' else parts[:-1]
        for node in ast.walk(ast.parse(raw, filename=str(path))):
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = '.'.join(package[:len(package) - node.level + 1]) if node.level else ''
                target = '.'.join(part for part in (base, node.module) if part)
                edge = (module, target, tuple(alias.name for alias in node.names))
                if edge in NON_REFERENCE_IMPORTS:
                    continue
                imports = [target]
                # `from package import submodule` also executes submodule.py.
                imports += [target + '.' + alias.name for alias in node.names
                            if locate(target + '.' + alias.name) is not None]
            elif isinstance(node, ast.Call):
                dynamic = (isinstance(node.func, ast.Name) and node.func.id == '__import__') or (
                    isinstance(node.func, ast.Attribute) and node.func.attr == 'import_module')
                if dynamic:
                    if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                        raise ValueError('dynamic reference import requires an explicit dependency: ' + module)
                    imports = [node.args[0].value]
            pending.extend(name for name in imports if name.split('.')[0] in ('thm', 'research'))
    return dict(sorted(manifest.items()))
