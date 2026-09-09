from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from thm.retrieval import SearchIndex,Document
from thm.runtime.testing import FakeEncoder
from thm.physical.contracts import *
from thm.physical.adapters import LocalFilesystemAdapter
from thm.physical.segments import export,current

class IsolationTests(unittest.TestCase):
    def test_extent_reads_are_not_semantic_demand(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);enc=FakeEncoder()
            with closing(SearchIndex(root/'i.sqlite')) as index:
                index.replace_scope('s',[Document('a','s','s',0,'alpha')]);index.embed('s',enc,enc.model_id,vector_storage='blob')
                export(index,'s',enc.profile,root);manifest=current(index,'s',enc.profile.id)
                before=list(index.db.iterdump())
                telemetry=PhysicalTelemetry('test');extent=TransferExtent(manifest['object_sha256'],0,8)
                for mode in ('buffered','mmap'):
                    adapter=LocalFilesystemAdapter(root,mode=mode)
                    self.assertTrue(adapter.verify(manifest['object_sha256']))
                    self.assertEqual(adapter.read(extent,telemetry=telemetry),b'THMSEG01')
                self.assertEqual(before,list(index.db.iterdump()))
                self.assertNotIn('hit',telemetry.receipt());self.assertEqual(telemetry.bytes_read,16)
                with self.assertRaises(ValueError):adapter.read(TransferExtent(manifest['object_sha256'],10**9,1))
    def test_representation_has_no_authority(self):
        parent=LogicalObjectRef('source','parent',GenerationRef('scope','g'))
        with self.assertRaises(ValueError):RepresentationRef(parent,'cache',DataRole.DERIVED_CACHE,authority=True)
        with self.assertRaises(ValueError):SegmentRef(parent,'locator',0,10,complete=True)
        self.assertEqual(PlacementIntent(DataRole.JOURNAL).operation,'buffered-sequential')
        self.assertEqual(PlacementIntent(DataRole.ARCHIVE).workload,'archive')
