import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch

from scripts.dev_retrieval_benchmark import evaluate_dev,validate_dev,load_frozen_dev
from scripts.milestone4b_paid_smoke import PaidController
from src.openrouter_paid import PaidBudget
from src.llm import PAID_MODEL
from src.agent import run_agent
from src.dense import RetrievalError

# Synthetic unit fixtures only; never used as the real PostgreSQL benchmark.
CHUNK=dict(id='synthetic',text='Synthetic evidence.',source_id='unit',source='unit.pdf',page=1,metadata={},score=.8)


def cases():
    return [dict(id=f'dev-{i}',split='dev',question=f'Synthetic unit question {i}',answerable=True,
        expected_answer='Synthetic evidence.',gold=[dict(chunk_id='synthetic',source_id='unit',page=1,
        evidence='Synthetic evidence.')]) for i in range(15)] + [
        dict(id=f'absent-{i}',split='dev',question=f'Synthetic absent question {i}',answerable=False,
             expected_behavior='search_and_abstain',absence_reason='Synthetic coverage review') for i in range(2)]


class DevReadinessTests(unittest.TestCase):
    def test_frozen_integrity_without_parsing_test_questions(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'dev.json').write_text(json.dumps([dict(split='dev')]))
            # Deliberately invalid JSON: held-out content must only be hashed.
            (root/'test.json').write_bytes(b'held-out opaque bytes')
            manifest=dict(review_status='ACCEPTED',identity={},files_sha256={
                name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                for name in ('dev.json','test.json')})
            (root/'manifest.json').write_text(json.dumps(manifest))
            digest=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest()
            (root/'manifest.sha256').write_text(digest+'  manifest.json\n')
            self.assertEqual(load_frozen_dev(root/'dev.json')[1],[dict(split='dev')])
            (root/'dev.json').write_text('[]')
            with self.assertRaisesRegex(ValueError,'FROZEN_DATASET_HASH'):
                load_frozen_dev(root/'dev.json')
            (root/'manifest.sha256').write_text('incorrect manifest.json')
            with self.assertRaisesRegex(ValueError,'FROZEN_MANIFEST_PIN'):
                load_frozen_dev(root/'dev.json')

    def test_gold_metadata_checked_before_search(self):
        r=MagicMock()
        for field in ('source','physical_page','printed_page_label'):
            rows=cases();rows[0]['gold'][0][field]='incorrect'
            with self.assertRaisesRegex(ValueError,'GOLD_SOURCE_OR_PRINTED_PAGE_MISMATCH'):
                evaluate_dev(rows,[CHUNK],dict(dense=r))
        r.search.assert_not_called()

    def test_three_methods_same_inputs_no_gold_in_retrieval_and_fixed_denominator(self):
        rows=cases();before=copy.deepcopy(rows)
        retrievers={m:MagicMock(spec=['search']) for m in ['dense','lexical','hybrid']}
        for r in retrievers.values():r.search.return_value=[CHUNK]
        result=evaluate_dev(rows,[CHUNK],retrievers)
        self.assertEqual(rows,before)
        for method,r in retrievers.items():
            for label in ['Hit@1','Evidence Hit@3','Context Evidence Rate']:
                self.assertEqual(result['summary'][method][label],dict(n=15,N=15,rate=1))
            self.assertEqual(r.search.call_count,17)
            for call,case in zip(r.search.call_args_list,rows):
                self.assertEqual(call.args,(case['question'],))
                self.assertEqual(call.kwargs,dict(filters=None,top_k=3))
        self.assertEqual(result['llm_calls'],0)
        self.assertEqual(result['traces'][0]['results'][0]['rank'],1)
        self.assertIs(result['traces'][0]['results'][0]['gold_match'],True)
        self.assertIsNone(result['traces'][15]['results'][0]['gold_match'])

    def test_context_rate_uses_packed_evidence_not_candidate_membership(self):
        r=MagicMock();r.search.return_value=[CHUNK]
        result=evaluate_dev(cases(),[CHUNK],dict(dense=r),budget=1)
        self.assertEqual(result['summary']['dense']['Hit@1']['n'],15)
        self.assertEqual(result['summary']['dense']['Context Evidence Rate']['n'],0)

    def test_errors_are_visible_not_removed_from_denominator(self):
        r=MagicMock();r.search.side_effect=RetrievalError('DATABASE_TIMEOUT')
        result=evaluate_dev(cases(),[CHUNK],dict(dense=r))
        self.assertEqual(result['summary']['dense']['errors'],17)
        self.assertEqual(result['summary']['dense']['Hit@1'],dict(n=0,N=15,rate=0))
        self.assertEqual(result['traces'][0]['error'],'RETRIEVAL_TIMEOUT')

    def test_reject_test_or_unresolved_gold_before_retrieval(self):
        r=MagicMock()
        for changes in [dict(split='test'),dict(gold=[dict(chunk_id='invented',source_id='unit',page=1,evidence='Synthetic')]),
                dict(gold=[dict(chunk_id='synthetic',source_id='unit',page=99,evidence='Synthetic')]),
                dict(gold=[dict(chunk_id='synthetic',source_id='unit',page=1,evidence='invented quote')])]:
            rows=cases();rows[0].update(changes)
            with self.assertRaises(ValueError):evaluate_dev(rows,[CHUNK],dict(dense=r))
        r.search.assert_not_called()

    def test_minimum_counts_absence_review_and_duplicates(self):
        with self.assertRaises(ValueError):validate_dev(cases()[:-1],[CHUNK])
        rows=cases();rows[-1]['absence_reason']=''
        with self.assertRaises(ValueError):validate_dev(rows,[CHUNK])
        rows=cases();rows[1]['question']=rows[0]['question']
        with self.assertRaises(ValueError):validate_dev(rows,[CHUNK])

    @patch.dict(os.environ,{'OPENROUTER_API_KEY':'mock'})
    @patch('src.llm.build_opener')
    def test_case_b_guard_path_and_repeated_search_fix_mock_replay(self,opener):
        body=dict(model=PAID_MODEL,choices=[dict(finish_reason='stop',message=dict(
            content=json.dumps(dict(action='search',query='same unrelated query'))))],
            usage=dict(cost=.0001,prompt_tokens=100,completion_tokens=10))
        opener.return_value.open.return_value.__enter__.return_value.read.return_value=json.dumps(body).encode()
        with tempfile.TemporaryDirectory() as directory:
            journal=Path(directory)/'journal';journal.write_text('')
            budget=PaidBudget(journal,verify=lambda _:dict(status='PASS'))
            budget.calls=4  # inherited=2 + successful Case A decisions=2
            controller=PaidController(budget)
            retriever=MagicMock();retriever.last_trace=None;retriever.search.return_value=[CHUNK]
            result=run_agent('A generic out-of-scope question',controller,retriever,count_tokens=len,
                             budget=12000,max_searches=2)
            self.assertEqual(result['status'],'abstain')
            self.assertEqual(result['events'][-1]['event'],'repeated_search')
            self.assertEqual((budget.calls,opener.return_value.open.call_count,retriever.search.call_count),(6,2,1))
            # A further request is operational failure, never abstention; it is
            # rejected before HTTP and leaves the actual request count unchanged.
            with self.assertRaises(RuntimeError):controller.decide('q',[])
            self.assertEqual(opener.return_value.open.call_count,2)
            self.assertEqual(controller.last_trace['error'],'SMOKE_API_BUDGET_STOP')
