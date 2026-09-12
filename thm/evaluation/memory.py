"""Duck-typed upstream memory interfaces backed by the existing SearchIndex."""
from pathlib import Path
from contextlib import contextmanager
from threading import RLock
from thm.retrieval import Document, SearchIndex, TokenCounter
from .adapters import trajectory_documents
from .contracts import nonempty


SNAPSHOT_MAX_BYTES = 16_000_000


class AgentMemory:
    """MemoryArena MemoryClient-compatible add/wrap_user_prompt interface.

    Instantiate once per task/user. Keep this object across that task's sessions;
    add only observations/actions produced by the agent/environment, never gold.
    """
    def __init__(self, path, scope, budget=600):
        self.scope = nonempty(scope)
        if type(budget) is not int or not 0 <= budget <= 32768:
            raise ValueError('invalid evidence budget')
        self.budget = budget
        if Path(path).exists():
            raise FileExistsError('native memory interface requires a fresh per-task database')
        self.path = Path(path)
        self.lock = RLock()
        self.closed = False
        # Connections are opened on the calling thread, including upstream query workers.
        index = SearchIndex(self.path, TokenCounter('utf8_bytes'))
        try:
            index.replace_scope(self.scope, [])
        finally:
            index.close()
        self.documents = []
        self.last_result = None

    @contextmanager
    def connection(self):
        with self.lock:
            if self.closed:
                raise RuntimeError('memory interface is closed')
            index = SearchIndex(self.path, TokenCounter('utf8_bytes'))
            try:
                yield index
            finally:
                index.close()

    def add(self, chunk):
        nonempty(chunk)
        with self.connection() as index:
            i = len(self.documents)
            doc = Document(f'event/{i}', self.scope, 'events', i, chunk)
            next_documents = [*self.documents, doc]
            index.replace_scope(self.scope, next_documents)
            self.documents = next_documents
            return {'status': 'stored', 'id': doc.id}

    def query(self, query):
        with self.connection() as index:
            self.last_result = index.search(self.scope, nonempty(query), mode='sparse', budget=self.budget)
            return self.last_result['context']

    def wrap_user_prompt(self, question):
        context = self.query(question)
        return f'{question}\n\nMemory evidence:\n{context}'

    def close(self):
        with self.lock:
            self.closed = True

    def save(self, output_dir):
        from dataclasses import asdict
        import json
        from .contracts import digest
        root = Path(output_dir)
        with self.lock:
            if self.closed:
                raise ValueError('memory interface closed')
            body = {'schema': 'thm-agent-memory/1', 'scope': self.scope, 'budget': self.budget,
                    'documents': [asdict(d) for d in self.documents]}
            encoded = json.dumps({**body, 'receipt_sha256': digest(body)}, ensure_ascii=False, allow_nan=False).encode('utf-8')
            if len(encoded) > SNAPSHOT_MAX_BYTES:
                raise ValueError('bounded memory snapshot required')
            root.mkdir(parents=True, exist_ok=True)
            import os
            import tempfile
            fd, temporary = tempfile.mkstemp(prefix='.thm-memory-', suffix='.pending', dir=root)
            try:
                with os.fdopen(fd, 'wb') as handle:
                    if handle.write(encoded) != len(encoded):
                        raise OSError('short snapshot write')
                    handle.flush()
                    os.fsync(handle.fileno())
                os.link(temporary, root/'thm-memory.json')  # atomic create-only publication
            finally:
                Path(temporary).unlink(missing_ok=True)

    def restore(self, input_dir):
        import json
        from .contracts import digest
        path = Path(input_dir)/'thm-memory.json'
        from thm._bounded_files import bounded_file_bytes
        value = json.loads(bounded_file_bytes(path, SNAPSHOT_MAX_BYTES).decode('utf-8'))
        checksum = value.pop('receipt_sha256', None)
        if checksum != digest(value) or value.get('schema') != 'thm-agent-memory/1' or value.get('scope') != self.scope or value.get('budget') != self.budget:
            raise ValueError('memory snapshot identity mismatch')
        documents = [Document(**row) for row in value['documents']]
        with self.connection() as index:
            index.replace_scope(self.scope, documents)
            self.documents = documents


class V2Memory(AgentMemory):
    """LongMemEval-V2 insert/query contract; explicit text-only operating point."""
    def insert(self, trajectory):
        docs = list(trajectory_documents(trajectory, self.scope))
        tid = trajectory['id']
        with self.connection() as index:
            next_documents = [d for d in self.documents if d.source != tid] + docs
            index.replace_scope(self.scope, next_documents)
            self.documents = next_documents

    def query(self, query, query_image=None):
        if query_image is not None:
            raise ValueError('text-only THM operating point cannot interpret query images')
        context = super().query(query)
        return [{'type': 'text', 'value': context}] if context else []


def register_longmemeval_v2():
    """Explicit opt-in registration inside an installed upstream harness process."""
    from memory_modules.memory import Memory, register_memory

    @register_memory
    class THMMemory(Memory):
        memory_type = 'thm_text'

        def __init__(self, memory_params):
            super().__init__(memory_params)
            import tempfile
            self._temp = tempfile.TemporaryDirectory(prefix='thm-v2-')
            self.backend = V2Memory(Path(self._temp.name) / 'index.sqlite', 'haystack',
                                    memory_params.get('budget', 600))

        def insert(self, trajectory):
            self.backend.insert(trajectory)

        def query(self, query, query_image=None):
            return self.backend.query(query, query_image)

        def close(self):
            self.backend.close()
            self._temp.cleanup()

        def _save_backend(self, output_dir):
            self.backend.save(output_dir)

        def _load_backend(self, input_dir):
            self.backend.restore(input_dir)

    return THMMemory
