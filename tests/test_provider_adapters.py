"""Public SDK call fixtures: execution code coverage, never hardware acceptance."""
from dataclasses import replace
from pathlib import Path
import contextlib
import io
import json
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock
import numpy as np

from thm.runtime.fabric.catalog import BUILTINS
from thm.runtime.fabric.inference import TorchInference, OrtInference, OpenVINOInference, CoreMLInference, MIGraphXInference
from thm.runtime.fabric.indexes import ExactAccelerator, HNSWGeneric
from thm.runtime.fabric.native import CuvsProvider, McFaissProvider, WindowsMLCatalog
from thm.runtime.fabric.registry import ProviderUnavailable, builtin_registry
from thm.runtime.fabric.service import RuntimeService, ResidentExecutor
from thm.runtime.fabric.store import ProfileStore
from thm.runtime.testing import FakeEncoder
from thm.retrieval import SearchIndex, TokenCounter
from test_provider_fabric import documents, index_identity, key


def spec(name):
    return next(s for s in BUILTINS if s.provider_id == name)


class Tensor(np.ndarray):
    def cpu(self):
        return self
    def numpy(self):
        return np.asarray(self)


def tensor(values, **kw):
    return np.asarray(values, dtype=kw.get('dtype', np.float32)).copy().view(Tensor)


def torch_fixture(vendor):
    api = types.SimpleNamespace(is_available=lambda: True, synchronize=mock.Mock())
    return types.SimpleNamespace(__version__='fixture-metax' if vendor == 'metax' else 'fixture',
        version=types.SimpleNamespace(hip='fixture' if vendor == 'amd' else None, cuda='fixture', maca='fixture' if vendor == 'metax' else None),
        cuda=api, mps=api, xpu=api, npu=api, musa=api, mlu=api, backends=types.SimpleNamespace(mps=api),
        float32=np.float32, tensor=mock.Mock(side_effect=tensor), as_tensor=tensor,
        argsort=lambda values,dim,descending,stable: np.argsort(-values,axis=dim,kind='stable').view(Tensor),
        gather=lambda values,dim,order: np.take_along_axis(values,order,axis=dim).view(Tensor))


class VendorFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.bundle = self.root/'model'; self.bundle.mkdir()
        self.model = self.bundle/'model.onnx'; self.model.write_bytes(b'local fixture')

    def test_every_framework_family_discover_prepare_execute_receipt(self):
        for vendor in ('nvidia','amd','intel','apple','ascend','musa','cambricon','metax'):
            with self.subTest(vendor=vendor):
                torch = torch_fixture(vendor)
                model = mock.Mock(); model.encode.return_value = np.asarray([[1.,0.],[1.,0.]])
                sentence = types.SimpleNamespace(SentenceTransformer=mock.Mock(return_value=model))
                modules = {'torch':torch, 'sentence_transformers':sentence,
                           'torch_npu':types.SimpleNamespace(), 'torch_mlu':types.SimpleNamespace(), 'torch_musa':types.SimpleNamespace()}
                with mock.patch.dict(sys.modules,modules):
                    provider = TorchInference(spec(vendor+'.inference'))
                    self.assertEqual(provider.probe()['availability'],'available')
                    artifact = provider.prepare(self.bundle); provider.load(artifact)
                    self.assertEqual(provider.encode_many(['a','b']),[[1.,0.],[1.,0.]])
                    receipt = provider.telemetry()
                    self.assertIn('startup_ms',receipt); self.assertIn('cpu_seconds',receipt)
                    self.assertIsNone(receipt['observed_kernel_dispatch'])
                    self.assertTrue(sentence.SentenceTransformer.call_args.kwargs['local_files_only'])
                    self.assertFalse(sentence.SentenceTransformer.call_args.kwargs['trust_remote_code'])
                    provider.close(); self.assertIsNone(provider.model)

    def test_every_framework_family_resident_topk_and_failed_allocation_cleanup(self):
        for vendor in ('nvidia','amd','intel','apple','ascend','musa','cambricon','metax'):
            with self.subTest(vendor=vendor):
                torch = torch_fixture(vendor)
                with mock.patch.dict(sys.modules,{'torch':torch,'torch_npu':types.SimpleNamespace(),'torch_mlu':types.SimpleNamespace(),'torch_musa':types.SimpleNamespace()}):
                    provider = ExactAccelerator(spec(vendor+'.exact'))
                    device = dict(provider.spec.options)['device']
                    self.assertEqual(provider.probe()['availability'],'available')
                    k = index_identity(provider=provider.spec.provider_id,device=device)
                    handle = provider.build([[1.,0.],[0.,1.],[1.,0.]],[10,20,30],k)
                    for _ in range(2):
                        rows, receipt = provider.search(handle,[[1.,0.]],2)
                        self.assertEqual(rows[0][0],[10,30])
                        self.assertFalse(receipt['document_matrix_transferred'])
                    self.assertEqual(torch.tensor.call_count,1)
                    torch.tensor.side_effect = MemoryError('fixture OOM')
                    with self.assertRaises(MemoryError):
                        provider.build([[1.,0.]],[10],replace(k,generation='g2'))
                    self.assertEqual(len(provider.handles),1)
                    provider.close(); self.assertEqual(provider.memory_usage(),0)

    def ort(self, ep, plugin=False):
        options = mock.Mock(); session = mock.Mock()
        session.get_providers.return_value = [ep]; session.run.return_value = [np.array([[1.,0.]])]
        ort = types.SimpleNamespace(__version__='fixture', SessionOptions=mock.Mock(return_value=options),
            InferenceSession=mock.Mock(return_value=session),get_available_providers=lambda: [] if plugin else [ep],
            get_ep_devices=lambda: [types.SimpleNamespace(ep_name=ep)],
            register_execution_provider_library=mock.Mock(),unregister_execution_provider_library=mock.Mock())
        return ort, options

    def test_ort_vendor_families_and_cpu_fallback_disabled(self):
        for name in ('nvidia.tensorrt-rtx','amd.migraphx-ep','qualcomm.qnn','windows.directml'):
            with self.subTest(provider=name):
                ep = dict(spec(name).options)['ep']; ort, options = self.ort(ep)
                with mock.patch.dict(sys.modules,{'onnxruntime':ort}):
                    p = OrtInference(spec(name)); self.assertEqual(p.probe()['availability'],'available')
                    a = p.prepare(self.model); p.load(a)
                    self.assertEqual(p.encode_many({'input_ids':[[1]]})[0].tolist(),[[1.,0.]])
                    options.add_session_config_entry.assert_called_with('session.disable_cpu_ep_fallback','1')
                    self.assertEqual(p.telemetry()['requested_ep'],ep)
                    self.assertIsNone(p.telemetry()['observed_operator_placement'])
                    p.close()

    def test_plugin_ep_uses_device_api_and_unregisters_after_session(self):
        name = 'nvidia.tensorrt-rtx'; ep = dict(spec(name).options)['ep']
        library = self.root/'plugin.dll'; library.write_bytes(b'fixture local EP')
        ort, options = self.ort(ep,plugin=True)
        with mock.patch.dict(sys.modules,{'onnxruntime':ort}):
            p = OrtInference(spec(name)); a = p.prepare(self.model); p.load(a,ep_library=library)
            options.add_provider_for_devices.assert_called_once()
            self.assertNotIn('providers',ort.InferenceSession.call_args.kwargs)
            p.close(); ort.unregister_execution_provider_library.assert_called_once()

    def test_ort_unavailable_does_not_fall_back_silently(self):
        ort, _ = self.ort('CPUExecutionProvider')
        with mock.patch.dict(sys.modules,{'onnxruntime':ort}):
            p = OrtInference(spec('qualcomm.qnn')); artifact = p.prepare(self.model)
            with self.assertRaises(ProviderUnavailable):p.load(artifact)
            ort.InferenceSession.assert_not_called()

    def test_openvino_all_native_device_policies(self):
        compiled = mock.Mock(return_value={'output':[[1.,0.]]}); compiled.get_property.return_value=['CPU']
        core = mock.Mock(); core.available_devices=['CPU','GPU','NPU']; core.compile_model.return_value=compiled
        with mock.patch.dict(sys.modules,{'openvino':types.SimpleNamespace(__version__='fixture',Core=lambda:core)}):
            for device in ('CPU','GPU','NPU','AUTO','MULTI:GPU,CPU','BATCH:GPU'):
                p = OpenVINOInference(spec('intel.openvino')); a=p.prepare(self.model)
                self.assertEqual(p.probe()['devices'],['CPU','GPU','NPU'])
                p.compile(a,device=device); p.encode_many({'x':[[1]]})
                self.assertEqual(p.telemetry()['allowed_devices'],device)
                self.assertEqual(p.telemetry()['runtime_execution_devices'],['CPU'])
                p.close()

    def test_coreml_allowed_units_are_not_observed_ane(self):
        model = mock.Mock(); model.predict.return_value={'output':[[1.,0.]]}
        ct = types.SimpleNamespace(__version__='fixture',models=types.SimpleNamespace(MLModel=mock.Mock(return_value=model)),
                                   ComputeUnit=types.SimpleNamespace(**{x:x for x in ('CPU_ONLY','CPU_AND_GPU','CPU_AND_NE','ALL')}))
        with mock.patch.dict(sys.modules,{'coremltools':ct}):
            for unit in ('CPU_ONLY','CPU_AND_GPU','CPU_AND_NE','ALL'):
                p=CoreMLInference(spec('apple.coreml')); a=p.prepare(self.model); p.load(a,compute_units=unit)
                p.encode_many({'x':1}); self.assertEqual(p.telemetry()['allowed_compute_units'],unit)
                self.assertIsNone(p.telemetry()['observed_ane_kernel']); p.close()

    def test_migraphx_native_compile_and_execution(self):
        model=mock.Mock(); model.run.return_value=[[1.,0.]]
        mgx=types.SimpleNamespace(__version__='fixture',parse_onnx=mock.Mock(return_value=model),get_target=lambda x:x,argument=lambda x:x)
        with mock.patch.dict(sys.modules,{'migraphx':mgx}):
            p=MIGraphXInference(spec('amd.migraphx')); a=p.prepare(self.model); p.compile(a)
            self.assertEqual(p.encode_many({'x':[[1.,0.]]}),[[1.,0.]])
            model.compile.assert_called_with('gpu',offload_copy=True,fast_math=False,exhaustive_tune=False)
            self.assertIn('compile_ms',p.telemetry()); p.close()

    def test_external_model_tensor_change_invalidates_artifact(self):
        ort,_=self.ort('QNNExecutionProvider')
        external=self.bundle/'arbitrary-weight-name'; external.write_bytes(b'weights')
        with mock.patch.dict(sys.modules,{'onnxruntime':ort}):
            p=OrtInference(spec('qualcomm.qnn')); artifact=p.prepare(self.model)
            external.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'identity changed'):p.load(artifact)
            ort.InferenceSession.assert_not_called()

    def test_windows_catalog_only_ready_never_provisions(self):
        ep='QNNExecutionProvider'; library=self.root/'qnn.dll'; library.write_bytes(b'local QNN')
        rows=[types.SimpleNamespace(name=ep,library_path=str(library),ready_state='READY'),
              types.SimpleNamespace(name='pending',library_path='missing',ready_state='NOT_PRESENT')]
        catalog=mock.Mock(); catalog.find_all_providers.return_value=rows
        winml=types.SimpleNamespace(ExecutionProviderReadyState=types.SimpleNamespace(READY='READY'))
        ort,_=self.ort(ep,plugin=True)
        with mock.patch.dict(sys.modules,{'onnxruntime':ort}):
            p=WindowsMLCatalog(spec('windows.catalog'))
            with mock.patch.object(p,'_catalog',return_value=(catalog,winml)):
                self.assertEqual(len(p.discover()),1)
                a=p.prepare(self.model); p.load(a,ep=ep); p.encode_many({'x':[[1]]})
                with self.assertRaises(ProviderUnavailable):p.load(a,ep='pending')
                catalog.ensure_ready_async.assert_not_called()
                p.close()


class OnlineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.index=SearchIndex(Path(self.temp.name)/'index.db',TokenCounter())
        self.addCleanup(self.index.close); self.index.replace_scope('scope',documents())
        self.encoder=FakeEncoder(); self.index.embed('scope',self.encoder,self.encoder.model_id)

    def test_online_burst_reaches_real_batch_and_matches_singleton(self):
        service=RuntimeService(self.index,encoder=self.encoder,model_id=self.encoder.model_id,background=False)
        try:
            settings={'mode':'hybrid','diagnostics':True}
            warm=service.search('scope','Beijing',**settings)
            batcher=next(iter(service.batchers.values()))
            with batcher.condition:
                futures=[service.submit('scope','Beijing '+str(i),**settings) for i in range(8)]
            results=[f.result(3) for f in futures]
            self.assertTrue(any(r['runtime_receipt']['actual_batch']>1 for r in results))
            for i,result in enumerate(results):
                reference=self.index.search('scope','Beijing '+str(i),encoder=self.encoder,model_id=self.encoder.model_id,**settings)
                self.assertEqual(result['ranked_ids'],reference['ranked_ids'])
                self.assertEqual(result['context'],reference['context'])
                self.assertEqual(result['runtime_receipt']['query_embedding_batch'],1)
                self.assertIn('queue_wait_ms',result['runtime_receipt'])
            self.assertEqual(service.telemetry.summary('reference','interactive')['sample_count'],9)
        finally:service.close()

    def test_resident_executor_is_used_by_search_many(self):
        executor=ResidentExecutor(builtin_registry(extensions=False)); self.index._vector_executor=executor
        try:
            rows=self.index.search_many('scope',['Beijing','Alice'],mode='hybrid',encoder=self.encoder,
                model_id=self.encoder.model_id,semantic_guard=True,diagnostics=True)
            self.assertEqual(rows[0]['batch_receipt']['batch_semantic_status'],'strict')
            self.assertIn('resident_receipt',rows[0]['batch_receipt'])
            self.assertEqual(len(executor.manager.handles),1)
        finally:self.index._vector_executor=None; executor.close()

    def test_store_ttl_and_bounded_history(self):
        clock=[100.]; store=ProfileStore(':memory:',clock=lambda:clock[0],max_observations=2,max_age_seconds=10)
        try:
            for candidate in ('a','b','c'):
                store.put(key(),candidate,{'p95':1},semantic_status='strict',material_gain='accepted')
            self.assertEqual(len(store.observations(key())),2)
            clock[0]=111.; self.assertEqual(store.observations(key()),[])
        finally:store.close()

    def test_fast_cli_does_not_probe_native_or_mutate_store(self):
        from thm.runtime.cli import main
        with mock.patch('thm.runtime.fabric.registry.ProviderRegistry.probe',side_effect=AssertionError('native')), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(['status']),0)
        self.assertFalse(json.loads(out.getvalue())['user_benchmark_required'])


