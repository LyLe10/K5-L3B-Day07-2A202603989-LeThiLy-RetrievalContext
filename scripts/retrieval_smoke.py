"""Three methods on Milestone 2 technical queries, never benchmark/gold."""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.dense_smoke import QUERIES, database_fingerprint
from scripts.check_day6_files import inventory
from src import dense as d
from src.retrieval import LexicalRetriever, create_retriever, load_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--day6-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    files_before = inventory(args.day6_root)
    dense = d.DenseRetriever(d.Config(args.day6_root), d.load_embedder(d.Config(args.day6_root)))
    before = database_fingerprint(dense)
    started = perf_counter()
    chunks = load_snapshot(dense)
    lexical = LexicalRetriever(chunks)
    index_ms = (perf_counter()-started)*1000
    traces = []
    for method in ('dense','lexical','hybrid'):
        retriever = create_retriever(method,dense,lexical=lexical)
        for query in QUERIES:
            hits = retriever.search(query,filters=None,top_k=3)
            assert len({c['id'] for c in hits}) == len(hits)
            context, ids = d.pack_dense_context(hits,budget=2400)
            trace = dict(retriever.last_trace, method=method,context=context,context_ids=ids,context_budget_chars=2400)
            assert hits == retriever.search(query,filters=None,top_k=3)
            traces.append(trace)
        assert retriever.search(QUERIES[0],filters={'section':'__smoke_nonexistent_section__'},top_k=3)==[]
    after = database_fingerprint(dense)
    assert before == after
    files_after = inventory(args.day6_root)
    changed = sorted(k for k in files_before.keys() | files_after.keys() if files_before.get(k)!=files_after.get(k))
    assert not changed
    # Post-retrieval coverage inspection only. Never passed to retrievers.
    coverage = [dict(id=c['id'],text=c['text'],page=c['page'],printed_page_label=c['printed_page_label'])
                for c in chunks if 'check constraint is satisfied' in c['text'].casefold() or 'on conflict' in c['text'].casefold()]
    report = dict(kind='smoke_not_benchmark',status='PASS',queries=traces,index_load_build_ms=index_ms,
        database_before=before,database_after=after,day6_files_checked=len(files_before),changed_paths=changed,
        filesystem_exclusions=['.venv','venv','pip-cache','.git','.pytest_cache','__pycache__'],
        coverage_review_after_retrieval=coverage,llm_calls=0,corpus_encoding_calls=0,service_cost_usd=0,
        config=dict(snapshot=d.SNAPSHOT,rrf_k=60,candidate_k=20,top_k=3))
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='PASS',queries=len(traces),files_checked=len(files_before))))


if __name__=='__main__':
    try: main()
    except d.RetrievalError as error:
        print(json.dumps(dict(status='ERROR',error=str(error))))
        sys.exit(1)
