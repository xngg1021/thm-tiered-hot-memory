#!/usr/bin/env python3
"""BEAM benchmark: THM retrieval + DeepSeek answer generation + official unified judge.

Faithfully reproduces the official BEAM evaluation pipeline (src/answer_probing_questions
+ src/evaluation/compute_metrics.py), replacing the official BM25/FAISS retriever with
THM's SearchIndex. Answer generation uses the official `answer_generation_for_rag` prompt;
scoring uses the official `unified_llm_judge_base_prompt` (one judge call per rubric item,
averaged). All model calls go to DeepSeek via the OpenAI-compatible /v1 endpoint.
"""
import json, os, sys, time, re, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests

sys.path.insert(0, '/Users/shijunfu/thm-tiered-hot-memory')
from thm.retrieval import SearchIndex, TokenCounter
from thm.evaluation.adapters import BEAM

API_KEY = os.environ['DEEPSEEK_API_KEY']
BASE = 'https://api.deepseek.com/v1'
MODEL = os.environ.get('BEAM_LLM_MODEL', 'deepseek-v4-pro')
BUDGET = int(os.environ.get('BEAM_BUDGET', '4000'))

JUDGE_PROMPT = """You are an expert evaluator tasked with judging whether the LLM's response demonstrates compliance with the specified RUBRIC CRITERION.

## EVALUATION INPUTS
- RUBRIC CRITERION (what to check): <rubric_item>
- RESPONSE TO EVALUATE: <llm_response>

## EVALUATION RUBRIC:
The rubric defines a specific requirement, constraint, or expected behavior that the LLM response should demonstrate. 

**IMPORTANT**: Pay careful attention to whether the rubric specifies:
- **Positive requirements** (things the response SHOULD include/do)
- **Negative constraints** (things the response SHOULD NOT include/do, often indicated by "no", "not", "avoid", "absent")

## RESPONSIVENESS REQUIREMENT
A compliant response must be **on-topic** and attempt to answer it.
- If the response does not address the QUESTION, score **0.0** and stop.
- For negative constraints, both must hold: (a) the response is responsive to the QUESTION, and (b) the prohibited element is absent.

## SEMANTIC TOLERANCE RULES:
Judge by meaning, not exact wording.
- Accept **paraphrases** and **synonyms** that preserve intent.
- **Case/punctuation/whitespace** differences must be ignored.
- **Numbers/currencies/dates** may appear in equivalent forms (e.g., "$68,000", "68k", "68,000 USD", or "sixty-eight thousand dollars"). Treat them as equal when numerically equivalent.
- If the rubric expects a number or duration, prefer **normalized comparison** (extract and compare values) over string matching.

## STYLE NEUTRALITY (prevents style contamination):
Ignore tone, politeness, length, and flourish unless the rubric explicitly requires a format/structure (e.g., "itemized list", "no citations", "one sentence").
- Do **not** penalize hedging, voice, or verbosity if content satisfies the rubric.
- Only evaluate format when the rubric **explicitly** mandates it.

## SCORING SCALE:
- **1.0 (Complete Compliance)**: Fully complies with the rubric criterion.
  - Positive: required element present, accurate, properly executed (allowing semantic equivalents).
  - Negative: prohibited element **absent** AND response is **responsive**.
  
- **0.5 (Partial Compliance)**: Partially complies.
  - Positive: element present but minor inaccuracies/incomplete execution.
  - Negative: generally responsive and mostly avoids the prohibited element but with minor/edge violations.
  
- **0.0 (No Compliance)**: Fails to comply.
  - Positive: required element missing or incorrect.
  - Negative: prohibited element present **or** response is non-responsive/evasive even if the element is absent.

## EVALUATION INSTRUCTIONS:
1. **Understand the Requirement**: Determine if the rubric is asking for something to be present (positive) or absent (negative/constraint).

2. **Parse Compound Statements**: If the rubric contains multiple elements connected by "and" or commas, evaluate whether:
   - **All elements** must be present for full compliance (1.0)
   - **Some elements** present indicates partial compliance (0.5)
   - **No elements** present indicates no compliance (0.0)
   
3. **Check Compliance**: 
   - For positive requirements: Look for the presence and quality of the required element
   - For negative constraints: Look for the absence of the prohibited element

4. **Assign Score**: Based on compliance with the specific rubric criterion according to the scoring scale above.

5. **Provide Reasoning**: Explain whether the rubric criterion was satisfied and justify the score.

## OUTPUT FORMAT:
Return your evaluation in JSON format with two fields:

{
   "score": [your score: 1.0, 0.5, or 0.0],
   "reason": "[detailed explanation of whether the rubric criterion was satisfied and why this justified the assigned score]"
}

NOTE: ONLY output the json object, without any explanation before or after that
"""

