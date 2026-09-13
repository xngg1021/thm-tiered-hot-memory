"""Optional Apple public vector/graph execution and explicit admission evidence."""
import ctypes as c
import ctypes.util
import platform
import time
from .contracts import finite


class AccelerateVector:
    def __init__(self, library=None):
        if library is None:
            if platform.system()!='Darwin':
                raise OSError('Accelerate is unavailable on this platform')
            library=c.CDLL('/System/Library/Frameworks/Accelerate.framework/Accelerate')
        self.library=library
        self.last={}
        self.closed=False
        self.library.cblas_sgemm.argtypes=[c.c_int,c.c_int,c.c_int,c.c_int,c.c_int,c.c_int,c.c_float,
            c.POINTER(c.c_float),c.c_int,c.POINTER(c.c_float),c.c_int,c.c_float,c.POINTER(c.c_float),c.c_int]
        self.library.cblas_sgemm.restype=None

    def matmul(self,left,right):
        import numpy as np
        if self.closed:
            raise ValueError('closed vector provider')
        a=np.ascontiguousarray(left,dtype=np.float32); b=np.ascontiguousarray(right,dtype=np.float32)
        if a.ndim!=2 or b.ndim!=2 or a.shape[1]!=b.shape[0] or not np.isfinite(a).all() or not np.isfinite(b).all():
            raise ValueError('invalid matrix shapes/values')
        m,k=a.shape; n=b.shape[1]
        if not min(m,k,n) or max(m,k,n)>4096 or m*k+k*n+m*n>4_000_000:
            raise ValueError('matrix bound')
        out=np.empty((m,n),dtype=np.float32); start=time.perf_counter()
        ptr=c.POINTER(c.c_float)
        self.library.cblas_sgemm(101,111,111,m,n,k,1.,a.ctypes.data_as(ptr),k,b.ctypes.data_as(ptr),n,0.,out.ctypes.data_as(ptr),n)
        reference=a@b
        error=float(np.max(np.abs(out-reference)))
        self.last={'native_path':'Accelerate-CBLAS','operation':'matmul','wall_seconds':time.perf_counter()-start,
            'max_absolute_error':error,'parity_accepted':bool(np.allclose(out,reference,rtol=1e-5,atol=1e-5)),
            'NEON_observed':None,'AMX_observed':None,'hardware_acceptance':False,'zero_copy':False}
        if not self.last['parity_accepted']:
            raise ValueError('Accelerate/reference parity failed')
        return out

    def close(self):
        self.closed=True


class MPSGraphBinding:
    """Public PyObjC graph binding; no generated kernels or model downloads."""
    def __init__(self, api=None):
        self.fixture=api is not None
        if api is None:
            import MetalPerformanceShadersGraph as api
        self.api=api
        self.graph=None
        self.last={}

    def matmul(self,left,right):
        import numpy as np
        from Foundation import NSData
        a=np.ascontiguousarray(left,dtype=np.float32); b=np.ascontiguousarray(right,dtype=np.float32)
        if a.ndim!=2 or b.ndim!=2 or a.shape[1]!=b.shape[0] or a.size+b.size>1_000_000:
            raise ValueError('bounded compatible matrices required')
        if not np.isfinite(a).all() or not np.isfinite(b).all():
            raise ValueError('finite matrix values required')
        graph=self.api.MPSGraph.alloc().init()
        dtype=getattr(self.api,'MPSDataTypeFloat32',0x10000000|32)
        ta=graph.constantWithData_shape_dataType_(NSData.dataWithBytes_length_(a.tobytes(),a.nbytes),list(a.shape),dtype)
        tb=graph.constantWithData_shape_dataType_(NSData.dataWithBytes_length_(b.tobytes(),b.nbytes),list(b.shape),dtype)
        tc=graph.matrixMultiplicationWithPrimaryTensor_secondaryTensor_name_(ta,tb,None)
        start=time.perf_counter()
        result=graph.runWithFeeds_targetTensors_targetOperations_({},[tc],None)[tc]
        out=np.empty((a.shape[0],b.shape[1]),dtype=np.float32)
        # PyObjC exposes the public raw-byte output buffer; no pointer is retained.
        result.mpsndarray().readBytes_strideBytes_(out,None)
        self.graph=graph
        self.last={'native_path':'MPSGraph','operation':'matmul','wall_seconds':time.perf_counter()-start,
            'evidence':'callable-fixture' if self.fixture else 'native-executed',
            'max_absolute_error':float(np.max(np.abs(out-a@b))), 'hardware_acceptance':False,
            'ANE_operator_observed':None,'zero_copy':False}
        if not np.allclose(out,a@b,rtol=1e-5,atol=1e-5):
            raise ValueError('MPSGraph/reference parity failed')
        return out

    def close(self):
        self.graph=None


def apple_auto_admission(*, mps_available, semantic_parity, sustained_gain, memory_accepted, fresh, new_session):
    flags=(mps_available,semantic_parity,sustained_gain,memory_accepted,fresh,new_session)
    if any(type(x) is not bool for x in flags):
        raise ValueError('explicit admission gates required')
    return {'mode':'auto-safe','eligible':all(flags),'adoption':'new-session-boundary',
            'hardware_generation_assumed':False,'source_memory_mutation':False}


def coreml_placement_receipt(compute_units, observed_operators=None):
    if compute_units not in ('CPU_ONLY','CPU_AND_GPU','CPU_AND_NE','ALL'):
        raise ValueError('invalid CoreML compute units')
    return {'compute_units_requested':compute_units,'observed_operators':observed_operators,
            'ANE_placement':'placement_unobservable' if observed_operators is None else 'external-observation-required',
            'ANE_accepted':False}