class NativeVectorFixtureTests(unittest.TestCase):
    def cupy(self):
        return types.SimpleNamespace(float32=np.float32,asarray=np.asarray,asnumpy=np.asarray,
            cuda=types.SimpleNamespace(runtime=types.SimpleNamespace(getDeviceCount=lambda:1),
                get_current_stream=lambda:types.SimpleNamespace(synchronize=lambda:None)))

    def nearest(self, *args):
        data, queries, k = args[-3:]
        scores=queries@data.T; indices=np.argsort(-scores,axis=1,kind='stable')[:,:k]
        return np.take_along_axis(scores,indices,axis=1),indices

    def test_cuvs_exact_ann_tiered_and_vamana_export_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            for algorithm in ('brute_force','cagra','ivf_flat','ivf_pq','ivf_sq','tiered_index','vamana'):
                with self.subTest(algorithm=algorithm):
                    api=types.SimpleNamespace(build=mock.Mock(side_effect=lambda *a,**k:a[-1]),
                        IndexParams=lambda **kw:kw,SearchParams=lambda **kw:kw,search=mock.Mock(side_effect=self.nearest),
                        save=mock.Mock(),AceParams=lambda **kw:kw)
                    with mock.patch.dict(sys.modules,{'cupy':self.cupy(),'cuvs.neighbors.'+algorithm:api,'cuvs.neighbors.cagra':api}):
                        p=CuvsProvider(spec('nvidia.cuvs.'+algorithm)); k=index_identity(provider=p.spec.provider_id,device='cuda')
                        self.assertEqual(p.probe()['availability'],'available')
                        h=p.build([[1.,0.],[0.,1.]],[7,8],k)
                        if algorithm=='vamana':
                            self.assertTrue(p.export_vamana(h,Path(temp)/'index.bin')['exported'])
                            with self.assertRaises(ProviderUnavailable):p.search(h,[[1.,0.]],1)
                        else:
                            rows,receipt=p.search(h,[[1.,0.]],1)
                            self.assertEqual(rows[0][0],[7]); self.assertFalse(receipt['document_matrix_transferred'])
                        p.close(); self.assertEqual(p.memory_usage(),0)

    def test_cagra_ace_keeps_build_dataset_on_host_with_memory_limits(self):
        api=types.SimpleNamespace(build=mock.Mock(side_effect=lambda *a,**k:a[-1]),IndexParams=lambda **kw:kw,AceParams=lambda **kw:kw)
        cp=self.cupy(); cp.asarray=mock.Mock(side_effect=AssertionError('ACE input must remain on host'))
        with mock.patch.dict(sys.modules,{'cupy':cp,'cuvs.neighbors.cagra':api}):
            p=CuvsProvider(spec('nvidia.cuvs.cagra'))
            h=p.build([[1.,0.]],[0],index_identity(),index_params={'build_algo':'ace'},resident_budget_bytes=1024**2)
            params=api.build.call_args.args[0]
            self.assertFalse(params['ace_params']['use_disk'])
            self.assertGreater(params['ace_params']['max_gpu_memory_gb'],0)
            self.assertTrue(h.data['host_build']); p.close()

    def test_mcfaiss_provenance_and_actual_index_api(self):
        graph=mock.Mock(); graph.search.return_value=(np.array([[1.]],dtype=np.float32),np.array([[0]],dtype=np.int64))
        faiss=types.SimpleNamespace(get_num_gpus=lambda:1,StandardGpuResources=lambda:object(),
            GpuIndexFlatConfig=lambda:types.SimpleNamespace(),GpuIndexFlatIP=mock.Mock(return_value=graph))
        with mock.patch.dict(sys.modules,{'faiss':faiss}),mock.patch('ctypes.util.find_library',return_value='fixture-mxmacalib'):
            p=McFaissProvider(spec('metax.mcfaiss')); self.assertEqual(p.probe()['availability'],'available')
            h=p.build([[1.,0.]],[19],index_identity(device='maca'))
            self.assertEqual(p.search(h,[[1.,0.]],1)[0][0][0],[19]); graph.add.assert_called_once(); p.close()
        with mock.patch.dict(sys.modules,{'faiss':faiss}),mock.patch('ctypes.util.find_library',return_value=None):
            with self.assertRaises(ProviderUnavailable):McFaissProvider(spec('metax.mcfaiss')).probe()

    def test_hnsw_build_and_search_is_explicitly_approximate(self):
        graph=mock.Mock(); graph.knn_query.return_value=(np.array([[0]]),np.array([[0.]]))
        with mock.patch.dict(sys.modules,{'hnswlib':types.SimpleNamespace(Index=mock.Mock(return_value=graph))}):
            p=HNSWGeneric(spec('host.hnsw')); self.assertEqual(p.probe()['semantic_class'],'approximate')
            h=p.build([[1.,0.]],[17],index_identity()); result,receipt=p.search(h,[[1.,0.]],1)
            self.assertEqual(result[0][0],[17]); self.assertEqual(receipt['semantic_class'],'approximate')
            graph.set_num_threads.assert_called_with(1); p.close()


