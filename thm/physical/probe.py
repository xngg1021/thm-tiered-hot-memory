"""Read-only public OS probes. Missing observations stay unknown."""
from dataclasses import replace
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
from .contracts import StorageTarget, StorageTopology, TopologyNode, TopologyEdge
from thm.runtime.identity import digest


def read(path):
    try:return Path(path).read_text().strip()
    except (OSError,UnicodeError):return None


def integer(value):
    try:return int(value)
    except (ValueError,TypeError):return None


def unescape(value):
    return re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),value)


def mounts(text):
    result=[]
    for line in text.splitlines():
        parts=line.split()
        try:
            split=parts.index('-')
            result.append({'device':parts[2],'root':unescape(parts[3]),'mount':unescape(parts[4]),
                'options':parts[5].split(','),'filesystem':parts[split+1],
                'source':unescape(parts[split+2]),'super_options':parts[split+3].split(',')})
        except (IndexError,ValueError):continue
    return result


def linux_block_remote(block, sysroot=Path('/sys'), seen=None):
    """Use kernel transport observations, never filesystem or product names."""
    if not block.exists():return None
    block=block.resolve();seen=set() if seen is None else set(seen)
    if block in seen:return None
    seen.add(block)
    if (block/'partition').exists():block=block.parent
    slaves=list((block/'slaves').glob('*'))
    if slaves:
        observed=[linux_block_remote(p,sysroot,seen) for p in slaves]
        return True if any(v is True for v in observed) else False if all(v is False for v in observed) else None
    ancestors=(block,*block.parents)
    # iSCSI sessions and FC host classes identify remote SCSI transports.
    for parent in ancestors:
        if re.fullmatch(r'session[0-9]+',parent.name):return True
        if re.fullmatch(r'host[0-9]+',parent.name) and any((sysroot/'class'/kind/parent.name).exists() for kind in ('iscsi_host','fc_host')):return True
        if re.fullmatch(r'nvme[0-9]+',parent.name):
            transport=read(parent/'transport')
            if transport=='pcie':return False
            if transport in ('tcp','rdma','fc'):return True
            return None
    # Virtual/loop devices do not establish where their backing bytes reside.
    if any(parent.name=='virtual' for parent in ancestors):return None
    if any(re.fullmatch(r'(ata|usb)[0-9]+',parent.name) for parent in ancestors):return False
    return None


def macos_mountpoint(output):
    # POSIX df -P emits one row per filesystem and keeps the mount point last;
    # maxsplit preserves spaces in mounted volume names, including APFS volumes.
    lines=output.strip().splitlines()
    fields=lines[-1].split(None,5) if len(lines)>=2 else []
    if len(fields)!=6 or not fields[5].startswith('/'):
        raise ValueError('containing macOS volume unavailable')
    return unescape(fields[5])


