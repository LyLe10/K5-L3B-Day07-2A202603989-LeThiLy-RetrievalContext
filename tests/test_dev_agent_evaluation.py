import copy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts.dev_agent_evaluation import (automatic_checks, cost_plan, evaluate_agent_dev,
    review_template, score_reviewed)
from tests.test_dev_readiness import CHUNK, cases


class MockController:
    """Synthetic requests only, never uses a network provider."""
    def __init__(self, mode='answer'):
        self.calls=0
        self.mode=mode
        self.inputs=[]
        self.last_trace=None

    def decide(self, question, history):
        self.calls+=1
        self.inputs.append(copy.deepcopy((question,history)))
        self.last_trace=dict(provider='mock',model='unit-model',status='ok',
            usage=dict(prompt_tokens=50,completion_tokens=10,total_tokens=60),service_cost_usd=.00001)
        if self.mode=='error':
            self.last_trace.update(status='error',error='OPENROUTER_UNAUTHORIZED',http_status=401)
            raise RuntimeError('private provider response')
        if not history:return dict(action='search',query='synthetic query')
        if self.mode=='repeat':return dict(action='search',query=' SYNTHETIC query  ')
        if self.mode=='abstain':return dict(action='answer',answer='not supported',citations=[])
        return dict(action='answer',answer='Claim [synthetic]',citations=['synthetic'])


