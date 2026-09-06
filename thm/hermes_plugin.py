"""Optional Hermes provider. Imported only by Hermes plugin discovery.

No automatic conversation export, feedback reinforcement, source writes or model
calls. An explicitly imported local retrieval index is required. Dynamic recall
returns on the current query, not stale cached text from a prior session.
"""
from __future__ import annotations
import json
import os
import sqlite3
from pathlib import Path
import threading
from .retrieval import SearchIndex, TokenCounter, SentenceEncoder
from agent.memory_provider import MemoryProvider, RecallStatus


class THMProvider(MemoryProvider):
    @property
    def name(self): return 'thm'

    def __init__(self, config=None):
        self.config = config or {}
        self._lock = threading.RLock()
        self.last = None
        self.error = None
        self.path = None
        self.session_id = None
        self.encoder = None
        self._index = None
        self.scope = self.config.get('scope') or os.environ.get('THM_RECALL_SCOPE')

    def is_available(self):
        # File access and model loading belong to initialize; no network readiness calls.
        return bool(self.scope)

    def unavailable_reason(self):
        return '' if self.scope else 'Set THM_RECALL_SCOPE and import an explicit local scope first.'

    def initialize(self, session_id, **kwargs):
        home = kwargs.get('hermes_home')
        if not home:
            raise ValueError('Hermes must supply profile-scoped hermes_home')
        with self._lock:
            self.session_id = session_id
            self.path = Path(home)/'memories/.thm/recall.sqlite3'
            self.counter = TokenCounter(self.config.get('counter', 'utf8_bytes'))
            self.budget = int(self.config.get('budget', 600))
            self.mode = self.config.get('mode', 'sparse')
            model = self.config.get('model_path')
            if model:
                self.encoder = SentenceEncoder(model, self.config['model_id'])
            self.last = None
            if self._index: self._index.close()
            self._index = SearchIndex(self.path, self.counter) if self.path.is_file() else None

    def system_prompt_block(self):
        return ''

    def prefetch(self, query, *, session_id=''):
        with self._lock:
            self.last, self.error = None, None
            if session_id and session_id != self.session_id:
                self.error = 'session mismatch; call on_session_switch first'
                return ''
            if not query.strip() or self.path is None or not self.path.is_file():
                return ''
            try:
                if self._index is None:
                    self._index = SearchIndex(self.path, self.counter)
                index = self._index
                out = index.search(self.scope, query, budget=self.budget, mode=self.mode,
                                   encoder=self.encoder, model_id=self.config.get('model_id'))
                self.last = out
                return out['context']
            except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
                self.error = str(exc)
                return ''

    def recall_status(self):
        if not self.last or not self.last['selected']: return None
        return RecallStatus(provider_label='THM', count=len(self.last['selected']))

    def on_session_switch(self, new_session_id, **kwargs):
        with self._lock:
            self.session_id = new_session_id
            self.last = None

    def get_tool_schemas(self):
        return [{'name':'thm_recall_status', 'description':'Return last recall metadata without source text.',
                 'parameters':{'type':'object','properties':{},'additionalProperties':False}}]

    def handle_tool_call(self, tool_name, args, **kwargs):
        if tool_name != 'thm_recall_status':
            return json.dumps({'error':'unknown THM tool'})
        with self._lock:
            return json.dumps({'error':self.error, 'returned_ids':[x['id'] for x in self.last['selected']] if self.last else [],
                               'usefulness':'unverified', 'budget_used':self.last['budget_used'] if self.last else 0})

    def on_memory_write(self, action, target, content, metadata=None):
        # A write is NOT a hit. Imported snapshots must be explicitly refreshed.
        self.last = None

    def shutdown(self):
        with self._lock:
            self.last = None
            self.encoder = None
            if self._index: self._index.close()
            self._index = None


def register(ctx):
    ctx.register_memory_provider(THMProvider())