def linux(root, *, sysroot=Path('/sys'), mountinfo=None):
    root=Path(root).resolve(); nodes=[]; edges=[]
    candidates=[m for m in mounts(mountinfo if mountinfo is not None else read('/proc/self/mountinfo') or '')
                if root==Path(m['mount']) or Path(m['mount']) in root.parents]
    m=max(candidates,key=lambda m:len(m['mount'])) if candidates else None
    fields={}
    if m:
        fs=m['filesystem'];relation=digest({'device':m['device'],'root':m['root'],'mount':m['mount']})
        block=sysroot/'dev/block'/m['device']
        remote=True if fs in ('nfs','nfs4','cifs','smb3','ceph','lustre','beegfs') else False if fs in ('tmpfs','ramfs') else None if fs=='overlay' else linux_block_remote(block,sysroot)
        fields.update(filesystem=fs,mount_relation=relation,readonly='ro' in m['options'],remote=remote)
        block=sysroot/'dev/block'/m['device']
        if block.exists():
            resolved=block.resolve();queue=resolved/'queue'
            if not queue.exists():queue=resolved.parent/'queue'
            rotational=integer(read(queue/'rotational'))
            fields.update(media_class='rotating-block' if rotational==1 else 'nonrotating-block' if rotational==0 else 'unknown',
                logical_block=integer(read(queue/'logical_block_size')),
                physical_block=integer(read(queue/'physical_block_size')),zoned=read(queue/'zoned'))
            numa=integer(read(resolved/'device/numa_node'))
            fields['numa_node']=numa if numa is not None and numa>=0 else None
            bdfs=re.findall(r'\b[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]\b',str(resolved))
            fields['pcie_bdf']=bdfs[-1] if bdfs else None
            subsystem=resolved/'device/subsystem'
            if subsystem.exists():fields['protocol']=subsystem.resolve().name
            nodes.append(TopologyNode('block','block-storage',{'relation':relation}))
            edges.append(TopologyEdge('block','mount','mounted-on'))
        if 'dax' in m['options']+m['super_options']:fields['dax']=True
    nodes.append(TopologyNode('mount','filesystem',{'filesystem':fields.get('filesystem')}))
    for node in sorted((sysroot/'devices/system/node').glob('node[0-9]*')):
        idx=integer(node.name[4:])
        if idx is None:continue
        nid=node.name;nodes.append(TopologyNode(nid,'numa-node',{'cpulist':read(node/'cpulist')}))
        nodes.append(TopologyNode(nid+'-memory','dram-or-far-memory',{'classification':'unknown'}))
        edges.append(TopologyEdge(nid,nid+'-memory','attached-memory'))
    ids={n.node_id for n in nodes}
    for node in sorted((sysroot/'devices/system/node').glob('node[0-9]*')):
        for i,distance in enumerate((read(node/'distance') or '').split()):
            if node.name in ids and 'node'+str(i) in ids:
                edges.append(TopologyEdge(node.name,'node'+str(i),'numa-distance',numa_distance=integer(distance)))
    sockets={}
    for cpu in sorted((sysroot/'devices/system/cpu').glob('cpu[0-9]*')):
        socket=integer(read(cpu/'topology/physical_package_id'))
        if socket is not None:sockets.setdefault(socket,[]).append(cpu.name)
    for socket,cores in sockets.items():
        sid='socket-'+str(socket);nodes.append(TopologyNode(sid,'cpu-socket'))
        nodes.append(TopologyNode(sid+'-cores','core-group',{'logical_cpus':len(cores)}))
        edges.append(TopologyEdge(sid,sid+'-cores','contains'))
    for kind,base,pattern in [('persistent-memory','bus/nd/devices','namespace*'),('cxl-memory','bus/cxl/devices','mem*'),
                              ('dax-device','class/dax','dax*'),('nic','class/net','*')]:
        for i,entry in enumerate(sorted((sysroot/base).glob(pattern))):
            nodes.append(TopologyNode(kind+'-'+str(i),kind,{'observation':'sysfs-presence; performance unvalidated'}))
    if fields.get('pcie_bdf'):
        pci='pci-'+fields['pcie_bdf'];nodes.append(TopologyNode(pci,'pcie-device'))
        if any(n.node_id=='block' for n in nodes):edges.append(TopologyEdge(pci,'block','pcie-relation'))
    if fields.get('numa_node') is not None and 'node'+str(fields['numa_node']) in {n.node_id for n in nodes}:
        edges.append(TopologyEdge('node'+str(fields['numa_node']),'block','observed-device-affinity'))
    for i,gpu in enumerate(sorted((sysroot/'class/drm').glob('card[0-9]'))):
        device=gpu/'device'
        if device.exists():
            gid='accelerator-'+str(i);nodes.append(TopologyNode(gid,'accelerator',{'observation':'public-drm-device; memory/copy capabilities unknown'}))
            numa=integer(read(device/'numa_node'))
            if numa is not None and 'node'+str(numa) in {n.node_id for n in nodes}:edges.append(TopologyEdge('node'+str(numa),gid,'observed-device-affinity'))
    return fields,StorageTopology(tuple(nodes),tuple(edges))


