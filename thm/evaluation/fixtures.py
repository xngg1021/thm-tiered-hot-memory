"""Original tiny native-shaped fixtures; no benchmark dataset redistribution."""
FIXTURES = {
 'locomo': [{'sample_id': 'fixture-locomo', 'conversation': {'session_1': [
     {'dia_id': 'D1:1', 'speaker': 'A', 'text': 'The observatory access code is cobalt.'},
     {'dia_id': 'D1:2', 'speaker': 'B', 'text': 'The museum opens on Tuesday.'}]},
     'qa': [{'question': 'observatory access code', 'evidence': ['D1:1'], 'category': 4, 'answer': 'cobalt'},
            {'question': 'observatory and museum', 'evidence': ['D1:1', 'D1:2'], 'category': 1},
            {'question': 'unknown', 'evidence': [], 'category': 5}]}],
 'longmemeval-s': [{'question_id': 'fixture-lme', 'question': 'observatory access code',
     'haystack_session_ids': ['s1', 's2'], 'haystack_sessions': [
         [{'role': 'user', 'content': 'The observatory access code is cobalt.'}],
         [{'role': 'user', 'content': 'The museum opens on Tuesday.'}]],
     'answer_session_ids': ['s1'], 'answer': 'cobalt'}],
 'longmemeval-v2': [{'id': 'fixture-v2', 'trajectories': [
     {'id': 'trajectory-1', 'goal': 'Open the observatory', 'start_url': 'https://fixture.invalid',
      'states': [{'url': 'https://fixture.invalid', 'accessibility_tree': 'observatory access code cobalt',
                  'action': 'click open', 'screenshot': 'not-interpreted.png'}]}],
      'questions': [{'question': 'observatory access code', 'answer': 'cobalt'}]}],
 'beam': [{'id': 'fixture-beam', 'chat_size': '100K', 'chat': [{'turns': [[
     {'role': 'user', 'content': 'The observatory access code is cobalt.'},
     {'role': 'assistant', 'content': 'The museum opens on Tuesday.'}]]}],
     'probing_questions': {'information_extraction': [
         {'question': 'observatory access code', 'ideal_answer': 'cobalt', 'rubric': ['cobalt']}]}}],
 'memoryarena': [{'id': 'fixture-arena', 'questions': ['Find the observatory code', 'Reuse the code'],
                  'answers': ['cobalt', 'cobalt'], 'backgrounds': ['An observatory has a code.', 'Reuse earlier experience.']}],
}
