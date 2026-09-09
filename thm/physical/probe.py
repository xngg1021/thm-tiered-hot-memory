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


def linux(root, *, sysroot=Path('/sys'), mountinfo=None):
    root=Path(root).resolve(); nodes=[]; edges=[]
    candidates=[m for m in mounts(mountinfo if mountinfo is not None else read('/proc/self/mountinfo') or '')
                if root==Path(m['mount']) or Path(m['mount']) in root.parents]
    m=max(candidates,key=lambda m:len(m['mount'])) if candidates else None
    fields={}
    if m:
        fs=m['filesystem'];relation=digest({'device':m['device'],'root':m['root'],'mount':m['mount']})
        remote=True if fs in ('nfs','nfs4','cifs','smb3','ceph','lustre','beegfs') else False if fs in ('ext4','xfs','btrfs','tmpfs','vfat','exfat','overlay','zfs') else None
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
    return fields,StorageTopology(tuple(nodes),tuple(edges))


def windows_fields(payload):
    data=json.loads(payload) if isinstance(payload,str) else payload
    # MediaType/BusType are CIM observations; FriendlyName/SerialNumber never used.
    disk=data.get('disk') or {};volume=data.get('volume') or {}
    if isinstance(disk,list):disk=disk[0] if len(disk)==1 else {}
    return {'filesystem':volume.get('FileSystem'),'protocol':str(disk['BusType']) if disk.get('BusType') is not None else None,
        'readonly':disk.get('IsReadOnly'),'logical_block':disk.get('LogicalSectorSize'),
        'physical_block':disk.get('PhysicalSectorSize'),'media_class':'unknown','remote':None,
        'numa_node':None}


def macos_fields(payload):
    d=plistlib.loads(payload) if isinstance(payload,bytes) else payload
    return {'filesystem':d.get('FilesystemType'),'protocol':d.get('BusProtocol'),
        'readonly':not d['Writable'] if type(d.get('Writable')) is bool else None,
        'logical_block':d.get('DeviceBlockSize'),'media_class':'nonrotating-block' if d.get('SolidState') is True else 'unknown',
        'remote':None,'numa_node':None}


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
            r=subprocess.run(['diskutil','info','-plist',str(path)],capture_output=True,timeout=5,check=True)
            fields=macos_fields(r.stdout)
    except (OSError,ValueError,subprocess.SubprocessError):fields={}
    usage=shutil.disk_usage(path)
    target=StorageTarget('local-'+digest(str(path))[:20],root=str(path),capacity=usage.total,free_capacity=usage.free,
        adapter='local-filesystem',observation='public-os-best-effort',**fields)
    return target,topology
