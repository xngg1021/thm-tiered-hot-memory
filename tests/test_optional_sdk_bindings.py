"""Public SDK call shapes, resource ownership and fail-closed operating points."""
import hashlib
import io
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock
import numpy as np
from thm.runtime.fabric.extensions import ExtensionConfig, ExtensionSession, FunctionBinding
from thm.runtime.fabric.sdk_extensions import DiskANNBinding, TTNNBinding, NeuronBinding, OpenCLBinding
from thm.runtime.fabric.optimizer import PolicySelector
from thm.physical.backends import S3Transport, BackendConfig, StorageBackend
from thm.physical.contracts import TransferExtent


def config(provider, source, **kw):
    return ExtensionConfig(provider, 'g', hashlib.sha256(source).hexdigest(), 'sdk', 'fixture', 'device', evidence='fixture-validated', **kw)


class SDKTests(unittest.TestCase):
    def test_diskann_build_load_search_and_owned_cleanup(self):
        matrix=np.array([[1,2],[3,4]],dtype=np.float32); calls=[]
        class Index:
            def __init__(self, **kw):calls.append(kw)
            def search(self, **kw):
                self.kw=kw
                return types.SimpleNamespace(identifiers=np.array([0]),distances=np.array([0.]))
        api=types.SimpleNamespace(build_memory_index=lambda **kw:calls.append(kw),StaticMemoryIndex=Index)
        with mock.patch.dict('sys.modules', {'diskannpy':api}):
            binding=DiskANNBinding(); s=ExtensionSession(config('diskann',matrix.tobytes()),binding)
            s.prepare(matrix);s.compile();root=Path(binding.directory.name);s.load()
            out=s.execute('search',{'query':matrix[0],'k':1},generation='g')
            self.assertEqual(out['identifiers'].tolist(),[0]);self.assertEqual(calls[0]['distance_metric'],'l2')
            s.close();self.assertFalse(root.exists())

    def test_ttnn_bf16_is_explicit_and_resources_close(self):
        closed=[]; deallocated=[]
        class Tensor:
            def __init__(self,x):self.x=np.asarray(x,dtype=np.float32)
            def reshape(self,*shape):return Tensor(self.x.reshape(*shape))
            def float(self):return self
            def numpy(self):return self.x
        torch=types.SimpleNamespace(bfloat16='bf16',as_tensor=lambda x,**kw:Tensor(x))
        api=types.SimpleNamespace(bfloat16='bf16',TILE_LAYOUT='tile',open_device=lambda **kw:'d',close_device=lambda d:closed.append(d),
            from_torch=lambda t,**kw:t,to_torch=lambda t:t,matmul=lambda a,b:Tensor(a.x@b.x),deallocate=lambda t:deallocated.append(t))
        matrix=np.array([[1,2],[3,4]],dtype=np.float32)
        with mock.patch.dict('sys.modules',{'torch':torch,'ttnn':api}):
            b=TTNNBinding()
            with self.assertRaises(ValueError):b.prepare(matrix,config('tenstorrent.ttnn',matrix.tobytes()))
            s=ExtensionSession(config('tenstorrent.ttnn',matrix.tobytes(),precision='bf16'),b)
            s.prepare(matrix);s.compile();s.load();np.testing.assert_equal(s.execute('score',matrix[0],generation='g'),[5,11]);s.close()
            self.assertEqual(closed,['d']);self.assertEqual(len(deallocated),3)

    def test_neuron_precompiled_model_execution(self):
        from contextlib import nullcontext
        class Tensor:
            def detach(self):return self
            def cpu(self):return self
            def numpy(self):return np.array([3],dtype=np.float32)
        class Model:
            def eval(self):return self
            def __call__(self,*x):return Tensor()
        api=types.SimpleNamespace(jit=types.SimpleNamespace(load=lambda p:Model()),as_tensor=lambda x:x,inference_mode=nullcontext)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict('sys.modules',{'torch':api,'torch_neuronx':types.SimpleNamespace()}):
            path=Path(tmp)/'model.pt';path.write_bytes(b'artifact')
            from thm.runtime.fabric.inference import artifact_digest
            cfg=config('aws.neuron',b'ignored')
            from dataclasses import replace
            s=ExtensionSession(replace(cfg,source_sha256=artifact_digest(path)),NeuronBinding())
            s.prepare(path);s.compile();s.load();np.testing.assert_equal(s.execute('inference',[np.array([1])],generation='g'),[3]);s.close()

    def test_opencl_real_kernel_call_shape_and_cleanup(self):
        released=[]
        class Buffer:
            def __init__(self,c,f,size=None,hostbuf=None):self.x=np.array(hostbuf) if hostbuf is not None else np.empty(size//4,dtype=np.float32)
            def release(self):released.append(self)
        class Program:
            def __init__(self,c,source):self.source=source
            def build(self,**kw):return self
            def scores(self,q,shape,local,matrix,query,out,dim):out.x=matrix.x@query.x
        api=types.SimpleNamespace(get_platforms=lambda:[types.SimpleNamespace(get_devices=lambda:['d'])],Context=lambda d:'ctx',
            CommandQueue=lambda c:types.SimpleNamespace(finish=lambda:None),Buffer=Buffer,Program=Program,
            mem_flags=types.SimpleNamespace(READ_ONLY=1,COPY_HOST_PTR=2,WRITE_ONLY=4))
        def copy(queue,out,buffer):
            out[:]=buffer.x
            return types.SimpleNamespace(wait=lambda:None)
        api.enqueue_copy=copy;matrix=np.array([[1,2],[3,4]],dtype=np.float32)
        with mock.patch.dict('sys.modules',{'pyopencl':api}):
            s=ExtensionSession(config('portable.opencl',matrix.tobytes()),OpenCLBinding())
            s.prepare(matrix);s.compile();s.load();np.testing.assert_equal(s.execute('score',matrix[0],generation='g'),[5,11]);s.close();s.close()
            self.assertEqual(len(released),3)

    def test_s3_conditional_publish_range_and_caller_ownership(self):
        objects={};closed=[]
        def put(**kw):
            self.assertEqual(kw['IfNoneMatch'],'*');objects[kw['Key']]=kw['Body']
        def get(**kw):
            a,b=map(int,kw['Range'][6:].split('-'));return {'Body':io.BytesIO(objects[kw['Key']][a:b+1])}
        client=types.SimpleNamespace(put_object=put,get_object=get,head_object=lambda **kw:dict(ContentLength=len(objects[kw['Key']])),close=lambda:closed.append(True))
        b=StorageBackend(BackendConfig('s3','s3','g'),S3Transport(client,'fixture'))
        key=b.write(b'abcdef',generation='g');self.assertEqual(b.read(TransferExtent(key,2,2),generation='g'),b'cd');b.close();self.assertEqual(closed,[])

    def test_unknown_cold_cost_is_never_free(self):
        p=PolicySelector()
        self.assertIsNone(p.predict({'p95':1},{'model_warm':False}))
        self.assertIsNone(p.predict({'p95':1},{'provider_ready':False}))
        self.assertEqual(p.predict({'p95':1},{}),1)

    def test_invalidation_closes_even_if_vendor_cleanup_fails(self):
        def fail():raise OSError('cleanup')
        b=FunctionBinding(operations=('transfer',),prepare=lambda x,c:x,compile=lambda x,c:x,load=lambda x,c:x,execute=lambda h,o,x:x,close=fail)
        s=ExtensionSession(config('extension',b'a'),b)
        with self.assertRaises(OSError):s.invalidate()
        self.assertEqual(s.state,'invalidated')


if __name__ == '__main__':unittest.main()
