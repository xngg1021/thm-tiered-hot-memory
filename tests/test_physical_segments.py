from contextlib import closing
import dataclasses
import tempfile
import unittest
from pathlib import Path
from thm.retrieval import SearchIndex,Document
from thm.runtime.testing import FakeEncoder
from thm.physical.segments import create,read_segment,export,current,object_path

class SegmentTests(unittest.TestCase):
    def test_export_rejects_same_generation_reembedding_from_another_connection(self):
        for storage in ('json','blob'):
            with self.subTest(storage=storage):
                folder=self.root/storage;folder.mkdir()
                newroot=folder/'new';newroot.mkdir()
                with closing(SearchIndex(folder/'index.sqlite')) as index:
                    docs=[Document('a','scope','s',0,'alpha'),Document('b','scope','s',1,'beta')]
                    index.replace_scope('scope',docs)
                    index.embed('scope',self.encoder,self.encoder.model_id,vector_storage=storage)
                    generation=index.db.execute('SELECT generation FROM scopes').fetchone()[0]
                    changed=FakeEncoder(kind='semantic-drift')
                    self.assertEqual(changed.profile,self.profile)
                    newer={}
                    def reembed():
                        with closing(SearchIndex(index.path)) as other:
                            other.embed('scope',changed,changed.model_id,vector_storage=storage)
                            export(other,'scope',self.profile,newroot)
                            newer.update(current(other,'scope',self.profile.id))
                    with self.assertRaisesRegex(ValueError,'vector snapshot changed'):
                        export(index,'scope',self.profile,folder,before_publish=reembed)
                    self.assertEqual(index.db.execute('SELECT generation FROM scopes').fetchone()[0],generation)
                    self.assertEqual(current(index,'scope',self.profile.id),newer)
                    from thm.physical.segments import load
                    from thm.runtime.storage import pack,unpack
                    actual=load(index,'scope',self.profile,generation)[1]
                    expected=[unpack(pack(v),self.profile.dimension) for v in changed.encode_many([': alpha',': beta'])]
                    self.assertEqual(actual,expected)

    def test_scope_replacement_clears_placements_transactionally(self):
        import sqlite3
        with closing(SearchIndex(self.root/'index.sqlite')) as index:
            docs=[Document('a','scope','s',0,'alpha')]
            other=[dataclasses.replace(d,scope='other') for d in docs]
            for scope,rows in (('scope',docs),('other',other)):
                index.replace_scope(scope,rows);index.embed(scope,self.encoder,self.encoder.model_id)
                export(index,scope,self.profile,self.root)
            snapshot=lambda:[tuple(r) for r in index.db.execute('SELECT * FROM physical_placements ORDER BY scope')]
            before=snapshot();files={p:p.read_bytes() for p in self.root.glob('*.seg')}
            self.assertEqual(len(files),2)
            self.assertFalse(index.replace_scope('scope',docs)['changed'])
            self.assertEqual(snapshot(),before)
            changed=[dataclasses.replace(d,text='changed') for d in docs]
            index.db.execute("CREATE TRIGGER fail_replace BEFORE INSERT ON docs BEGIN SELECT RAISE(ABORT,'injected'); END")
            with self.assertRaises(sqlite3.IntegrityError):index.replace_scope('scope',changed)
            self.assertEqual(snapshot(),before)
            index.db.execute('DROP TRIGGER fail_replace')
            index.replace_scope('scope',changed)
            self.assertIsNone(current(index,'scope',self.profile.id))
            self.assertIsNotNone(current(index,'other',self.profile.id))
            self.assertEqual({p:p.read_bytes() for p in files},files)

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
    def test_payload_validation_even_with_recomputed_checksums(self):
        import hashlib,json,struct
        m=create(self.root,self.profile,'g',self.keys,self.values)
        raw=object_path(self.root,m['object_name']).read_bytes()
        length=struct.unpack('<I',raw[8:12])[0];offset=12+length
        for value in (float('nan'),float('inf'),0.):
            payload=struct.pack('<'+'f'*self.profile.dimension,*([value]*self.profile.dimension))
            modified=raw[:offset]+payload+hashlib.sha256(payload).digest()
            path=self.root/'corrupt';path.write_bytes(modified)
            manifest={**m,'object_sha256':hashlib.sha256(modified).hexdigest()}
            with self.assertRaises(ValueError):read_segment(path,manifest,self.profile,'g',self.keys)
        for field,value in (('dimension',self.profile.dimension+1),('rows',2),('dtype','f16le'),('schema',2)):
            header={**json.loads(raw[12:offset]),field:value};encoded=json.dumps(header).encode()
            modified=raw[:8]+struct.pack('<I',len(encoded))+encoded+raw[offset:]
            path=self.root/'corrupt';path.write_bytes(modified)
            manifest={**m,field:value,'object_sha256':hashlib.sha256(modified).hexdigest()}
            with self.assertRaises(ValueError):read_segment(path,manifest,self.profile,'g',self.keys)
