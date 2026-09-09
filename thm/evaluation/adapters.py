"""Native input interfaces. Only allowlisted source fields enter the dataplane."""
from .contracts import Task, GroundTruth, nonempty
from thm.retrieval import Document
from thm.sources import locomo_documents


class LoCoMo:
    name, protocol = 'locomo', 'LoCoMo Protocol 2'

    def tasks(self, source):
        from .parsing import evidence_ids
        for sample in source:
            docs = tuple(locomo_documents(sample))
            known = {d.id for d in docs}
            scope = str(sample['sample_id'])
            for i, qa in enumerate(sample['qa']):
                if type(qa['category']) is not int or qa['category'] not in range(1, 6):
                    raise ValueError('unsupported LoCoMo category')
                gold, malformed = evidence_ids(qa.get('evidence', []))
                task = Task(f'{scope}/{i}', scope, qa['question'], docs)
                yield task, GroundTruth(task.id, tuple(sorted(gold)), resolved=not malformed and gold <= known,
                    diagnostic_only=qa['category'] == 5, answer=qa.get('answer'))


class LongMemEvalS:
    name, protocol = 'longmemeval-s', 'LongMemEval-S session coverage 1'

    def tasks(self, source):
        for sample in source:
            sessions, ids = sample['haystack_sessions'], sample['haystack_session_ids']
            if len(sessions) != len(ids):
                raise ValueError('unaligned haystack sessions')
            scope = str(sample['question_id'])
            docs = []
            for i, (sid, messages) in enumerate(zip(ids, sessions)):
                nonempty(sid)
                for j, message in enumerate(messages):
                    text = message['content']
                    if not isinstance(text, str):
                        raise ValueError('message content must be text')
                    if text.strip():
                        role = message.get('role', '')
                        docs.append(Document(f'{sid}~{i}#{j}', scope, sid, j,
                            f'{role}: {text}' if role else text, speaker=role, source=sid))
            gold = tuple(sorted(set(sample['answer_session_ids'])))
            task = Task(scope, scope, sample['question'], tuple(docs))
            yield task, GroundTruth(scope, gold, 'session', set(gold) <= {d.source for d in docs}, answer=sample.get('answer'))


def trajectory_documents(trajectory, scope):
    """Public V2 states (accessibility_tree/text); screenshots are not interpreted."""
    tid = nonempty(trajectory['id'])
    states = trajectory['states']
    if not isinstance(states, list) or not states:
        raise ValueError('public trajectory states required')
    for i, state in enumerate(states):
        text = state.get('accessibility_tree', state.get('text'))
        if not isinstance(text, str):
            raise ValueError('state text required')
        action = state.get('action') or ''
        url = nonempty(state['url'])
        if not isinstance(action, str):
            raise ValueError('action must be text')
        yield Document(f'{tid}#{i}', scope, tid, i, f'{url}\n{text}\n{action}', source=tid)


class LongMemEvalV2:
    name, protocol = 'longmemeval-v2', 'public trajectory states / text-only 1'

    def tasks(self, source):
        # Explicit THM envelope pairs upstream public trajectories with questions.
        for sample in source:
            scope = nonempty(sample['id'])
            docs = tuple(d for t in sample['trajectories'] for d in trajectory_documents(t, scope))
            for i, qa in enumerate(sample['questions']):
                task = Task(f'{scope}/{i}', scope, qa['question'], docs, query_image=qa.get('query_image'))
                yield task, GroundTruth(task.id, unit='unavailable', answer=qa.get('answer'))


class BEAM:
    name, protocol = 'beam', 'native batches/turns + probing_questions 1'

    def tasks(self, source):
        for sample in source:
            scope = nonempty(sample['id'])
            chat = sample['chat']
            if sample['chat_size'] == '10M' and any(not isinstance(plan, dict) or len(plan) != 1 for plan in chat):
                raise ValueError('10M plan requires exactly one batch collection')
            batches = [batch for plan in chat for batch in next(iter(plan.values()))] if sample['chat_size'] == '10M' else chat
            docs = []
            for bi, batch in enumerate(batches):
                for ti, turn in enumerate(batch['turns']):
                    for mi, message in enumerate(turn):
                        text = nonempty(message['content'])
                        docs.append(Document(f'{bi}:{ti}:{mi}', scope, str(bi), len(docs),
                                             text, speaker=message['role'], source=str(bi)))
            for category, questions in sample['probing_questions'].items():
                for i, qa in enumerate(questions):
                    task = Task(f'{scope}/{category}/{i}', scope, qa['question'], tuple(docs))
                    yield task, GroundTruth(task.id, unit='unavailable',
                        answer=qa.get('ideal_answer', qa.get('ideal_response')), rubric=qa.get('rubric'))


class MemoryArena:
    name, protocol = 'memoryarena', 'native multi-session tasks / agent-benchmark 1'

    def tasks(self, source):
        for sample in source:
            scope = str(sample['id'])
            questions, answers = sample['questions'], sample['answers']
            if len(questions) != len(answers):
                raise ValueError('unaligned subtasks')
            backgrounds = sample.get('backgrounds', '')
            if not backgrounds and 'base_person' in sample:
                import json
                backgrounds = json.dumps(sample['base_person'], ensure_ascii=False)
            if isinstance(backgrounds, list) and len(backgrounds) != len(questions):
                raise ValueError('unaligned backgrounds')
            for i, question in enumerate(questions):
                background = backgrounds[i] if isinstance(backgrounds, list) else backgrounds
                if not isinstance(background, str):
                    raise ValueError('background must be text')
                docs = (Document(f'background/{i}', scope, 'background', i, background),) if background.strip() else ()
                task = Task(f'{scope}/{i}', scope, question, docs, sequence=i)
                yield task, GroundTruth(task.id, unit='unavailable', answer=answers[i])


ADAPTERS = {a.name: a for a in (LoCoMo(), LongMemEvalS(), LongMemEvalV2(), BEAM(), MemoryArena())}
