import json
from pathlib import Path
import tempfile
import unittest
from thm.physical.probe import probe,linux,mounts,windows_fields,macos_fields

class ProbeTests(unittest.TestCase):
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
            fields,g=linux(d,sysroot=s,mountinfo='1 0 0:1 / / rw - nfs server:/private rw')
            self.assertTrue(fields['remote']);self.assertIsNone(fields.get('numa_node'))
            self.assertTrue(any(e.numa_distance==10 for e in g.edges))
            self.assertNotIn('private',str(g))
