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
