import copy
import json
import unittest
from unittest.mock import MagicMock,patch

from src.context import pack_context
from src.agent import run_agent,ABSTENTION
from src.dense import RetrievalError
from src.llm import OllamaController

CHUNK=dict(id='B:unit-1',source_id='unit-doc',source='unit.pdf',page=42,
           printed_page_label='4',text='Synthetic evidence.',metadata={},score=0.99)


def counter(text):
    # Deliberately simple deterministic test double, never reported as model tokens.
    return len(text)


class ContextAgentTests(unittest.TestCase):
    def agent(self,actions,rows=None,**kwargs):
        controller=MagicMock(spec=['decide'])
        controller.decide.side_effect=actions
        retriever=MagicMock(spec=['search'])
        retriever.search.return_value=[CHUNK] if rows is None else rows
        return run_agent('Technical smoke question',controller,retriever,count_tokens=counter,**kwargs)

    def test_context_metadata_dedup_determinism_and_immutability(self):
        before=copy.deepcopy(CHUNK)
        a=pack_context([CHUNK,CHUNK],1000,counter)
        self.assertEqual(a,pack_context([CHUNK],1000,counter))
        self.assertEqual(CHUNK,before)
        c=json.loads(a['context'])[0]
        for k in ('source_id','source','page','printed_page_label','id','text'):
            self.assertEqual(c[k],CHUNK[k])
        self.assertNotIn('score',c)

    def test_exact_budget_skip_oversize_and_empty(self):
        a=pack_context([CHUNK],1000,counter)
        self.assertEqual(pack_context([CHUNK],a['context_tokens'],counter),a)
        self.assertEqual(pack_context([CHUNK],a['context_tokens']-1,counter)['context_ids'],[])
        large=dict(CHUNK,id='large',text='x'*2000)
        self.assertEqual(pack_context([large,CHUNK],1000,counter)['context_ids'],[CHUNK['id']])
        self.assertEqual(pack_context([],1,counter)['context_tokens'],0)

    def test_context_conflicts_and_invalid_counter(self):
        with self.assertRaises(ValueError):pack_context([CHUNK,dict(CHUNK,text='different')],1000,counter)
        with self.assertRaises(ValueError):pack_context([CHUNK],1000,lambda _: -1)

    def test_search_answer_and_citation_map(self):
        result=self.agent([dict(action='search',query='q'),dict(action='answer',
            answer='Synthetic evidence [B:unit-1]',citations=['B:unit-1'])])
        self.assertEqual(result['status'],'answered')
        self.assertEqual(result['citation_map']['B:unit-1']['page'],42)
        self.assertEqual(result['events'][1]['event'],'search')
        self.assertEqual(result['events'][1]['results'][0],CHUNK)

    def test_explicit_abstention_discards_unsupported_answer(self):
        r=self.agent([dict(action='search',query='q'),dict(action='answer',answer='Unsupported claim',citations=[])])
        self.assertEqual((r['status'],r['answer']),('abstain',ABSTENTION))

    def test_unknown_extra_duplicate_or_unmarked_citations(self):
        for answer,citations in [('claim [unknown]',['unknown']),('claim',['B:unit-1']),
                ('claim [B:unit-1] [unknown]',['B:unit-1']),('claim [B:unit-1]',['B:unit-1','B:unit-1'])]:
            r=self.agent([dict(action='search',query='q'),dict(action='answer',answer=answer,citations=citations)])
            self.assertEqual(r['status'],'abstain')

    def test_empty_context_and_no_search_cannot_answer(self):
        answer=dict(action='answer',answer='claim [B:unit-1]',citations=['B:unit-1'])
        for actions,rows,budget in [([answer],None,800),([dict(action='search',query='q'),answer],[],800),
                                    ([dict(action='search',query='q'),answer],None,1)]:
            self.assertEqual(self.agent(actions,rows,budget=budget)['status'],'abstain')

    def test_cumulative_context_budget_and_filter_forwarding(self):
        controller=MagicMock(spec=['decide'])
        controller.decide.side_effect=[dict(action='search',query='one'),dict(action='search',query='two'),
            dict(action='answer',answer='claim [B:unit-1]',citations=['B:unit-1'])]
        retriever=MagicMock(spec=['search'])
        retriever.search.side_effect=[[CHUNK],[dict(CHUNK,id='second')]]
        run_agent('q',controller,retriever,count_tokens=counter,budget=240,filters={'section':'DDL'})
        self.assertEqual(retriever.search.call_args.kwargs['filters'],{'section':'DDL'})
        history=controller.decide.call_args.args[1]
        self.assertLessEqual(history[0]['context_tokens'],240)
        self.assertEqual(history[0]['queries'],['one','two'])

    def test_search_limit_and_invalid_actions(self):
        r=self.agent([dict(action='search',query='q')]*3,max_searches=2)
        self.assertEqual(r['events'][-1]['event'],'search_limit')
        for action in [None,dict(action='bad'),dict(action='search',query=''),dict(action='answer',answer=1,citations=[])]:
            self.assertEqual(self.agent([action])['status'],'error')

    def test_llm_retrieval_errors_and_timeouts_are_separate_from_abstention(self):
        for error in [RuntimeError('secret backend'),TimeoutError('secret')]:
            r=self.agent([error])
            self.assertEqual(r['status'],'error')
            self.assertNotIn('secret',json.dumps(r))
        for error in [RetrievalError('DATABASE_ERROR'),RetrievalError('DATABASE_TIMEOUT'),TimeoutError('secret')]:
            c=MagicMock(spec=['decide']);c.decide.return_value=dict(action='search',query='q')
            r=MagicMock(spec=['search']);r.search.side_effect=error
            result=run_agent('q',c,r,count_tokens=counter)
            self.assertEqual(result['status'],'error')
            self.assertNotIn('secret',json.dumps(result))
            if str(error)=='DATABASE_TIMEOUT':
                self.assertEqual(result['events'][-1]['event'],'RETRIEVAL_TIMEOUT')

    def test_duplicate_retrieval_results_fail(self):
        r=self.agent([dict(action='search',query='q')],rows=[CHUNK,CHUNK])
        self.assertEqual(r['status'],'error')

    @patch('src.llm.build_opener')
    def test_local_controller_request_usage_and_action(self,opener):
        response=opener.return_value.open.return_value.__enter__.return_value
        response.read.return_value=json.dumps(dict(done=True,done_reason='stop',prompt_eval_count=20,
            eval_count=10,message=dict(content='{"action":"search","query":"q"}'))).encode()
        c=OllamaController('unit-model')
        self.assertEqual(c.decide('question',[])['action'],'search')
        request=opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url,'http://127.0.0.1:11434/api/chat')
        self.assertEqual(c.last_trace['usage']['eval_count'],10)
        self.assertEqual(json.loads(request.data)['options']['temperature'],0)

    @patch('src.llm.build_opener')
    def test_controller_timeout_and_malformed_json(self,opener):
        c=OllamaController('unit-model')
        opener.return_value.open.side_effect=TimeoutError('secret')
        with self.assertRaises(TimeoutError):c.decide('q',[])
        self.assertEqual(c.last_trace['error'],'LLM_TIMEOUT')
        opener.return_value.open.side_effect=ValueError('secret')
        with self.assertRaisesRegex(RuntimeError,'LLM_ERROR'):c.decide('q',[])

    @patch('src.llm.build_opener')
    def test_controller_rejects_truncated_or_invalid_model_output(self,opener):
        response=opener.return_value.open.return_value.__enter__.return_value
        for body in [dict(done=False),dict(done=True,done_reason='length'),
                     dict(done=True,message=dict(content='not json')),
                     dict(done=True,message=dict(content='[]'))]:
            response.read.return_value=json.dumps(body).encode()
            with self.assertRaisesRegex(RuntimeError,'LLM_ERROR'):
                OllamaController('unit-model').decide('q',[])
        with self.assertRaises(ValueError):OllamaController('unit-cloud')
