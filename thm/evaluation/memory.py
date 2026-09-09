"""Duck-typed upstream memory interfaces backed by the existing SearchIndex."""
from pathlib import Path
from thm.retrieval import Document, SearchIndex, TokenCounter
from .adapters import trajectory_documents
from .contracts import nonempty


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
        self.index = SearchIndex(Path(path), TokenCounter('utf8_bytes'))
        self.documents = []
        self.last_result = None

    def add(self, chunk):
        nonempty(chunk)
        i = len(self.documents)
        doc = Document(f'event/{i}', self.scope, 'events', i, chunk)
        next_documents = [*self.documents, doc]
        self.index.replace_scope(self.scope, next_documents)
        self.documents = next_documents
        return {'status': 'stored', 'id': doc.id}

    def query(self, query):
        self.last_result = self.index.search(self.scope, nonempty(query), mode='sparse', budget=self.budget)
        return self.last_result['context']

    def wrap_user_prompt(self, question):
        context = self.query(question)
        return f'{question}\n\nMemory evidence:\n{context}'

    def close(self):
        self.index.close()


class V2Memory(AgentMemory):
    """LongMemEval-V2 insert/query contract; explicit text-only operating point."""
    def insert(self, trajectory):
        docs = list(trajectory_documents(trajectory, self.scope))
        tid = trajectory['id']
        next_documents = [d for d in self.documents if d.source != tid] + docs
        self.index.replace_scope(self.scope, next_documents)
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
            raise NotImplementedError('prebuilt persistence is not supported by thm_text')

        def _load_backend(self, input_dir):
            raise NotImplementedError('prebuilt persistence is not supported by thm_text')

    return THMMemory
