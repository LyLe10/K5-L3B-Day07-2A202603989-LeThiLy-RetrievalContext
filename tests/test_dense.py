import copy
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
import tempfile
from unittest.mock import MagicMock, patch

from src import dense as d


def sample():
    c = {k: 'value' for k in d.COLUMNS}
    c.update(chunk_id='B:'+'a'*64, document_id='doc', source='https://example.org/manual.pdf',
             physical_page=120, printed_page_label='82', text='Evidence text.', section='DDL',
             start_char=1, end_char=15, metadata={'source_id': 'doc', 'physical_page': 120},
             dataset_id=d.DATASET, profile_id=d.PROFILE, strategy='B', snapshot_id=d.SNAPSHOT,
             manifest_sha256=d.MANIFEST, corpus_sha256=d.CORPUS)
    return tuple(c[k] for k in d.COLUMNS) + (0.2,)


class DenseTests(unittest.TestCase):
    def setUp(self):
        self.encoder = MagicMock(profile_id=d.PROFILE)
        self.encoder.embed_query.return_value = [1.0] + [0.0]*383
        self.config = SimpleNamespace(statement_timeout_ms=10000)
        self.connect = MagicMock()
        self.conn = self.connect.return_value
        self.cur = self.conn.cursor.return_value.__enter__.return_value
        self.cur.fetchone.side_effect = [('day6_lab', 'day6', 'on'),
            ('complete',264,264,40,d.MANIFEST,d.CORPUS),
            (self.encoder.profile.config_canonical,), (264,40,384,384)]
        self.cur.fetchall.return_value = [sample()]
        self.retriever = d.DenseRetriever(self.config, self.encoder, connect=self.connect)
        self.dsn_patch = patch.object(d, 'read_dsn', return_value='redacted-test-placeholder')
        self.dsn_patch.start()
        self.addCleanup(self.dsn_patch.stop)

    def test_mapping_and_original_metadata(self):
        row = sample()
        original = copy.deepcopy(row)
        hit = d.map_chunk(row,1)
        self.assertEqual(row, original)
        self.assertEqual((hit['id'],hit['source_id'],hit['page']), ('B:'+'a'*64,'doc',120))
        self.assertEqual(hit['printed_page_label'],'82')
        self.assertEqual(hit['citation']['physical_page'],120)
        self.assertEqual(hit['start_char'],1)
        self.assertAlmostEqual(hit['score'],0.8)

    def test_context_budget_and_page_labels(self):
        hit = d.map_chunk(sample(),1)
        text, ids = d.pack_dense_context([hit,hit],1000)
        self.assertIn('physical 120; printed 82',text)
        self.assertEqual(ids,[hit['id']])
        self.assertEqual(d.pack_dense_context([hit],1),('',[]))

    def test_real_contract_and_readonly_cleanup(self):
        hits = self.retriever.search('What is a constraint?',filters=None,top_k=1)
        self.assertEqual(len(hits),1)
        self.encoder.embed_query.assert_called_once_with('What is a constraint?')
        self.assertIn('default_transaction_read_only=on',self.connect.call_args.kwargs['options'])
        self.conn.rollback.assert_called_once()
        self.conn.close.assert_called_once()
        sql, params = self.cur.execute.call_args.args
        self.assertIn('embedding <=>',sql)
        self.assertEqual(params[1:5],d.NAMESPACE)
        self.assertEqual(params[-1],1)

    def test_empty_query_invalid_topk_and_filter_fail_before_encode(self):
        for query,k,filters in [('',3,None),(' ',3,None),('a\x00',3,None),('q',0,None),
                                 ('q',True,None),('q',265,None),('q',3,{'gold':'secret'}),
                                 ('q',3,{'section':''}),('q',3,[])]:
            with self.subTest(query=query,k=k,filters=filters),self.assertRaises(d.RetrievalError):
                self.retriever.search(query,filters=filters,top_k=k)
        self.encoder.embed_query.assert_not_called()
        self.connect.assert_not_called()

    def test_vector_validation(self):
        for vector in [[0]*384,[1]*383,[float('nan')]*384,[True]+[0]*383]:
            with self.assertRaises(d.RetrievalError): d.validate_vector(vector)

    def test_bad_target_and_timeout_config(self):
        for value in [None,'postgresql://day6:secret@remote:55433/day6_lab',
                      'postgresql://day6:secret@127.0.0.1:55433/day6_lab?options=x']:
            with self.assertRaises(d.RetrievalError) as error:d.validate_dsn(value)
            self.assertNotIn('secret',str(error.exception))
        with self.assertRaises(d.RetrievalError):d.Config(Path('.'),0)

    def test_snapshot_mismatch(self):
        self.cur.fetchone.side_effect=[('day6_lab','day6','on'),('complete',246,246,40,d.MANIFEST,d.CORPUS)]
        with self.assertRaisesRegex(d.RetrievalError,'SNAPSHOT_MISMATCH'):
            self.retriever.search('q',filters=None,top_k=3)
        self.assertEqual(self.cur.execute.call_count,3)
        self.conn.rollback.assert_called_once()

    def test_profile_mismatch(self):
        self.cur.fetchone.side_effect=[('day6_lab','day6','on'),
            ('complete',264,264,40,d.MANIFEST,d.CORPUS),('wrong-profile',)]
        with self.assertRaisesRegex(d.RetrievalError,'DATABASE_PROFILE_MISMATCH'):
            self.retriever.search('q',filters=None,top_k=3)

    def test_chunk_provenance_mismatch(self):
        row=list(sample());row[d.COLUMNS.index('strategy')]='A'
        with self.assertRaisesRegex(d.RetrievalError,'CHUNK_PROVENANCE_MISMATCH'):d.map_chunk(row,1)

    def test_database_error_and_timeout_are_sanitized(self):
        for state,expected in [('57014','DATABASE_TIMEOUT'),('08006','DATABASE_ERROR')]:
            error=RuntimeError('password=do-not-log')
            error.sqlstate=state
            self.connect.side_effect=error
            with self.assertRaisesRegex(d.RetrievalError,expected) as caught:
                self.retriever.search('q',filters=None,top_k=3)
            self.assertNotIn('do-not-log',str(caught.exception))
            self.assertEqual(self.retriever.last_trace['error'],expected)

    def test_metadata_filter_is_bound_parameter(self):
        self.retriever.search('q',filters={'section':"DDL' OR true --"},top_k=3)
        sql,params=self.cur.execute.call_args.args
        self.assertNotIn("DDL'",sql)
        self.assertEqual(params[-2],"DDL' OR true --")

    def test_model_profile_mismatch_before_connect(self):
        with self.assertRaisesRegex(d.RetrievalError,'EMBEDDING_PROFILE_MISMATCH'):
            d.DenseRetriever(self.config,SimpleNamespace(profile_id='other'),connect=self.connect)
        self.connect.assert_not_called()

    def test_env_reads_only_database_entry_without_mutating_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'starter').mkdir()
            (root/'starter/.env').write_text(
                'DATABASE_URL=postgresql://day6:synthetic@127.0.0.1:55433/day6_lab\n'
                'OPENAI_API_KEY=synthetic-unused\n',encoding='utf-8')
            before=dict(os.environ)
            # setUp patches read_dsn for DB doubles; exercise the original function here.
            self.dsn_patch.stop()
            value=d.read_dsn(SimpleNamespace(day6_root=root))
            self.assertEqual(d.validate_dsn(value),value)
            self.assertEqual(dict(os.environ),before)


if __name__ == '__main__':unittest.main()
