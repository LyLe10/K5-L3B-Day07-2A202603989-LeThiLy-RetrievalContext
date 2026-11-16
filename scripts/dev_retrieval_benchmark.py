"""DEV-only retrieval comparison. No LLM calls, requests or TEST execution."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src import dense as d
from src.context import pack_context
from src.retrieval import LexicalRetriever, create_retriever, load_snapshot, validate_search
from starter.baseline import hit
from scripts.milestone4b_smoke import ByteBudget
from scripts.dense_smoke import database_fingerprint


def validate_dev(cases,chunks):
    """Single-evidence alternatives only; no inferred gold or held-out split."""
    if not isinstance(cases,list) or not cases:
        raise ValueError('DEV_CASES_REQUIRED')
    known={c['id']:c for c in chunks}
    seen,questions=set(),set()
    for case in cases:
        if not isinstance(case,dict) or case.get('split')!='dev':
            raise ValueError('DEV_ONLY_FILE_REQUIRED')
        cid=case.get('id')
        if not isinstance(cid,str) or not cid.strip() or cid in seen:
            raise ValueError('INVALID_OR_DUPLICATE_CASE_ID')
        seen.add(cid)
        validate_search(case.get('question'),case.get('filter'),3)
        normalized=' '.join(case['question'].casefold().split())
        if normalized in questions:raise ValueError('DUPLICATE_QUESTION')
        questions.add(normalized)
        if type(case.get('answerable')) is not bool:
            raise ValueError('ANSWERABLE_BOOLEAN_REQUIRED')
        if 'evidence_sets' in case:
            raise ValueError('MULTIHOP_NEEDS_EXPLICIT_SCORER')
        if case['answerable']:
            if not isinstance(case.get('expected_answer'),str) or not case['expected_answer'].strip():
                raise ValueError('EXPECTED_ANSWER_REQUIRED')
            gold=case.get('gold')
            if not isinstance(gold,list) or not gold:raise ValueError('REAL_GOLD_REQUIRED')
            for evidence in gold:
                if not isinstance(evidence,dict):raise ValueError('INVALID_GOLD')
                chunk=known.get(evidence.get('chunk_id'))
                if (not all(k in evidence for k in ('source_id','page','evidence'))
                        or chunk is None or not isinstance(evidence.get('evidence'),str)
                        or not evidence['evidence'].strip() or not hit(chunk,[evidence])):
                    raise ValueError('GOLD_NOT_IN_REAL_CHUNK_SOURCE_PAGE')
                if any(k in evidence and evidence[k]!=chunk.get(k)
                       for k in ('source','physical_page','printed_page_label')):
                    raise ValueError('GOLD_SOURCE_OR_PRINTED_PAGE_MISMATCH')
        elif (case.get('expected_behavior')!='search_and_abstain'
                or not isinstance(case.get('absence_reason'),str) or not case['absence_reason'].strip()
                or case.get('gold')):
            raise ValueError('UNANSWERABLE_COVERAGE_REVIEW_REQUIRED')
    answerable=sum(c['answerable'] for c in cases)
    if answerable<15 or len(cases)-answerable<2:
        raise ValueError('DEV_REQUIRES_15_ANSWERABLE_PLUS_2_UNANSWERABLE')


def evaluate_dev(cases,chunks,retrievers,*,budget=12000):
    validate_dev(cases,chunks)
    if type(budget) is not int or budget<1:raise ValueError('INVALID_CONTEXT_BUDGET')
    traces=[]
    for method,retriever in retrievers.items():
        for case in cases:
            started=perf_counter()
            trace=dict(query_id=case['id'],question=case['question'],split='dev',method=method,
                answerable=case['answerable'],status='ok',hit1=None,hit3=None,context_hit=None)
            try:
                # Only question + declared user filter enter retrieval. No gold.
                results=retriever.search(case['question'],filters=case.get('filter'),top_k=3)
                if len(results)>3 or len({c['id'] for c in results})!=len(results):
                    raise ValueError('INVALID_RETRIEVER_RESULTS')
                results=[dict(c,rank=rank,gold_match=(hit(c,case['gold']) if case['answerable'] else None))
                         for rank,c in enumerate(results,1)]
                packed=pack_context(results,budget,ByteBudget())
                trace.update(results=results,**packed)
                if case['answerable']:
                    # Score the actual text sent, not just candidate ID membership.
                    selected=json.loads(packed['context']) if packed['context'] else []
                    trace.update(hit1=bool(results and hit(results[0],case['gold'])),
                        hit3=any(hit(c,case['gold']) for c in results),
                        context_hit=any(hit(c,case['gold']) for c in selected))
            except Exception as error:
                trace.update(status='error',error=('RETRIEVAL_TIMEOUT' if isinstance(error,TimeoutError)
                    or (isinstance(error,d.RetrievalError) and str(error)=='DATABASE_TIMEOUT') else 'RETRIEVAL_OR_CONTEXT_ERROR'))
            trace['elapsed_ms']=(perf_counter()-started)*1000
            traces.append(trace)
    summaries={}
    for method in retrievers:
        selected=[t for t in traces if t['method']==method]
        denominator=sum(t['answerable'] for t in selected)
        summaries[method]=dict(cases=len(selected),errors=sum(t['status']=='error' for t in selected))
        for label,field in [('Hit@1','hit1'),('Evidence Hit@3','hit3'),('Context Evidence Rate','context_hit')]:
            numerator=sum(t['answerable'] and t[field] is True for t in selected)
            # Fixed answerable denominator; errors are visible and cannot inflate rates.
            summaries[method][label]=dict(n=numerator,N=denominator,rate=numerator/denominator)
    return dict(kind='dev_retrieval_only_not_agent_evaluation',split='dev',llm_calls=0,
        config=dict(top_k=3,context_budget=budget,context_budget_unit=ByteBudget.name),
        summary=summaries,traces=traces)


def load_frozen_dev(path):
    """Hash TEST bytes for freeze integrity only; never parse its questions/gold."""
    directory=path.parent
    manifest_raw=(directory/'manifest.json').read_bytes()
    manifest=json.loads(manifest_raw)
    sha=lambda raw:hashlib.sha256(raw).hexdigest()
    if (directory/'manifest.sha256').read_text(encoding='utf-8').split()!=[sha(manifest_raw),'manifest.json']:
        raise ValueError('FROZEN_MANIFEST_PIN_MISMATCH')
    hashes={name:sha((directory/name).read_bytes()) for name in ('dev.json','test.json')}
    if hashes!=manifest['files_sha256'] or manifest.get('review_status')!='ACCEPTED':
        raise ValueError('FROZEN_DATASET_HASH_OR_REVIEW_MISMATCH')
    if path.name!='dev.json':raise ValueError('FROZEN_DEV_FILE_REQUIRED')
    raw=path.read_bytes();cases=json.loads(raw)
    if not isinstance(cases,list) or any(not isinstance(c,dict) or c.get('split')!='dev' for c in cases):
        raise ValueError('DEV_ONLY_FILE_REQUIRED')
    return raw,cases,dict(manifest_sha256=sha(manifest_raw),files_sha256=hashes,
        manifest_pin_sha256=sha((directory/'manifest.sha256').read_bytes()),
        identity=manifest['identity'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dev',type=Path,required=True,help='Curated DEV-only JSON; never a TEST file')
    parser.add_argument('--day6-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Output exists; preserve evidence')
    raw,cases,frozen=load_frozen_dev(args.dev)
    if (frozen['identity']['snapshot_id']!=d.SNAPSHOT or frozen['identity']['profile_id']!=d.PROFILE
            or frozen['identity']['corpus_sha256']!=d.CORPUS):
        raise ValueError('FROZEN_SNAPSHOT_IDENTITY_MISMATCH')
    config=d.Config(args.day6_root)
    dense=d.DenseRetriever(config,d.load_embedder(config))
    before=database_fingerprint(dense)
    try:
        chunks=load_snapshot(dense)
        validate_dev(cases,chunks)  # fail integrity before any search
        lexical=LexicalRetriever(chunks)
        retrievers={m:create_retriever(m,dense,lexical=lexical) for m in ('dense','lexical','hybrid')}
        report=evaluate_dev(cases,chunks,retrievers)
        report.update(snapshot_id=d.SNAPSHOT,profile_id=d.PROFILE,corpus_sha256=d.CORPUS,
            dev_sha256=hashlib.sha256(raw).hexdigest(),snapshot_chunks=len(chunks),
            fusion=dict(rrf_k=60,candidate_k=20),database_before=before)
        report.update(preflight=dict(status='PASS',snapshot_chunks=len(chunks),read_only=True,
            frozen=frozen,gold_integrity='PASS'),embedding_model=d.MODEL,embedding_revision=d.REVISION,
            embedding_runtime=dense.embedder.runtime)
    finally:
        after=database_fingerprint(dense)
    report.update(database_after=after,database_unchanged=before==after)
    if before!=after:raise RuntimeError('DATABASE_CONTENT_CHANGED')
    after_raw,_,after_frozen=load_frozen_dev(args.dev)
    if after_raw!=raw or after_frozen!=frozen:raise RuntimeError('DATASET_CHANGED_DURING_RUN')
    report['dataset_unchanged']=True
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps(dict(output=str(args.output),llm_calls=0,summary=report['summary'])))


if __name__=='__main__':main()
