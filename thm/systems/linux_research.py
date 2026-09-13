"""Explicit Linux userfaultfd and libbpf lifecycles; never enabled by discovery."""
import ctypes as c
import ctypes.util
import hashlib
import mmap
import os
import platform
import select
import struct
from .contracts import PermissionGate, finite, integer, nonempty


class UserfaultfdBinding:
    """Owned missing-page regions with bounded poll/copy and explicit caller ownership."""
    evidence='native-executed'

    def __init__(self,*,experimental=False,gate=PermissionGate()):
        if experimental is not True:raise PermissionError('userfaultfd research defaults off')
        gate.require('S1')
        if platform.system()!='Linux':raise OSError('userfaultfd requires Linux')
        number={'x86_64':323,'aarch64':282}.get(platform.machine())
        if number is None:raise OSError('unverified userfaultfd syscall ABI')
        self.lib=c.CDLL(None,use_errno=True);self.lib.syscall.restype=c.c_long
        self.fd=self.lib.syscall(c.c_long(number),c.c_long(os.O_CLOEXEC|os.O_NONBLOCK|1))
        if self.fd<0:raise OSError(c.get_errno(),'userfaultfd unavailable')
        self.regions={};self.closed=False
        try:
            response=self._ioctl(0xC018AA3F,struct.pack('=QQQ',0xAA,0,0))
            api,features,ioctls=struct.unpack('=QQQ',response)
            if api!=0xAA or not ioctls&1:raise OSError('userfaultfd API negotiation failed')
        except BaseException:self.close();raise

    def _ioctl(self,command,payload):
        import fcntl
        buffer=bytearray(payload);fcntl.ioctl(self.fd,command,buffer,True);return buffer

    def register(self,identity,size):
        nonempty(identity);integer(size,minimum=1,maximum=1048576)
        if self.closed or identity in self.regions or len(self.regions)>=16:raise ValueError('closed/duplicate/full regions')
        length=(size+mmap.PAGESIZE-1)//mmap.PAGESIZE*mmap.PAGESIZE
        memory=mmap.mmap(-1,length,flags=mmap.MAP_PRIVATE|mmap.MAP_ANONYMOUS)
        view=(c.c_ubyte*length).from_buffer(memory);address=c.addressof(view)
        try:
            result=self._ioctl(0xC020AA00,struct.pack('=QQQQ',address,length,1,0))
            if not struct.unpack('=QQQQ',result)[3]&(1<<3):raise OSError('UFFDIO_COPY unavailable')
        except BaseException:
            view=None;memory.close();raise
        self.regions[identity]=(memory,view,address,length,size)
        return {'identity':identity,'bytes':size,'registered_bytes':length,'evidence':self.evidence}

    def poll(self,timeout=.1,capacity=16):
        finite(timeout);integer(capacity,minimum=1,maximum=1024)
        if self.closed or timeout>5:raise ValueError('closed/unbounded userfaultfd poll')
        if not select.select([self.fd],[],[],timeout)[0]:return []
        raw=os.read(self.fd,32*capacity)
        if len(raw)%32:raise ValueError('truncated userfaultfd event')
        rows=[]
        for offset in range(0,len(raw),32):
            event=raw[offset:offset+32]
            if event[0]!=0x12:raise ValueError('unexpected userfaultfd event')
            address=struct.unpack_from('=Q',event,16)[0]
            for identity,(_,_,start,length,size) in self.regions.items():
                if start<=address<start+length:
                    rows.append({'kind':'page-fault','identity':identity,'offset':address-start});break
            else:raise ValueError('fault outside owned regions')
        return rows

    def copy(self,identity,offset,data):
        memory,view,address,length,size=self.regions[identity]
        integer(offset,maximum=size);integer(len(data),minimum=1,maximum=size-offset)
        if offset%mmap.PAGESIZE or (len(data)%mmap.PAGESIZE and offset+len(data)!=size):
            raise ValueError('userfaultfd copy requires complete pages or final page')
        padded=data+b'\0'*((-len(data))%mmap.PAGESIZE)
        owned=c.create_string_buffer(padded)
        result=self._ioctl(0xC028AA03,struct.pack('=QQQQq',address+offset,c.addressof(owned),len(padded),0,0))
        copied=struct.unpack('=QQQQq',result)[4]
        if copied!=len(padded):raise OSError('incomplete UFFDIO_COPY')
        return {'bytes':len(data),'source_sha256':hashlib.sha256(data).hexdigest(),'evidence':self.evidence,'zero_copy':False}

    def unregister(self,identity):
        memory,view,address,length,size=self.regions[identity]
        self._ioctl(0x8010AA01,struct.pack('=QQ',address,length))
        self.regions.pop(identity);view=None;memory.close()

    def close(self):
        if self.closed:return
        for key in tuple(self.regions):self.unregister(key)
        os.close(self.fd);self.closed=True