ANSWER_PROMPT = """You are an assistant that MUST answer questions using ONLY the information provided in the context below. 

STRICT INSTRUCTIONS:
1. Answer ONLY based on the provided context
2. Do NOT use your internal knowledge

CONTEXT:
<context>

QUESTION:
<question>

ANSWER REQUIREMENTS:
- Be direct and concise
- Only output the answer to the question without any explanation 

RESPONSE:
"""


def chat(messages, temperature=0.0, retries=4):
    last = None
    for attempt in range(retries):
        try:
            r = requests.post(
                f'{BASE}/chat/completions',
                headers={'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'},
                json={'model': MODEL, 'messages': messages, 'temperature': temperature, 'max_tokens': 1024},
                timeout=180,
            )
            r.raise_for_status()
            return r.json()['choices'][0]['message']['content']
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def answer(context, question):
    prompt = ANSWER_PROMPT.replace('<context>', context).replace('<question>', question)
    return chat([{'role': 'user', 'content': prompt}]).strip()


def judge_one(rubric_item, llm_response):
    prompt = JUDGE_PROMPT.replace('<rubric_item>', rubric_item).replace('<llm_response>', llm_response)
    out = chat([{'role': 'user', 'content': prompt}]).strip()
    m = re.search(r'["\']score["\']\s*:\s*([0-9.]+)', out)
    if m:
        return float(m.group(1))
    m = re.search(r'([0-9]*\.?[0-9]+)', out)
    if m:
        v = float(m.group(1))
        return 1.0 if v > 1.0 else v
    return 0.0


def score_question(context, question, rubric):
    ans = answer(context, question)
    scores = [judge_one(item, ans) for item in rubric]
    return ans, statistics.mean(scores) if scores else 0.0, scores


def load_sample(chat_size, conv_id):
    base = Path('/tmp/beam-repo/chats') / chat_size / conv_id
    chat = json.load(open(base / 'chat.json'))
    pq = json.load(open(base / 'probing_questions/probing_questions.json'))
    return {'id': f'{chat_size}-{conv_id}', 'chat_size': chat_size, 'chat': chat, 'probing_questions': pq}


def run_conversation(chat_size, conv_id, adapter, question_limit=None):
    sample = load_sample(chat_size, conv_id)
    tasks = list(adapter.tasks([sample]))
    task0 = tasks[0][0]
    docs = task0.documents
    index = SearchIndex(f'/tmp/beam_idx_{chat_size}_{conv_id}.sqlite', TokenCounter('cl100k_base'))
    index.replace_scope(task0.scope, docs)
    results = []
    tasks = tasks[:question_limit] if question_limit else tasks
    for i, (task, gold) in enumerate(tasks):
        out = index.search(task.scope, task.query, mode='sparse', budget=BUDGET)
        context = '\n\n'.join(x['text'] for x in out['selected'] if x.get('complete'))
        rubric = gold.rubric if isinstance(gold.rubric, list) else [gold.rubric]
        category = task.id.split('/')[1]
        ans, sc, _ = score_question(context, task.query, rubric)
        results.append({'conversation': conv_id, 'category': category, 'score': sc,
                        'question': task.query, 'llm_response': ans, 'budget_used': out['budget_used']})
        print(f'[{chat_size}/{conv_id}] q{i+1}/{len(tasks)} [{category}] score={sc:.2f}', flush=True)
    index.close()
    return results


def summarize(results):
    by_cat = {}
    for r in results:
        by_cat.setdefault(r['category'], []).append(r['score'])
    print('\n=== 按能力类别准确率 ===')
    for cat in sorted(by_cat):
        v = by_cat[cat]
        print(f'  {cat:28s} {statistics.mean(v)*100:5.1f}%  (n={len(v)})')
    alls = [r['score'] for r in results]
    print(f'\n  总平均: {statistics.mean(alls)*100:.1f}%  (n={len(alls)})')


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--chat-size', default='100K')
    ap.add_argument('--conv', nargs='+', help='conversation ids (default: all in chat_size)')
    ap.add_argument('--question-limit', type=int, default=None)
    ap.add_argument('--workers', type=int, default=1)
    ap.add_argument('--out', default='/tmp/beam_results.json')
    args = ap.parse_args()

    adapter = BEAM()
    convs = args.conv if args.conv else sorted(
        [d for d in os.listdir(f'/tmp/beam-repo/chats/{args.chat_size}') if d.isdigit()], key=int)

    all_results = []
    if args.workers <= 1:
        for c in convs:
            all_results += run_conversation(args.chat_size, c, adapter, args.question_limit)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(run_conversation, args.chat_size, c, adapter, args.question_limit): c for c in convs}
            for f in as_completed(futs):
                all_results += f.result()

    json.dump(all_results, open(args.out, 'w'), ensure_ascii=False, indent=2)
    summarize(all_results)
