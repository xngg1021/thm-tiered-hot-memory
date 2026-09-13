from pathlib import Path
import tempfile
import unittest
from thm.retrieval import SearchIndex,Document,TokenCounter
from thm.long_tail_retrieval import LongTailSearchIndex
from thm.long_tail import EvidenceCandidate,Event,EventGraph,TimeInterval
from thm.evaluation.ceiling import RetrievalCeilingReport


class ExpansionAndDependencies(unittest.TestCase):
    def test_expansion_gold_is_a_gain_not_ranking_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            class SeedIndex(SearchIndex):
                def _lexical_channels(self,scope,query,mode,candidate_limit):
                    return [[row['rowid'] for row in self.rows(scope) if row['id']=='seed']]
            index=SeedIndex(Path(directory)/'db',TokenCounter('utf8_bytes'))
            try:
                index.replace_scope('s',[Document('seed','s','session',0,'querymatch'),Document('gold','s','session',1,'hidden evidence')])
                result=index.search('s','querymatch',budget=600,neighbor_turns=1)
            finally:index.close()
        self.assertEqual(result['candidate_ids'],['seed'])
        self.assertEqual(result['pre_expansion_ranked_ids'],['seed'])
        self.assertIn('gold',result['packing_ids'])
        seed=EvidenceCandidate('seed',10,0)
        gold=EvidenceCandidate('gold',10,0,frozenset({'g'}))
        out=RetrievalCeilingReport('q',frozenset({'g'}),(seed,),('seed',),('seed','gold'),100,
             packing_ids=('seed','gold'),packing_candidates=(seed,gold)).public()
        self.assertEqual(out['candidate_ceiling']['covered_units'],0)
        self.assertEqual(out['ranking_loss'],0)
        self.assertEqual(out['neighbor_expansion_gain'],1)
        self.assertEqual(out['packing_loss'],0)

    def _index(self,path,counter):
        index=LongTailSearchIndex(path,counter)
        index.replace_scope('s',[Document('shared','s','session',0,'target update'),
                                Document('p1','s','session',1,'first source '+('a'*150)),
                                Document('p2','s','session',2,'second source '+('b'*150))])
        rows={row['id']:row for row in index.rows('s')}
        def event(name,source,date,predecessor=()):
            return Event(name,'s',source,rows[source]['hash'],TimeInterval.parse(date),predecessor=predecessor)
        index.attach_events(EventGraph('s',(event('a','p1','2026-01-01'),event('b','p2','2026-01-02'),
            event('one','shared','2026-02-01',('a',)),event('two','shared','2026-02-02',('b',)))))
        return index

    def test_shared_source_accumulates_both_event_chains(self):
        with tempfile.TemporaryDirectory() as directory:
            index=self._index(Path(directory)/'db',TokenCounter('utf8_bytes'))
            try:
                result=index.search('s','latest target',budget=300)
                from thm.features import RetrievalFeatures
                with self.assertRaisesRegex(ValueError,'complete-source'):
                    index.search('s','latest target',features=RetrievalFeatures(segment=True))
                self.assertEqual(index.required_source_sets['shared'],frozenset({'shared','p1','p2'}))
                self.assertNotIn('shared',[row['id'] for row in result['selected']])
            finally:index.close()

    def test_nonadditive_counters_preserve_whole_dependency_groups(self):
        tokenizer=TokenCounter('utf8_bytes');tokenizer.encode=lambda text:list(text)
        for counter in (tokenizer,lambda text:len(text)):
            with tempfile.TemporaryDirectory() as directory:
                index=self._index(Path(directory)/'db',counter)
                try:
                    short=index.search('s','latest target',budget=300)
                    self.assertNotIn('shared',[row['id'] for row in short['selected']])
                    self.assertTrue(short['long_tail']['dependencies_atomic'])
                    full=index.search('s','latest target',budget=1000)
                    self.assertEqual({row['id'] for row in full['selected']},{'shared','p1','p2'})
                    self.assertLessEqual(counter(full['context']),1000)
                finally:index.close()


    def test_batch_segment_guard_runs_before_encoder_or_packing(self):
        from thm.features import RetrievalFeatures
        class Encoder:
            model_id='fixture-batch'
            def __call__(self,texts):raise AssertionError('rejected query must not encode')
        with tempfile.TemporaryDirectory() as directory:
            index=self._index(Path(directory)/'db',TokenCounter('utf8_bytes'))
            try:
                for mode in ('dense','hybrid'):
                    with self.assertRaisesRegex(ValueError,'complete-source'):
                        index.search_many('s',['latest target'],mode=mode,encoder=Encoder(),model_id='fixture-batch',
                                          features=RetrievalFeatures(segment=True),overlap=True)
            finally:index.close()

    def test_overlapped_batch_keeps_each_queries_dependencies_and_receipt(self):
        class Encoder:
            model_id='fixture-batch'
            def __call__(self,texts):return [[1.,0.] for text in texts]
        with tempfile.TemporaryDirectory() as directory:
            index=self._index(Path(directory)/'db',TokenCounter('utf8_bytes'));encoder=Encoder()
            try:
                index.embed('s',encoder,encoder.model_id)
                settings=dict(mode='hybrid',encoder=encoder,model_id=encoder.model_id,budget=300)
                queries=['latest target','neutral question']
                singles=[index.search('s',query,**settings) for query in queries]
                index._clear_caches()
                batch=index.search_many('s',queries,overlap=True,query_batch_size=2,**settings)
                self.assertTrue(batch[0]['batch_receipt']['overlap_active'])
                self.assertEqual(batch[0]['long_tail']['track'],'0G')
                self.assertNotIn('shared',[row['id'] for row in batch[0]['selected']])
                for expected,actual in zip(singles,batch):
                    self.assertEqual(actual['context'],expected['context'])
                    self.assertEqual(actual['long_tail'],expected['long_tail'])
            finally:index.close()


    def test_temporal_tip_and_neutral_queries_cannot_pack_intermediate_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            index=LongTailSearchIndex(Path(directory)/'db',TokenCounter('utf8_bytes'))
            try:
                index.replace_scope('s',[Document('a','s','session',0,'large source '+('a'*1000)),
                    Document('b','s','session',1,'middle event'),Document('c','s','session',2,'tip event')])
                rows={row['id']:row for row in index.rows('s')}
                events=[Event(key,'s',key,rows[key]['hash'],TimeInterval.parse(date),predecessor=parents)
                    for key,date,parents in [('a','2026-01-01',()),('b','2026-02-01',('a',)),('c','2026-03-01',('b',))]]
                index.attach_events(EventGraph('s',events))
                for query in ('closest before 2026-04-01','middle event'):
                    result=index.search('s',query,budget=300)
                    self.assertNotIn('b',[row['id'] for row in result['selected']])
                    self.assertNotIn('c',[row['id'] for row in result['selected']])
                    self.assertEqual(index.required_source_sets['b'],frozenset({'a','b'}))
            finally:index.close()


if __name__=='__main__':unittest.main()
