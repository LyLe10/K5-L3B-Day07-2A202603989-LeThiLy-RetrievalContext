"""Offline dataset integrity checks; no retrieval/model/database operations."""
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from src import dense as d


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode())


def load_offline_snapshot(root):
    """Verify Day 06 artifact against pinned manifest/corpus/snapshot identities."""
    root=Path(root)
    manifest_raw=(root/'data/manifest.json').read_bytes()
    if sha(manifest_raw)!=d.MANIFEST:raise ValueError('MANIFEST_HASH_MISMATCH')
    manifest=json.loads(manifest_raw)
    artifact=root/'data/local/stage3/chunks/B.jsonl'
    artifact_raw=artifact.read_bytes()
    rows=[json.loads(line) for line in artifact_raw.decode('utf-8').splitlines() if line.strip()]
    if len(rows)!=264 or len({r['chunk_id'] for r in rows})!=264:raise ValueError('B_CHUNK_COUNT_MISMATCH')
    sources={s['source_id']:s for s in manifest['sources']}
    pages={}
    for source in sources.values():
        # Existing public source bytes are verified, never extracted or modified.
        if sha((root/source['local_path']).read_bytes())!=source['sha256']:
            raise ValueError('PDF_HASH_MISMATCH')
        for page in source['pages']:
            if page['included']:
                text=(root/page['text_path']).read_bytes()
                if (sha(text)!=page['text_sha256'] or page['extraction_status']!='ok'
                        or page['review_status']!='approved'):
                    raise ValueError('PAGE_HASH_OR_REVIEW_MISMATCH')
                pages[page['page_id']]=dict(record=page,text=text.decode('utf-8'),source=source)
    if len(pages)!=40:raise ValueError('PAGE_COUNT_MISMATCH')
    chunks=[];page_metadata={};coverage={pid:[] for pid in pages}
    for row in rows:
        m=row['metadata'];p=pages[m['page_id']];record=p['record'];source=p['source'];trace=m['_chunking']
        start,end=trace['start_char'],trace['end_char']
        if (not row['chunk_id'].startswith('B:') or trace['strategy']!='B'
                or row['document_id']!=source['source_id'] or row['source']!=source['source_path_or_url']
                or type(row['page']) is not int or row['page']!=record['physical_page']
                or m['physical_page']!=row['page'] or m['printed_page_label']!=record['printed_page_label']
                or m['source_id']!=row['document_id'] or m['text_sha256']!=record['text_sha256']
                or row['text']!=p['text'][start:end]):
            raise ValueError('CHUNK_PAGE_PROVENANCE_MISMATCH')
        metadata={k:v for k,v in m.items() if k!='_chunking'}
        if m['page_id'] in page_metadata and page_metadata[m['page_id']]!=metadata:
            raise ValueError('PAGE_METADATA_CONFLICT')
        page_metadata[m['page_id']]=metadata;coverage[m['page_id']].append((start,end))
        chunks.append(dict(row,id=row['chunk_id'],source_id=row['document_id'],
            physical_page=row['page'],printed_page_label=m['printed_page_label']))
    for pid,spans in coverage.items():
        cursor=0
        for start,end in sorted(spans):
            if start!=cursor or end<=start:raise ValueError('B_PAGE_COVERAGE_GAP_OR_OVERLAP')
            cursor=end
        if cursor!=len(pages[pid]['text']):raise ValueError('B_PAGE_COVERAGE_INCOMPLETE')
    corpus_descriptor=[dict(document_id=p['source']['source_id'],source=p['source']['source_path_or_url'],
        physical_page=p['record']['physical_page'],source_sha256=p['source']['sha256'],metadata=page_metadata[pid])
        for pid,p in sorted(pages.items())]
    corpus_hash=digest(corpus_descriptor)
    chunk_hash=digest([dict(chunk_id=r['chunk_id'],text_sha256=sha(r['text'].encode()),metadata=r['metadata'])
                       for r in sorted(rows,key=lambda r:r['chunk_id'])])
    snapshot_hash=digest(dict(namespace=[d.DATASET,d.PROFILE,'B'],manifest_sha256=d.MANIFEST,
        corpus_sha256=corpus_hash,chunkset_sha256=chunk_hash,selected_page_count=40,expected_count=264))
    if corpus_hash!=d.CORPUS or snapshot_hash!=d.SNAPSHOT:raise ValueError('OFFLINE_SNAPSHOT_IDENTITY_MISMATCH')
    return chunks,pages,dict(dataset_id=d.DATASET,profile_id=d.PROFILE,snapshot_id=snapshot_hash,
        manifest_sha256=d.MANIFEST,corpus_sha256=corpus_hash,chunkset_sha256=chunk_hash,
        chunk_artifact_sha256=sha(artifact_raw),chunk_count=264,page_count=40)


