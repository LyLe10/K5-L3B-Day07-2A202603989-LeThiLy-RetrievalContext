import copy
import unittest
from unittest.mock import MagicMock

from src import dense as d
from src.retrieval import LexicalRetriever, HybridRetriever, create_retriever, load_snapshot
from test_dense import sample


def corpus():
    chunks = []
    for i in range(264):
        c = d.map_chunk(sample(), 1)
        c.update(id=f'B:{i:064x}', chunk_id=f'B:{i:064x}', text='alpha beta' if i < 2 else 'gamma',
                 section='DDL' if i == 0 else 'Other')
        chunks.append(c)
    return chunks


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.chunks = corpus()
        self.lexical = LexicalRetriever(self.chunks)

    def test_starter_scores_ties_and_determinism(self):
        a = self.lexical.search('alpha', filters=None, top_k=3)
        self.assertEqual([c['id'] for c in a], [c['id'] for c in self.chunks[:2]])
        self.assertAlmostEqual(a[0]['score'], 2**-0.5)
        self.assertEqual(a, self.lexical.search('alpha', filters=None, top_k=3))
        self.assertEqual(a[0]['strategy'], 'B')

    def test_metadata_isolation_and_filters(self):
        self.chunks[0]['text'] = 'changed'
        a = self.lexical.search('alpha', filters={'section': 'DDL'}, top_k=1)
        self.assertEqual(a[0]['text'], 'alpha beta')
        self.assertEqual(a[0]['citation'], self.chunks[0]['citation'])
        a[0]['metadata'].clear()
        self.assertTrue(self.lexical.search('alpha', filters=None, top_k=1)[0]['metadata'])
        self.assertEqual(self.lexical.search('unknown', filters=None, top_k=3), [])

    def test_invalid_queries_topk_filters(self):
        hybrid = HybridRetriever(MagicMock(), self.lexical)
        for r in (self.lexical, hybrid):
            for q, k, f in [('',3,None),(' ',3,None),('x\x00',3,None),('x',0,None),
                             ('x',True,None),('x',265,None),('x',3,{'gold':'x'}),('x',3,[])]:
                with self.subTest(q=q,k=k,f=f), self.assertRaises(d.RetrievalError):
                    r.search(q, filters=f, top_k=k)
            self.assertEqual(r.last_trace['status'], 'error')

    def test_reject_duplicate_or_wrong_snapshot(self):
        for chunks in [self.chunks[:-1], [self.chunks[0]]*264]:
            with self.assertRaises(d.RetrievalError): LexicalRetriever(chunks)
        self.chunks[0]['strategy'] = 'A'
        with self.assertRaises(d.RetrievalError): LexicalRetriever(self.chunks)

    def test_rrf_formula_dedup_ties_and_input_immutability(self):
        a, b = self.chunks[:2]
        left, right = MagicMock(), MagicMock()
        left.search.return_value = [a,a,b]
        right.search.return_value = [b,a]
        before = copy.deepcopy(left.search.return_value)
        hybrid = HybridRetriever(left,right)
        hits = hybrid.search('alpha',filters=None,top_k=2)
        self.assertEqual([c['id'] for c in hits], [a['id'],b['id']])
        self.assertAlmostEqual(hits[0]['score'],1/61+1/62)
        self.assertEqual(hits[0]['component_ranks']['lexical']['rank'],2)
        self.assertEqual(before,left.search.return_value)
        left.search.assert_called_once_with('alpha',filters=None,top_k=20)

    def test_hybrid_empty_single_component_and_failures(self):
        left = MagicMock()
        left.search.return_value = []
        hybrid = HybridRetriever(left,self.lexical)
        self.assertEqual(len(hybrid.search('alpha',filters=None,top_k=1)),1)
        self.assertEqual(hybrid.search('unknown',filters=None,top_k=3),[])
        left.search.side_effect = d.RetrievalError('DATABASE_ERROR')
        with self.assertRaisesRegex(d.RetrievalError,'DATABASE_ERROR'):
            hybrid.search('alpha',filters=None,top_k=3)
        self.assertEqual(hybrid.last_trace['status'],'error')

    def test_hybrid_provenance_conflict(self):
        left = MagicMock()
        left.search.return_value = [dict(self.chunks[0], text='conflicting text')]
        with self.assertRaisesRegex(d.RetrievalError,'CHUNK_PROVENANCE_MISMATCH'):
            HybridRetriever(left,self.lexical).search('alpha',filters=None,top_k=3)

    def test_config_and_factory(self):
        dense = MagicMock()
        self.assertIs(create_retriever('dense',dense),dense)
        self.assertIs(create_retriever('lexical',dense,lexical=self.lexical),self.lexical)
        self.assertIsInstance(create_retriever('hybrid',dense,lexical=self.lexical),HybridRetriever)
        with self.assertRaises(d.RetrievalError):create_retriever('other',dense)
        for kwargs in [dict(rrf_k=0),dict(candidate_k=265),dict(rrf_k=True)]:
            with self.assertRaises(d.RetrievalError):HybridRetriever(dense,self.lexical,**kwargs)

    def test_snapshot_loader_uses_namespace_and_preflight(self):
        dense = MagicMock()
        cur = dense.transaction.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = [tuple(c[k] for k in d.COLUMNS) for c in self.chunks]
        loaded = load_snapshot(dense)
        self.assertEqual(len(loaded),264)
        dense.preflight.assert_called_once()
        self.assertEqual(cur.execute.call_args.args[1],d.NAMESPACE)
        self.assertNotIn('embedding <=>',cur.execute.call_args.args[0])
