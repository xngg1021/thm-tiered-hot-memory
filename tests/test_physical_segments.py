from contextlib import closing
import dataclasses
import tempfile
import unittest
from pathlib import Path
from thm.retrieval import SearchIndex,Document
from thm.runtime.testing import FakeEncoder
from thm.physical.segments import create,read_segment,export,current,object_path

class SegmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.encoder=FakeEncoder();self.profile=self.encoder.profile
        self.keys=[['a','hash']];self.values=self.encoder.encode_many(['alpha'])
    def tearDown(self):self.temp.cleanup()
    def test_buffered_mmap_corruption(self):
        m=create(self.root,self.profile,'g',self.keys,self.values);p=object_path(self.root,m['object_name'])
        a=read_segment(p,m,self.profile,'g',self.keys)
        self.assertEqual(a,read_segment(p,m,self.profile,'g',self.keys,mode='mmap'))
        for profile,g,keys in [(dataclasses.replace(self.profile,device='cuda'),'g',self.keys),(self.profile,'stale',self.keys),(self.profile,'g',[['b','hash']])]:
            with self.assertRaises(ValueError):read_segment(p,m,profile,g,keys)
        with self.assertRaises(FileExistsError):create(self.root,self.profile,'g',self.keys,self.values)
        p.write_bytes(p.read_bytes()[:-1])
        with self.assertRaises(ValueError):read_segment(p,m,self.profile,'g',self.keys)
    def test_invalid_vectors(self):
        for values in ([[0.]*self.profile.dimension],[[float('nan')]*self.profile.dimension],[[float('inf')]*self.profile.dimension],[[1.,0.]]):
            with self.assertRaises(ValueError):create(self.root,self.profile,'g',self.keys,values)
    def test_index_parity_and_stale_publication(self):
        with closing(SearchIndex(self.root/'index.sqlite')) as index:
            docs=[Document('a','scope','s',0,'alpha'),Document('b','scope','s',1,'beta')]
            index.replace_scope('scope',docs);index.embed('scope',self.encoder,self.encoder.model_id,vector_storage='blob')
            before=index.search('scope','alpha',mode='dense',encoder=self.encoder,model_id=self.encoder.model_id)
            export(index,'scope',self.profile,self.root)
            after=index.search('scope','alpha',mode='dense',encoder=self.encoder,model_id=self.encoder.model_id)
            self.assertEqual(before['selected'],after['selected'])
            self.assertGreater(index.physical_io_receipt['bytes_read'],0)
            other=self.root/'other';other.mkdir()
            with self.assertRaisesRegex(ValueError,'generation changed'):
                export(index,'scope',self.profile,other,before_publish=lambda:index.replace_scope('scope',[Document('c','scope','s',0,'changed')]))