def absence_scan(pages,terms):
    """Exhaustive full-page text scan, not top-k search or semantic proof."""
    return {term:[pid for pid,p in sorted(pages.items()) if term.casefold() in p['text'].casefold()]
            for term in terms}


def normalized_question(text):
    return ' '.join(re.findall(r'\w+',unicodedata.normalize('NFC',text).casefold()))


def validate_dataset(dev,test,chunks,pages,identity):
    errors=[];pending=[];accepted=[];audit=[];seen=set();questions=set();gold_ids={'dev':set(),'test':set()}
    by_id={c['id']:c for c in chunks}
    for split,cases,counts in [('dev',dev,(15,2)),('test',test,(5,2))]:
        if not isinstance(cases,list):raise ValueError('SPLIT_MUST_BE_ARRAY')
        if any(not isinstance(c,dict) for c in cases):raise ValueError('CASE_MUST_BE_OBJECT')
        if (len(cases)!=sum(counts) or sum(c.get('answerable') is True for c in cases)!=counts[0]
                or sum(c.get('answerable') is False for c in cases)!=counts[1]):
            errors.append(dict(split=split,error='SPLIT_COUNTS_INVALID'))
        for case in cases:
            cid=case.get('id');case_errors=[]
            if not isinstance(cid,str) or not re.fullmatch(split+r'-\d{2}',cid) or cid in seen:
                case_errors.append('CASE_ID_INVALID_OR_DUPLICATE')
            if isinstance(cid,str):seen.add(cid)
            question=case.get('question')
            if not isinstance(question,str) or not question.strip():case_errors.append('QUESTION_REQUIRED')
            else:
                key=normalized_question(question)
                if key in questions:case_errors.append('DUPLICATE_QUESTION_ACROSS_SPLITS')
                questions.add(key)
            if case.get('split')!=split or type(case.get('answerable')) is not bool:
                case_errors.append('SPLIT_OR_ANSWERABLE_INVALID')
            if case.get('snapshot_id')!=identity['snapshot_id']:case_errors.append('CASE_SNAPSHOT_MISMATCH')
            if case.get('answerable') is True:
                if not isinstance(case.get('expected_answer'),str) or not case['expected_answer'].strip():
                    case_errors.append('EXPECTED_ANSWER_REQUIRED')
                gold=case.get('gold')
                if not isinstance(gold,list) or not gold:case_errors.append('GOLD_REQUIRED');gold=[]
                local=set()
                for g in gold:
                    c=by_id.get(g.get('chunk_id')) if isinstance(g,dict) else None
                    if c is None:case_errors.append('UNKNOWN_GOLD_CHUNK');continue
                    gold_ids[split].add(c['id'])
                    if c['id'] in local:case_errors.append('DUPLICATE_GOLD')
                    local.add(c['id'])
                    if any(g.get(k)!=c[k] for k in ('source_id','source','page','physical_page','printed_page_label')):
                        case_errors.append('GOLD_SOURCE_OR_PAGE_MISMATCH')
                    if type(g.get('page')) is not int or type(g.get('physical_page')) is not int:
                        case_errors.append('GOLD_PAGE_MUST_BE_INTEGER')
                    quote=g.get('evidence')
                    if not isinstance(quote,str) or not quote.strip() or quote not in c['text']:
                        case_errors.append('GOLD_QUOTE_NOT_IN_CHUNK')
                    review=case.get('gold_review',{})
                    if (not isinstance(review,dict) or review.get('status')!='ASSISTANT_REVIEWED' or not review.get('support_rationale')
                            or review.get('evidence_sha256')!=sha(c['text'].encode())):
                        case_errors.append('GOLD_SUPPORT_REVIEW_REQUIRED')
                if case_errors:errors.append(dict(id=cid,errors=case_errors))
                audit.append(dict(id=cid,split=split,exact_evidence='FAIL' if case_errors else 'PASS',
                    semantic_review='ASSISTANT_REVIEWED_NOT_INDEPENDENT_HUMAN',gold=gold))
            else:
                a=case.get('absence_review',{})
                if not isinstance(a,dict):a={}
                terms=a.get('terms',[])
                if (case.get('expected_behavior')!='search_and_abstain' or not case.get('absence_reason')
                        or case.get('gold') or not isinstance(terms,list) or not terms
                        or any(not isinstance(t,str) or not t.strip() for t in terms)):
                    case_errors.append('ABSENCE_SCHEMA_INVALID')
                else:
                    scan=absence_scan(pages,terms)
                    if (a.get('scope_snapshot_id')!=identity['snapshot_id'] or a.get('pages_reviewed')!=40
                            or a.get('chunks_reviewed')!=264 or a.get('term_matches')!=scan):
                        case_errors.append('ABSENCE_SCOPE_OR_SCAN_MISMATCH')
                    if any(scan.values()):case_errors.append('ABSENCE_TERMS_FOUND_REQUIRES_REVIEW')
                # ACCEPTED is explicit review metadata, never inferred from scan.
                # CLI also verifies the approval record bound to this snapshot.
                if a.get('status')=='ACCEPTED':
                    accepted.append(dict(id=cid,split=split,status='ACCEPTED'))
                elif a.get('status')=='PENDING_REVIEW':
                    pending.append(dict(id=cid,split=split,status='PENDING_REVIEW',
                        action='Human must verify full-corpus semantic absence; zero keyword matches are not proof.'))
                else:case_errors.append('ABSENCE_NOT_INDEPENDENTLY_VERIFIED')
                if case_errors:errors.append(dict(id=cid,errors=case_errors))
    overlap=gold_ids['dev']&gold_ids['test']
    if overlap:errors.append(dict(error='GOLD_CHUNK_OVERLAP_BETWEEN_SPLITS',chunk_ids=sorted(overlap)))
    return dict(status='FAIL' if errors else 'PENDING_REVIEW' if pending else 'PASS',
        schema_and_integrity='FAIL' if errors else 'PASS',identity=identity,errors=errors,
        counts=dict(dev=len(dev),test=len(test),answerable_gold_cases=len(audit),pending_absence=len(pending),
                    accepted_absence=len(accepted)),
        gold_audit=audit,pending_review=pending,accepted_review=accepted,
        ready_for_milestone5b=not errors and not pending and len(accepted)==4,
        retrieval_benchmark_run=False,llm_calls=0)


def validate_absence_approval(dev,test,manifest,identity):
    """Bind ACCEPTED metadata to the user's exact four-case snapshot approval."""
    accepted={c['id'] for c in dev+test if c.get('absence_review',{}).get('status')=='ACCEPTED'}
    if not accepted:return []
    record=manifest.get('absence_approval',{})
    expected={'dev-16','dev-17','test-06','test-07'}
    if (accepted!=expected or not isinstance(record,dict)
            or record.get('case_ids')!=sorted(expected) or record.get('decision')!='ACCEPTED'
            or record.get('approved_by')!='user' or record.get('basis')!='explicit_user_approval_in_conversation'
            or record.get('snapshot_id')!=identity['snapshot_id'] or identity['snapshot_id']!=d.SNAPSHOT
            or record.get('chunk_count')!=264
            or record.get('physical_pages')!=list(range(97,133))+list(range(148,152))
            or manifest.get('review_status')!='ACCEPTED'):
        return [dict(error='ABSENCE_APPROVAL_RECORD_MISMATCH')]
    return []