class DevAgentEvaluationTests(unittest.TestCase):
    def execute(self, root, controller, **kwargs):
        lexical=MagicMock(spec=['search','last_trace'])
        lexical.last_trace=None
        lexical.search.return_value=[CHUNK]
        with patch('scripts.dev_agent_evaluation.LexicalRetriever',return_value=lexical) as factory:
            report=evaluate_agent_dev(cases(),[CHUNK],controller,
                output=Path(root)/'traces.jsonl',request_count=lambda:controller.calls,**kwargs)
            factory.assert_called_once_with([CHUNK])
        return report,lexical

    def test_all_17_use_selected_lexical_top3_without_gold_and_save_cases(self):
        with tempfile.TemporaryDirectory() as root:
            controller=MockController()
            result,retriever=self.execute(root,controller)
            self.assertEqual(controller.calls,34)
            self.assertEqual(retriever.search.call_count,17)
            for call in retriever.search.call_args_list:
                self.assertEqual(call.kwargs,dict(filters=None,top_k=3))
            self.assertEqual([q for q,h in controller.inputs[::2]],[c['question'] for c in cases()])
            self.assertNotIn('expected_answer',json.dumps(controller.inputs))
            self.assertNotIn('gold',json.dumps(controller.inputs))
            rows=[json.loads(line) for line in (Path(root)/'traces.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),17)
            self.assertEqual(rows[-1]['cumulative_llm_requests'],34)
            self.assertEqual(rows[0]['automatic']['token_usage']['total_tokens']['known_sum'],120)
            self.assertEqual(rows[0]['llm_requests'],2)
            self.assertEqual(rows[0]['config']['top_k'],3)
            self.assertEqual(rows[0]['config']['max_searches'],2)
            self.assertEqual(rows[0]['manual_review']['status'],'PENDING_MANUAL_REVIEW')
            self.assertIsNone(rows[-1]['automatic']['context_gold_hit'])
            self.assertEqual(result['status'],'PENDING_MANUAL_REVIEW')

    def test_repeated_search_is_abstention_not_second_retrieval(self):
        with tempfile.TemporaryDirectory() as root:
            result,retriever=self.execute(root,MockController('repeat'))
            self.assertEqual(retriever.search.call_count,17)
            self.assertTrue(all(t['status']=='abstain' and
                t['automatic']['termination']=='repeated_search' for t in result['cases']))

    def test_provider_failure_stops_other_cases_never_becomes_abstention(self):
        with tempfile.TemporaryDirectory() as root:
            controller=MockController('error')
            result,retriever=self.execute(root,controller)
            self.assertEqual(controller.calls,1)
            retriever.search.assert_not_called()
            self.assertEqual(result['system_errors'],1)
            self.assertEqual(result['not_run'],16)
            self.assertEqual(result['cases'][0]['llm_requests'],1)
            self.assertNotIn('private',json.dumps(result))

    def test_existing_output_refused_without_controller_calls(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'traces.jsonl';p.write_text('old evidence')
            controller=MockController()
            with self.assertRaises(FileExistsError):self.execute(root,controller)
            self.assertEqual(controller.calls,0)
            self.assertEqual(p.read_text(),'old evidence')

    def test_test_rows_rejected_before_retriever_or_controller(self):
        rows=cases();rows[0]['split']='test'
        with patch('scripts.dev_agent_evaluation.LexicalRetriever') as factory:
            with self.assertRaises(ValueError):
                evaluate_agent_dev(rows,[CHUNK],MockController(),output=Path('unused'),request_count=lambda:0)
            factory.assert_not_called()

    def test_membership_does_not_auto_approve_semantic_support(self):
        with tempfile.TemporaryDirectory() as root:
            result,_=self.execute(root,MockController())
        traces=result['cases']
        reviews=[]
        for case,t in zip(cases(),traces):
            review=review_template(case,t)
            review.update(status='REVIEWED',rationale='Synthetic manual test: unsupported claim.',
                context_grade=2,answer_correctness_grade=0,answer_grade=0,
                citation_support=[False],citation_reasons=['Does not support the claim.'],
                abstention_correct=False)
            reviews.append(review)
        self.assertTrue(traces[0]['automatic']['citation_membership'][0])
        scored=score_reviewed(cases(),traces,reviews)
        self.assertEqual(scored['citation_validity'],dict(n=0,N=17))
        self.assertEqual(scored['answer_correctness']['N'],15)
        self.assertEqual(scored['answer_correctness']['normalized_mean'],0)
        self.assertEqual(scored['abstention_scheduled'],dict(n=0,N=2))
        reviews[0]['citation_support']=[True]
        traces[0]['context_ids']=[]
        with self.assertRaisesRegex(ValueError,'SUPPORTED_CITATION'):
            score_reviewed(cases(),traces,reviews)

    def test_pending_reviews_and_incomplete_run_cannot_produce_final_metrics(self):
        with tempfile.TemporaryDirectory() as root:
            result,_=self.execute(root,MockController('abstain'))
        traces=result['cases'];reviews=[review_template(c,t) for c,t in zip(cases(),traces)]
        with self.assertRaisesRegex(ValueError,'MANUAL_REVIEW'):
            score_reviewed(cases(),traces,reviews)
        traces[0]['status']='NOT_RUN_GLOBAL_STOP'
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_RUN'):
            score_reviewed(cases(),traces,reviews)

    def test_missing_usage_is_unknown_not_free_or_zero_tokens(self):
        with tempfile.TemporaryDirectory() as root:
            result,_=self.execute(root,MockController())
        t=result['cases'][0]
        for e in t['events']:e.pop('llm',None)
        checks=automatic_checks(cases()[0],t)
        self.assertFalse(checks['token_usage']['prompt_tokens']['complete'])
        self.assertFalse(checks['reported_cost_usd']['complete'])
        self.assertEqual(checks['reported_cost_usd']['reported_calls'],0)

    def test_cost_proposal_is_separate_from_exhausted_smoke_and_disabled(self):
        plan=cost_plan()
        self.assertEqual(plan['max_llm_requests'],17*(2+1))
        self.assertEqual(Decimal(plan['estimated_max_cost_usd']),Decimal('0.16852032'))
        self.assertLess(Decimal(plan['proposed_total_reservation_usd']),Decimal(plan['proposed_budget_usd']))
        self.assertFalse(plan['paid_execution_enabled'])
        self.assertEqual(plan['status'],'PROPOSED_NOT_AUTHORIZED')