class LibbpfProbe:
    """Load caller-approved ELF bytes, attach programs, consume a bounded ring map."""
    def __init__(self,object_bytes,expected_sha256,decoder,*,map_name='events',gate=PermissionGate(),api=None):
        gate.require('S2')
        if not isinstance(object_bytes,bytes) or not 0<len(object_bytes)<=1048576:
            raise ValueError('bounded BPF object bytes required')
        if hashlib.sha256(object_bytes).hexdigest()!=expected_sha256:raise ValueError('BPF consumed bytes identity mismatch')
        nonempty(map_name)
        if not callable(decoder):raise TypeError('explicit event decoder required')
        self.evidence='callable-fixture' if api is not None else 'native-executed'
        self.api=api or c.CDLL(ctypes.util.find_library('bpf') or 'libbpf.so.1',use_errno=True)
        self.object=None;self.ring=None;self.links=[];self.events=[];self.error=None;self.capacity=0;self.dropped=0
        self.decoder=decoder;self.sha=expected_sha256;self.owned=c.create_string_buffer(object_bytes)
        callback_type=c.CFUNCTYPE(c.c_int,c.c_void_p,c.c_void_p,c.c_size_t)
        self.callback=callback_type(self._event)
        signatures={
            'bpf_object__open_mem':([c.c_void_p,c.c_size_t,c.c_void_p],c.c_void_p),
            'libbpf_get_error':([c.c_void_p],c.c_long),'bpf_object__load':([c.c_void_p],c.c_int),
            'bpf_object__next_program':([c.c_void_p,c.c_void_p],c.c_void_p),
            'bpf_program__attach':([c.c_void_p],c.c_void_p),
            'bpf_object__find_map_fd_by_name':([c.c_void_p,c.c_char_p],c.c_int),
            'ring_buffer__new':([c.c_int,callback_type,c.c_void_p,c.c_void_p],c.c_void_p),
            'ring_buffer__poll':([c.c_void_p,c.c_int],c.c_int),
            'ring_buffer__free':([c.c_void_p],None),'bpf_link__destroy':([c.c_void_p],c.c_int),
            'bpf_object__close':([c.c_void_p],None)}
        if api is None:
            for name,(args,result) in signatures.items():
                fn=getattr(self.api,name);fn.argtypes=args;fn.restype=result
        try:
            self.object=self._pointer(self.api.bpf_object__open_mem(self.owned,len(object_bytes),None))
            if self.api.bpf_object__load(self.object):raise OSError('BPF verifier/load rejected')
            previous=None
            for _ in range(64):
                program=self.api.bpf_object__next_program(self.object,previous)
                if not program:break
                self.links.append(self._pointer(self.api.bpf_program__attach(program)));previous=program
            else:raise ValueError('BPF program count bound')
            fd=self.api.bpf_object__find_map_fd_by_name(self.object,map_name.encode())
            if fd<0:raise OSError('BPF event ring missing')
            self.ring=self._pointer(self.api.ring_buffer__new(fd,self.callback,None,None))
        except BaseException:self.close();raise

    def _pointer(self,value):
        if not value or self.api.libbpf_get_error(value):raise OSError('libbpf lifecycle failure')
        return value

    def _event(self,context,data,size):
        if size>65536:self.error='event record bound';return -1
        if len(self.events)>=self.capacity:self.dropped+=1;return -1
        try:self.events.append(self.decoder(c.string_at(data,size)))
        except Exception as exc:self.error=type(exc).__name__;return -1
        return 0

    def poll(self,timeout,capacity):
        finite(timeout);integer(capacity,minimum=1,maximum=100000)
        if not self.ring or timeout>5:raise ValueError('closed/unbounded BPF poll')
        self.events=[];self.error=None;self.capacity=capacity
        status=self.api.ring_buffer__poll(self.ring,int(timeout*1000))
        if self.error:raise ValueError(self.error)
        if status<0 and status!=-4:raise OSError('BPF poll interrupted or overflowed')
        return list(self.events)

    def close(self):
        if self.ring:self.api.ring_buffer__free(self.ring);self.ring=None
        while self.links:self.api.bpf_link__destroy(self.links.pop())
        if self.object:self.api.bpf_object__close(self.object);self.object=None