def windows_fields(payload):
    data=json.loads(payload) if isinstance(payload,str) else payload
    # MediaType/BusType are CIM observations; FriendlyName/SerialNumber never used.
    disk=data.get('disk') or {};volume=data.get('volume') or {}
    if isinstance(disk,list):disk=disk[0] if len(disk)==1 else {}
    if not isinstance(disk,dict):disk={}
    if not isinstance(volume,dict):volume={}
    bus=disk.get('BusType')
    # MSFT_Disk BusType enum, including numeric ConvertTo-Json output:
    # https://learn.microsoft.com/en-us/windows-hardware/drivers/storage/msft-disk
    # SCSI/RAID/virtual/Storage Spaces alone do not prove local backing.
    local={2,3,7,10,11,12,13,17}
    network={6,9}
    names={'atapi':2,'ata':3,'usb':7,'sas':10,'sata':11,'sd':12,'mmc':13,
           'nvme':17,'fibre channel':6,'fibrechannel':6,'iscsi':9}
    code=bus if type(bus) is int else names.get(bus.strip().lower()) if isinstance(bus,str) else None
    if isinstance(bus,str) and bus.strip().isdigit():code=int(bus.strip())
    remote=False if code in local else True if code in network else None
    return {'filesystem':volume.get('FileSystem'),'protocol':str(bus) if bus is not None else None,
        'readonly':disk.get('IsReadOnly'),'logical_block':disk.get('LogicalSectorSize'),
        'physical_block':disk.get('PhysicalSectorSize'),'media_class':'unknown','remote':remote,
        'numa_node':None}


def macos_fields(payload):
    d=plistlib.loads(payload) if isinstance(payload,bytes) else payload
    bus=d.get('BusProtocol')
    protocol=bus.strip().lower() if isinstance(bus,str) else None
    local={'pci-express','pci','nvme','sata','ata','sas','usb','secure digital','sd','firewire','thunderbolt'}
    network={'iscsi','fibre channel','fibrechannel','smb','nfs'}
    remote=False if protocol in local else True if protocol in network else None
    # A disk-image protocol or explicit virtual observation never proves local
    # backing, even if the image happens to reside on an internal volume.
    if d.get('VirtualOrPhysical')=='Virtual' or d.get('DiskImage') is True:remote=None
    return {'filesystem':d.get('FilesystemType'),'protocol':d.get('BusProtocol'),
        'readonly':not d['Writable'] if type(d.get('Writable')) is bool else None,
        'logical_block':d.get('DeviceBlockSize'),'media_class':'nonrotating-block' if d.get('SolidState') is True else 'unknown',
        'remote':remote,'numa_node':None}


def probe(root):
    path=Path(root)
    if path.is_symlink() or not path.is_dir():raise ValueError('existing nonsymlink storage root required')
    path=path.resolve();fields={};topology=StorageTopology((),())
    system=platform.system()
    try:
        if system=='Linux':fields,topology=linux(path)
        elif system=='Windows':
            drive=path.drive.rstrip(':')
            if not re.fullmatch('[A-Za-z]',drive):raise ValueError('local drive unavailable')
            script=f"$v=Get-Volume -DriveLetter '{drive}'; $d=Get-Partition -DriveLetter '{drive}' | Get-Disk; @{{volume=$v;disk=$d}} | ConvertTo-Json -Depth 3"
            r=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,timeout=5,check=True)
            fields=windows_fields(r.stdout)
        elif system=='Darwin':
            volume=subprocess.run(['df','-P',str(path)],capture_output=True,text=True,timeout=5,check=True)
            mount=macos_mountpoint(volume.stdout)
            r=subprocess.run(['diskutil','info','-plist',mount],capture_output=True,timeout=5,check=True)
            fields=macos_fields(r.stdout)
    except (OSError,ValueError,subprocess.SubprocessError):fields={}
    usage=shutil.disk_usage(path)
    target=StorageTarget('local-'+digest(str(path))[:20],root=str(path),capacity=usage.total,free_capacity=usage.free,
        adapter='local-filesystem',observation='public-os-best-effort',**fields)
    return target,topology
