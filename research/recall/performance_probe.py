"""Isolated before/after lookup timings; not a LoCoMo or answer-quality test."""
import argparse, hashlib, importlib.util, json, platform, statistics, sys, tempfile, time, types
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', required=True, type=Path)
parser.add_argument('--candidate', required=True, type=Path)
parser.add_argument('--output', required=True, type=Path)
args=parser.parse_args()

def load(name, path):
    package=types.ModuleType(name);package.__path__=[str(path.parent)];sys.modules[name]=package
    name += '.retrieval'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def percent(values, q):
    a=sorted(values); return a[int((len(a)-1)*q)]

def run(module, directory):
    ix=module.SearchIndex(directory/'recall.sqlite')
    docs=[module.Document(str(i),'scope',f'session-{i//20}',i%20,
          f'Project {i} uses database service {i%13} on port {8000+i}. '
          f'The configuration belongs to environment {i%7}. '+('Extra unchanged background. '*5),
          speaker='Alice' if i%2 else 'Bob') for i in range(500)]
    ix.replace_scope('scope',docs)
    queries=[f'Project {i*3} database port configuration' for i in range(80)]
    uncached=[]; outputs=[]
    for query in queries:
        start=time.perf_counter(); out=ix.search('scope',query,budget=600)
        uncached.append((time.perf_counter()-start)*1000)
        outputs.append((out['context'],out['ranked_ids']))
    query=queries[-1]
    repeat=[]
    for _ in range(200):
        start=time.perf_counter(); out=ix.search('scope',query,budget=600)
        repeat.append((time.perf_counter()-start)*1000)
    ix.close()
    return {'uncached_p50_ms':statistics.median(uncached),'uncached_p95_ms':percent(uncached,.95),
            'repeated_p50_ms':statistics.median(repeat),'repeated_p95_ms':percent(repeat,.95)},outputs

base=load('thm_perf_base',args.baseline/'thm/retrieval.py')
fixed=load('thm_perf_fixed',args.candidate/'thm/retrieval.py')
with tempfile.TemporaryDirectory() as temp:
    a,o1=run(base,Path(temp)/'base'); b,o2=run(fixed,Path(temp)/'fixed')
result={'kind':'synthetic_same_output_lookup_microbenchmark','documents':500,'different_queries':80,
        'repeated_queries':200,'counter':'utf8_bytes','budget':600,
        'base':a,'patched':b,'all_80_contexts_and_rankings_identical':o1==o2,
        'python':platform.python_version(),'platform':platform.system(),
        'source_sha256':{k:hashlib.sha256((p/'thm/retrieval.py').read_bytes()).hexdigest() for k,p in [('baseline',args.baseline),('candidate',args.candidate)]},
        'limits':['Not full LoCoMo','Not user-perceived latency','No semantic model calls',
                  'One local process environment; no universal speedup claim',
                  'Repeated-query cache benefit is reported separately from uncached work']}
assert o1==o2
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
