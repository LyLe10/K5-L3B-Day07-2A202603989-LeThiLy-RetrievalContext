import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.benchmark_data import validate_dataset,validate_absence_approval,absence_scan,sha
from src import dense as d


def fixture():
    # Synthetic unit data; not a source of PostgreSQL benchmark evidence.
    identity=dict(snapshot_id='unit-snapshot')
    pages={f'p{i:04}':dict(text='Unit page content') for i in range(40)}
    chunks=[dict(id=f'unit-{i}',text=f'Unit evidence number {i}.',source_id='unit-doc',source='unit.pdf',
        page=i+1,physical_page=i+1,printed_page_label=str(i+1)) for i in range(20)]
    splits={};offset=0
    for split,count in [('dev',15),('test',5)]:
        rows=[]
        for i in range(count):
            c=chunks[offset+i]
            gold={k:c[k] for k in ('source_id','source','page','physical_page','printed_page_label')}
            gold.update(chunk_id=c['id'],evidence=c['text'])
            rows.append(dict(id=f'{split}-{i+1:02}',split=split,answerable=True,question=f'Unit question {offset+i}',
                snapshot_id='unit-snapshot',expected_answer='Unit answer',gold=[gold],
                gold_review=dict(status='ASSISTANT_REVIEWED',support_rationale='Unit rationale',
                    evidence_sha256=sha(c['text'].encode()))))
        offset+=count
        for i in range(2):
            rows.append(dict(id=f'{split}-{count+i+1:02}',split=split,answerable=False,
                question=f'Absent unit question {split} {i}',snapshot_id='unit-snapshot',
                expected_behavior='search_and_abstain',absence_reason='Unit scope limitation',
                absence_review=dict(status='PENDING_REVIEW',scope_snapshot_id='unit-snapshot',
                    pages_reviewed=40,chunks_reviewed=264,terms=['missing-term'],term_matches={'missing-term':[]})))
        splits[split]=rows
    return splits['dev'],splits['test'],chunks,pages,identity


class BenchmarkDatasetTests(unittest.TestCase):
    def test_dev_runner_cannot_overwrite_dataset(self):
        from scripts import dev_retrieval_benchmark as runner
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'dev.json';path.write_text('[]',encoding='utf-8')
            before=path.read_bytes()
            with patch('sys.argv',['dev','--dev',str(path),'--day6-root',directory,'--output',str(path)]), \
                    patch.object(runner.d,'load_embedder') as embedder:
                with self.assertRaises(SystemExit):runner.main()
                embedder.assert_not_called()
            self.assertEqual(path.read_bytes(),before)

    def test_accepted_reviews_require_exact_snapshot_approval_record(self):
        args=fixture()
        for rows in args[:2]:
            for c in rows:
                c['snapshot_id']=d.SNAPSHOT
                if not c['answerable']:
                    c['absence_review'].update(status='ACCEPTED',scope_snapshot_id=d.SNAPSHOT)
        args[4]['snapshot_id']=d.SNAPSHOT
        result=validate_dataset(*args)
        self.assertEqual(result['status'],'PASS')
        self.assertTrue(result['ready_for_milestone5b'])
        self.assertEqual(result['counts']['accepted_absence'],4)
        record=dict(case_ids=['dev-16','dev-17','test-06','test-07'],decision='ACCEPTED',approved_by='user',
            basis='explicit_user_approval_in_conversation',snapshot_id=d.SNAPSHOT,chunk_count=264,
            physical_pages=list(range(97,133))+list(range(148,152)))
        manifest=dict(review_status='ACCEPTED',absence_approval=record)
        self.assertEqual(validate_absence_approval(args[0],args[1],manifest,args[4]),[])
        self.assertTrue(validate_absence_approval(args[0],args[1],{},args[4]))
        for key,value in [('snapshot_id','wrong'),('approved_by','assistant'),('chunk_count',3),('case_ids',['dev-16'])]:
            invalid=copy.deepcopy(manifest);invalid['absence_approval'][key]=value
            self.assertTrue(validate_absence_approval(args[0],args[1],invalid,args[4]))

    def test_valid_structure_never_promotes_pending_absence_to_pass(self):
        args=fixture();before=copy.deepcopy(args)
        r=validate_dataset(*args)
        self.assertEqual(r['schema_and_integrity'],'PASS')
        self.assertEqual(r['status'],'PENDING_REVIEW')
        self.assertEqual((r['counts']['answerable_gold_cases'],len(r['pending_review'])),(20,4))
        self.assertFalse(r['ready_for_milestone5b'])
        self.assertEqual(args,before)

    def test_gold_id_source_page_printed_page_and_quote_tampering(self):
        for field,value in [('chunk_id','invented'),('source','wrong.pdf'),('source_id','wrong'),
                ('page',999),('physical_page',999),('printed_page_label','999'),('evidence','invented quote')]:
            args=fixture();args[0][0]['gold'][0][field]=value
            self.assertEqual(validate_dataset(*args)['status'],'FAIL',field)

    def test_counts_ids_duplicates_across_splits(self):
        args=fixture();args[0].pop()
        self.assertEqual(validate_dataset(*args)['status'],'FAIL')
        args=fixture();args[1][0]['id']='dev-01'
        self.assertEqual(validate_dataset(*args)['status'],'FAIL')
        args=fixture();args[1][0]['question']='  UNIT question 0?'
        self.assertEqual(validate_dataset(*args)['status'],'FAIL')

    def test_false_absence_scope_and_claimed_pass_fail(self):
        for field,value in [('status','PASS'),('chunks_reviewed',3),('pages_reviewed',1),
                ('scope_snapshot_id','wrong'),('term_matches',{'missing-term':['p0001']})]:
            args=fixture();args[0][-1]['absence_review'][field]=value
            self.assertEqual(validate_dataset(*args)['status'],'FAIL',field)

    def test_full_page_scan_finds_terms_and_does_not_use_topk(self):
        args=fixture();args[3]['p0039']['text']='Late page has MISSING-TERM.'
        self.assertEqual(absence_scan(args[3],['missing-term']),{'missing-term':['p0039']})
        for split in args[:2]:
            for c in split:
                if not c['answerable']:
                    c['absence_review']['term_matches']={'missing-term':['p0039']}
        self.assertEqual(validate_dataset(*args)['status'],'FAIL')

    def test_gold_overlap_and_invalid_schema_rejected(self):
        args=fixture();args[1][0]['gold']=copy.deepcopy(args[0][0]['gold'])
        self.assertTrue(any(e.get('error')=='GOLD_CHUNK_OVERLAP_BETWEEN_SPLITS' for e in validate_dataset(*args)['errors']))
        args=fixture();args[0][0]='not object'
        with self.assertRaises(ValueError):validate_dataset(*args)
