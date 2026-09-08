"""Core-only ignition gate: forbid optional model/provider imports and network."""
import importlib.abc
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


class NoModels(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'torch','numpy','sentence_transformers','openai','anthropic','onnxruntime','openvino'}:
            raise AssertionError('core imported optional backend: '+fullname)


def main():
    sys.meta_path.insert(0,NoModels())
    socket.socket.connect=lambda *args:(_ for _ in ()).throw(AssertionError('network forbidden'))
    from thm.retrieval import SearchIndex,Document
    from thm.harness import HarnessConfig,THMHarnessAdapter
    from thm.runtime.hardware import probe
    from thm.mcp_legacy_server import LegacyMCPServer
    with tempfile.TemporaryDirectory() as temp:
        db=Path(temp)/'index.sqlite';index=SearchIndex(db)
        index.replace_scope('core',[Document('1','core','s',0,'ERR_BUILD_42 deterministic memory')]);index.close()
        config=HarnessConfig(str(db),'core')
        with THMHarnessAdapter(config) as adapter:
            result=adapter.recall('ERR_BUILD_42');assert result['generation_calls']==0 and result['context']
        server=LegacyMCPServer(config)
        # Actual JSON-RPC handling, including startup, list, status and recall.
        try:
            messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'core-probe','version':'1'}}},
                {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'thm_status','arguments':{}}},
                {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'thm_recall','arguments':{'query':'ERR_BUILD_42'}}}]
            for message in messages:
                response=server.handle(message)
                assert response and 'error' not in response,response
        finally:server.close()
        probe()
    print(json.dumps({'status':'pass','generation_calls':0,'provider_calls':0,'network_calls':0,'mcp':['initialize','tools/list','thm_status','thm_recall']}))

if __name__=='__main__':main()
