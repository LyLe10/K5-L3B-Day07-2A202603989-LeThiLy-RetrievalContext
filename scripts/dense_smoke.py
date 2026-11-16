"""Opt-in live integration + technical smoke queries. Never reads benchmark/gold."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
from time import perf_counter
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import dense as d

# Authored from general PostgreSQL topics, independent of benchmark questions/evidence.
QUERIES = [
    'What does a foreign key constraint require of values in the referencing table?',
    'How does INSERT ON CONFLICT DO UPDATE handle a conflicting row?',
    'How does a CHECK constraint treat a null result?',
]


def database_fingerprint(retriever):
    result = {}
    with retriever.transaction() as conn:
        with conn.cursor() as cur:
            for table, order in [('chunks','dataset_id,profile_id,strategy,chunk_id'),
                                 ('embedding_profiles','profile_id'),
                                 ('strategy_snapshots','dataset_id,profile_id,strategy'),
                                 ('schema_migrations','version')]:
                cur.execute("SELECT count(*),encode(sha256(convert_to(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY "
                            + order + "),''),'UTF8')),'hex') FROM day6_ingestion." + table + ' t')
                result[table] = cur.fetchone()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--day6-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    config = d.Config(args.day6_root)
    started = perf_counter()
    print('Verifying local model artifacts and pinned runtime...',flush=True)
    encoder = d.load_embedder(config)
    retriever = d.DenseRetriever(config,encoder)
    before = database_fingerprint(retriever)
    checks = []

    def check(name, action):
        action()
        checks.append(dict(name=name,status='PASS'))
        print(json.dumps(dict(check=name,status='PASS')),flush=True)

    def expect(code, action):
        try:action()
        except d.RetrievalError as error:
            assert str(error)==code, (str(error),code)
        else:raise AssertionError('Expected sanitized error '+code)

    def preflight():
        with retriever.transaction() as conn:retriever.preflight(conn)
    check('real_database_readonly_profile_snapshot_preflight',preflight)
    check('empty_query',lambda:expect('INVALID_QUERY',lambda:retriever.search(' ',filters=None,top_k=3)))
    check('invalid_config',lambda:expect('INVALID_STATEMENT_TIMEOUT',lambda:d.Config(args.day6_root,0)))

    def checksum_failure():
        module=importlib.import_module('_day6_dense_readonly.embeddings')
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'README.md').write_text('corrupted artifact')
            try:module.MyEmbedder(d.MODEL,snapshot_path=p)
            except module.EmbeddingError as error:assert 'checksum mismatch' in str(error)
            else:raise AssertionError('Corrupt model accepted')
    check('corrupt_model_checksum_rejected_before_loading',checksum_failure)

    def snapshot_mismatch():
        with patch.object(d,'NAMESPACE',(d.DATASET,d.PROFILE,'B','0'*64)):
            expect('SNAPSHOT_MISMATCH',lambda:retriever.search('PostgreSQL constraints',filters=None,top_k=1))
    check('real_snapshot_mismatch',snapshot_mismatch)

    def timeout():
        def operation():
            with retriever.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL statement_timeout='1ms'")
                    cur.execute('SELECT pg_catalog.pg_sleep(0.05)')
        expect('DATABASE_TIMEOUT',operation)
    check('real_database_timeout',timeout)

    def database_error():
        def operation():
            with retriever.transaction() as conn:
                with conn.cursor() as cur:cur.execute('SELECT missing_column FROM day6_ingestion.chunks LIMIT 1')
        expect('DATABASE_ERROR',operation)
    check('real_database_error_sanitized',database_error)

    def empty_results():
        assert retriever.search('PostgreSQL constraints',filters={'section':'__smoke_nonexistent_section__'},top_k=3)==[]
    check('real_empty_result_with_explicit_filter',empty_results)

    traces=[]
    for query in QUERIES:
        results=retriever.search(query,filters=None,top_k=3)
        assert len(results)==3 and len({c['id'] for c in results})==3
        assert all(c['strategy']=='B' and c['profile_id']==d.PROFILE and c['snapshot_id']==d.SNAPSHOT for c in results)
        context,ids=d.pack_dense_context(results,budget=2400)
        assert len(context)<=2400 and ids
        trace={**retriever.last_trace,'context':context,'context_ids':ids,'context_budget_chars':2400}
        traces.append(trace)
    checks.append(dict(name='three_real_dense_queries_top3_context_and_metadata',status='PASS'))

    def cache_and_topk():
        results=retriever.search(QUERIES[0],filters=None,top_k=1)
        assert len(results)==1 and retriever.last_trace['query_cache_hit']
        assert results[0]['id']==traces[0]['results'][0]['id']
    check('query_cache_and_top_k_one',cache_and_topk)
    after=database_fingerprint(retriever)
    assert before==after,'Database content changed during smoke test'
    checks.append(dict(name='all_day6_tables_content_fingerprints_unchanged',status='PASS'))
    report=dict(kind='integration_and_smoke_not_benchmark',status='PASS',checks=checks,
        model=d.MODEL,revision=d.REVISION,profile_id=d.PROFILE,snapshot_id=d.SNAPSHOT,
        model_runtime=encoder.runtime,embedding_stats=encoder.stats,
        database_before=before,database_after=after,queries=traces,
        elapsed_seconds=perf_counter()-started,service_cost_usd=0,
        llm_calls=0,corpus_encoding_calls=0)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='PASS',checks=len(checks),queries=len(traces),output=str(args.output))))


if __name__=='__main__':
    try:main()
    except d.RetrievalError as error:
        print(json.dumps(dict(status='ERROR',error=str(error))))
        sys.exit(1)
