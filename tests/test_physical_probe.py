import json
from pathlib import Path
import tempfile
import unittest
from thm.physical.probe import probe,linux,mounts,windows_fields,macos_fields

class ProbeTests(unittest.TestCase):
    def test_macos_bus_evidence_reaches_local_only_planner(self):
        import plistlib
        from thm.physical.contracts import StorageTarget,StorageProfile,PlacementIntent,DataRole
        from thm.physical.planner import plan
        for bus,remote in [('PCI-Express',False),('NVMe',False),('SATA',False),('SAS',False),
                           ('USB',False),('Thunderbolt',False),('Disk Image',None),
                           ('Virtual Interface',None),('unknown',None),('',None),
                           ('iSCSI',True),('Fibre Channel',True),('NFS',True)]:
            with self.subTest(bus=bus):
                fields=macos_fields(plistlib.dumps({'BusProtocol':bus,'Writable':True,'FilesystemType':'apfs'}))
                self.assertIs(fields['remote'],remote)
                target=StorageTarget('mac',free_capacity=100,adapter='local-filesystem',**fields)
                profile=StorageProfile(target.fingerprint,({'operation':'buffered-random','size':4096,
                    'concurrency':1,'p95_ms':1.,'bytes_per_second':1000.},),1024,1.)
                result=plan(PlacementIntent(DataRole.VECTOR_SEGMENT,capacity_required=10),[target],[profile])
                self.assertEqual(result['selected_target'],'mac' if remote is False else None)
        for payload in ({},{'MediaName':'fast local NVMe'},
                        {'BusProtocol':'PCI-Express','VirtualOrPhysical':'Virtual'},
                        {'BusProtocol':'USB','DiskImage':True}):
            self.assertIsNone(macos_fields(payload)['remote'])

    def test_windows_bus_evidence_and_local_only_planner(self):
        from thm.physical.contracts import StorageTarget,StorageProfile,PlacementIntent,DataRole
        from thm.physical.planner import plan
        cases=[('NVMe',False),(17,False),('17',False),('SATA',False),(11,False),
               ('SAS',False),(10,False),('USB',False),(7,False),
               ('SCSI',None),(1,None),('RAID',None),('Virtual',None),(14,None),
               ('File Backed Virtual',None),('Storage Spaces',None),(16,None),
               ('unknown',None),(None,None),(True,None),('iSCSI',True),(9,True),
               ('Fibre Channel',True),(6,True)]
        for bus,remote in cases:
            with self.subTest(bus=bus):
                fields=windows_fields(json.dumps({'disk':{'BusType':bus,'IsReadOnly':False},'volume':{'FileSystem':'NTFS'}}))
                self.assertIs(fields['remote'],remote)
                target=StorageTarget('windows',free_capacity=100,adapter='local-filesystem',**fields)
                profile=StorageProfile(target.fingerprint,({'operation':'buffered-random','size':4096,
                    'concurrency':1,'p95_ms':1.,'bytes_per_second':1000.},),1024,1.)
                result=plan(PlacementIntent(DataRole.VECTOR_SEGMENT,capacity_required=10,local_only=True),[target],[profile])
                self.assertEqual(result['selected_target'],'windows' if remote is False else None)
        for disk in (None,[],[{'BusType':'NVMe'},{'BusType':'SATA'}],{'FriendlyName':'NVMe local disk'},'unresolved'):
            self.assertIsNone(windows_fields({'disk':disk})['remote'])
        self.assertFalse(windows_fields({'disk':[{'BusType':'NVMe'}]})['remote'])

    def test_missing_and_privacy(self):
        with tempfile.TemporaryDirectory() as d:
            target,topology=probe(d)
            self.assertNotIn(d,json.dumps(target.public()))
            self.assertEqual(target.fingerprint,__import__('dataclasses').replace(target,free_capacity=1).fingerprint)
            fields,graph=linux(d,sysroot=Path(d),mountinfo='invalid')
            self.assertEqual(fields,{})
    def test_mount_and_foreign_parsers(self):
        self.assertEqual(mounts('1 0 8:1 / /a\\040b rw - ext4 /dev/sda rw')[0]['mount'],'/a b')
        self.assertEqual(windows_fields({'disk':{'FriendlyName':'NVMe fast CXL','SerialNumber':'private'},'volume':{}})['media_class'],'unknown')
        self.assertEqual(macos_fields({'MediaName':'super-fast'})['media_class'],'unknown')
    def test_synthetic_topology(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d);node=s/'devices/system/node/node0';node.mkdir(parents=True)
            (node/'distance').write_text('10');(node/'cpulist').write_text('0-3')
            mount=s.resolve().as_posix().replace(' ',r'\040')
            fields,g=linux(d,sysroot=s,mountinfo=f'1 0 0:1 / {mount} rw - nfs server:/private rw')
            self.assertTrue(fields['remote']);self.assertIsNone(fields.get('numa_node'))
            self.assertTrue(any(e.numa_distance==10 for e in g.edges))
            self.assertNotIn('private',str(g))
