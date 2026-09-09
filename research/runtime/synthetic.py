"""Tiny zero-model ignition and partial-evidence parity for bounded verification."""
from contextlib import closing
from pathlib import Path
import tempfile
from thm.retrieval import SearchIndex,Document
from thm.features import RetrievalFeatures

def smoke():
    with tempfile.TemporaryDirectory() as d,closing(SearchIndex(Path(d)/'i.sqlite')) as index:
        index.replace_scope('smoke',[Document('a','smoke','turn',0,'alpha memory'),Document('b','smoke','turn',1,'beta context')])
        first=index.search('smoke','alpha',mode='sparse')
        again=index.search('smoke','alpha',mode='sparse')
        if first['selected']!=again['selected']:raise ValueError('synthetic deterministic parity failed')
        partial=index.search('smoke','alpha',mode='sparse',features=RetrievalFeatures(segment=True))
        return {'schema':1,'status':'passed','generation_calls':0,'documents':2,
            'deterministic_parity':True,'feature_execution':bool(partial),'evidence':'tiny-synthetic-only'}
