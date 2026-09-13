"""Owned page-aligned staging buffers, explicit pinning and transfer evidence."""
import ctypes as c
import mmap
import os
from .contracts import PermissionGate, integer


class OwnedBuffer:
    def __init__(self,size):
        integer(size,minimum=1,maximum=256*1024**2)
        self.size=size
        self.mapping=mmap.mmap(-1,size)
        self.view=(c.c_ubyte*size).from_buffer(self.mapping)
        self.address=c.addressof(self.view)
        self.pinned=False
        self.registration=None
        self.closed=False
        self.unpin=None

    def pin(self,gate=PermissionGate()):
        gate.require('S1')
        if self.closed or self.pinned:
            raise ValueError('closed/already pinned')
        if os.name=='nt':
            library=c.WinDLL('kernel32',use_last_error=True)
            library.VirtualLock.argtypes=[c.c_void_p,c.c_size_t]
            library.VirtualUnlock.argtypes=[c.c_void_p,c.c_size_t]
            if not library.VirtualLock(self.address,self.size):
                raise c.WinError(c.get_last_error())
            self.unpin=lambda:library.VirtualUnlock(self.address,self.size)
        else:
            library=c.CDLL(None,use_errno=True)
            library.mlock.argtypes=[c.c_void_p,c.c_size_t]
            library.munlock.argtypes=[c.c_void_p,c.c_size_t]
            if library.mlock(self.address,self.size):
                raise OSError(c.get_errno(),'mlock unavailable')
            self.unpin=lambda:library.munlock(self.address,self.size)
        self.pinned=True
        return self.receipt()

    def register(self,binding):
        if self.closed or self.registration is not None:
            raise ValueError('closed/already registered')
        token=binding.register(self.address,self.size)
        self.registration=(binding,token)
        return self.receipt()

    def receipt(self):
        return {'bytes':self.size,'owned':True,'pinned':self.pinned,'registered':self.registration is not None,
                'copy_path':'owned-host-staging','zero_copy':False,'device_transfer_observed':False}

    def close(self):
        if self.closed:return
        if self.registration is not None:
            binding,token=self.registration
            binding.unregister(token)
            self.registration=None
        if self.pinned:
            self.unpin();self.pinned=False
        self.view=None
        self.mapping.close()
        self.closed=True
