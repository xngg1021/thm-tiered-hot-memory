"""No optional enterprise driver is imported or advertised as executable."""
from typing import Protocol
from .contracts import TransferExtent

class PhysicalAdapter(Protocol):
    def read(self, extent: TransferExtent) -> bytes: ...
    def verify(self, object_sha256: str) -> bool: ...

EXTENSIONS = ('dram','unified-memory','vram','pmem','dax','cxl-type3','far-memory',
    'nvme','sata-ssd','sas-ssd','cmr-hdd','smr-hdd','zns','usb','sd','emmc','ufs',
    'smb','nfs','nas','nvme-tcp','nvme-rdma','fc-nvme','ceph-rbd','lustre','beegfs',
    'daos','s3','hsm','tape','archive','spdk','gds-cufile')

def capabilities():
    return {'local-filesystem':{'adapter':'implemented','buffered':True,'mmap':True,
                'hardware_performance':'pending-real-hardware'},
        **{name:{'adapter':'unavailable','contract':'extension-descriptor',
                'hardware_performance':'unvalidated'} for name in EXTENSIONS}}

class LocalFilesystemAdapter:
    """Immutable content-addressed extent reads, with physical-only telemetry."""
    def __init__(self,root,*,mode='buffered'):
        from pathlib import Path
        if mode not in ('buffered','mmap'):raise ValueError('invalid read mode')
        self.root=Path(root);self.mode=mode
        if self.root.is_symlink() or not self.root.is_dir():raise ValueError('invalid local root')
    def verify(self,object_sha256):
        from .segments import object_path,file_sha
        path=object_path(self.root,object_sha256+'.seg')
        return path.is_file() and file_sha(path)==object_sha256
    def read(self,extent,*,telemetry=None):
        import mmap
        import os
        import time
        from .segments import object_path
        path=object_path(self.root,extent.object_sha256+'.seg');start=time.perf_counter()
        with path.open('rb') as f:
            if extent.offset+extent.length>os.fstat(f.fileno()).st_size:raise ValueError('transfer exceeds object extent')
            if self.mode=='mmap':
                with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mapped:data=mapped[extent.offset:extent.offset+extent.length]
            else:f.seek(extent.offset);data=f.read(extent.length)
            if len(data)!=extent.length:raise ValueError('short physical read')
        if telemetry is not None:
            telemetry.bytes_requested+=extent.length;telemetry.bytes_read+=len(data)
            telemetry.transfer_seconds+=time.perf_counter()-start;telemetry.access_mode=self.mode
        return data