class RTXFixtureTests(unittest.TestCase):
    def test_native_aot_jit_cache_identity_and_tensor_execution(self):
        from thm.runtime.fabric.rtx import TensorRTRTXInference
        class Buffer:
            registry={}
            def __init__(self,value):
                self.array=np.asarray(value); self.shape=self.array.shape; self.nbytes=self.array.nbytes
                self.data=types.SimpleNamespace(ptr=id(self)); self.registry[id(self)]=self
        class Stream:
            ptr=77
            def __init__(self,**kw):pass
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def synchronize(self):pass
        class Context:
            def __init__(self):self.pointers={}
            def set_input_shape(self,name,shape):self.shape=shape;return True
            def get_tensor_shape(self,name):return self.shape
            def set_tensor_address(self,name,address):self.pointers[name]=address;return True
            def execute_async_v3(self,stream):
                Buffer.registry[self.pointers['y']].array[:]=Buffer.registry[self.pointers['x']].array
                return True
        context=Context()
        engine=types.SimpleNamespace(num_io_tensors=2,get_tensor_name=lambda i:['x','y'][i],get_tensor_mode=lambda n:'INPUT' if n=='x' else 'OUTPUT',
            get_tensor_dtype=lambda n:'float32',create_execution_context=lambda:context)
        builder=mock.Mock(); builder.build_serialized_network.return_value=b'compiled fixture'; parser=mock.Mock(); parser.parse_from_file.return_value=True
        logger=mock.Mock();logger.ERROR=1
        trt=types.SimpleNamespace(__version__='fixture',Logger=logger,Builder=mock.Mock(return_value=builder),OnnxParser=mock.Mock(return_value=parser),
            MemoryPoolType=types.SimpleNamespace(WORKSPACE=0),Runtime=lambda log:types.SimpleNamespace(deserialize_cuda_engine=lambda data:engine),
            TensorIOMode=types.SimpleNamespace(INPUT='INPUT'),nptype=lambda dtype:np.float32)
        version=[100]
        cp=types.SimpleNamespace(ascontiguousarray=lambda x,**kw:Buffer(np.asarray(x,**kw)),empty=lambda shape,**kw:Buffer(np.empty(shape,**kw)),asnumpy=lambda x:x.array.copy(),
            cuda=types.SimpleNamespace(Stream=Stream,runtime=types.SimpleNamespace(getDeviceCount=lambda:1,getDevice=lambda:0,
                getDeviceProperties=lambda i:{'major':9,'minor':0,'totalGlobalMem':2**30},driverGetVersion=lambda:version[0],runtimeGetVersion=lambda:100)))
        with tempfile.TemporaryDirectory() as temp,mock.patch.dict(sys.modules,{'tensorrt_rtx':trt,'cupy':cp}):
            root=Path(temp);bundle=root/'bundle';bundle.mkdir();model=bundle/'model.onnx';model.write_bytes(b'fixture')
            p=TensorRTRTXInference(spec('nvidia.rtx-native'));a=p.prepare(model)
            self.assertEqual(p.probe()['availability'],'available')
            p.compile(a,cache_root=root/'cache'); p.load(a,cache_root=root/'cache')
            self.assertEqual(builder.build_serialized_network.call_count,1)
            output=p.encode_many({'x':[[1.,2.]]});self.assertEqual(output['y'].tolist(),[[1.,2.]])
            self.assertTrue(p.telemetry()['compiled_cache_hit']);self.assertIn('jit_startup_ms',p.telemetry())
            version[0]=101; p.compile(a,cache_root=root/'cache');self.assertEqual(builder.build_serialized_network.call_count,2)
            p.close();self.assertIsNone(p.model)


class ExactTokenPrefixTests(unittest.TestCase):
    def test_real_bpe_prefix_reuse_matches_full_tokenization(self):
        try:import tiktoken
        except ImportError:self.skipTest('optional tokenizer installed by correctness CI')
        # In-memory vocabulary: no network or downloaded tokenizer data.
        ranks={bytes([i]):i for i in range(256)}
        ranks.update({b'ab':256,b'abc':257,b'  ':258,b'\xe4\xb8\xad':259})
        encoding=tiktoken.Encoding(name='thm-fixture',pat_str=r'\s+|[^\s]+',mergeable_ranks=ranks,special_tokens={})
        counter=TokenCounter();counter.encode=encoding.encode_ordinary
        corpus=['abc abc','a b c','abc\n\nabc','中文 abc 🔎','  a  b  ','ab'*2000,'line\nnext']
        for text in corpus:
            for length in range(1,len(text)+1,max(1,len(text)//23)):
                self.assertEqual(counter.count_prefix(text[:length]),counter(text[:length]))
        self.assertLessEqual(len(counter._piece_cache),512)
