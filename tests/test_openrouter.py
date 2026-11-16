import io
import json
import os
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

from src.llm import OpenRouterController, _NoRedirect
from src.agent import run_agent

MODEL = 'qwen/qwen3-next-80b-a3b-instruct:free'


@patch.dict(os.environ, {'OPENROUTER_API_KEY':'mock-secret'})
class OpenRouterTests(unittest.TestCase):
    def response(self, opener, content=None, **extra):
        body = dict(choices=[dict(finish_reason='stop', message=dict(content=json.dumps(
            content or dict(action='search', query='q'))))],
            usage=dict(prompt_tokens=30, completion_tokens=10, total_tokens=40, cost=0))
        body.update(extra)
        opener.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(body).encode()

    @patch('src.llm.build_opener')
    def test_request_contract_and_usage(self, opener):
        c = OpenRouterController(MODEL, timeout=12, max_output_tokens=123)
        opener.assert_not_called()
        self.response(opener)
        self.assertEqual(c.decide('question', []), dict(action='search', query='q'))
        request = opener.return_value.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, 'https://openrouter.ai/api/v1/chat/completions')
        self.assertEqual(request.get_header('Authorization'), 'Bearer mock-secret')
        self.assertEqual(payload['model'], MODEL)
        self.assertEqual(payload['max_tokens'], 123)
        self.assertEqual(payload['provider'], dict(allow_fallbacks=False, require_parameters=True,
                                                 max_price=dict(prompt=0, completion=0)))
        self.assertNotIn('models', payload)
        self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], 12)
        self.assertEqual(c.last_trace['usage']['total_tokens'], 40)
        self.assertEqual(c.last_trace['service_cost_usd'], 0)
        self.assertNotIn('mock-secret', json.dumps(c.last_trace))

    @patch('src.llm.build_opener')
    def test_missing_key_no_http(self, opener):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'OPENROUTER_KEY_MISSING'):
                OpenRouterController(MODEL).decide('q', [])
        opener.assert_not_called()

    def test_invalid_config(self):
        for model in ['', 'openrouter/free', 'qwen/paid', None, MODEL+' ', '/:free']:
            with self.assertRaises(ValueError): OpenRouterController(model)
        for kwargs in [dict(timeout=0), dict(timeout=float('nan')), dict(max_output_tokens=True)]:
            with self.assertRaises(ValueError): OpenRouterController(MODEL, **kwargs)

    @patch('src.llm.build_opener')
    def test_http_errors_no_retry_or_secret_leak(self, opener):
        for status, code in [(401,'OPENROUTER_UNAUTHORIZED'), (429,'OPENROUTER_RATE_LIMIT'),
                             (503,'OPENROUTER_PROVIDER_ERROR'), (302,'OPENROUTER_PROVIDER_ERROR')]:
            opener.return_value.open.reset_mock()
            opener.return_value.open.side_effect = HTTPError('url', status, 'mock-secret', {}, io.BytesIO(b'mock-secret'))
            c = OpenRouterController(MODEL)
            with self.assertRaisesRegex(RuntimeError, code): c.decide('q', [])
            self.assertEqual(c.last_trace['http_status'], status)
            self.assertNotIn('mock-secret', json.dumps(c.last_trace))
            self.assertEqual(opener.return_value.open.call_count, 1)

    @patch('src.llm.build_opener')
    def test_timeout_and_network(self, opener):
        for error, expected in [(TimeoutError('mock-secret'), TimeoutError),
                (URLError(TimeoutError('mock-secret')), TimeoutError), (URLError('mock-secret'), RuntimeError)]:
            opener.return_value.open.side_effect = error
            c = OpenRouterController(MODEL)
            with self.assertRaises(expected): c.decide('q', [])
            self.assertNotIn('mock-secret', json.dumps(c.last_trace))

    @patch('src.llm.build_opener')
    def test_provider_error_and_invalid_outputs(self, opener):
        bodies = [dict(error=dict(message='mock-secret')), {},
                  dict(choices=[dict(finish_reason='length')])]
        bodies += [dict(choices=[dict(finish_reason='stop',message=dict(content=s))])
                   for s in ['not json', '[]', None]]
        c = OpenRouterController(MODEL)
        for body in bodies:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(body).encode()
            with self.assertRaises(RuntimeError): c.decide('q', [])
            self.assertNotIn('mock-secret', json.dumps(c.last_trace))
        self.response(opener, usage={})
        c.decide('q', [])
        self.assertIsNone(c.last_trace['service_cost_usd'])

    def test_no_redirect(self):
        self.assertIsNone(_NoRedirect().redirect_request(None,None,302,'',{},'https://example.com'))

    @patch('src.llm.build_opener')
    def test_agent_search_answer_and_abstain(self, opener):
        for citations in [['chunk'], []]:
            self.response(opener, dict(action='search',query='q'))
            first = opener.return_value.open.return_value.__enter__.return_value.read.return_value
            self.response(opener, dict(action='answer',answer='Evidence [chunk]',citations=citations))
            second = opener.return_value.open.return_value.__enter__.return_value.read.return_value
            opener.return_value.open.return_value.__enter__.return_value.read.side_effect = [first,second]
            retriever = MagicMock()
            retriever.search.return_value = [dict(id='chunk',text='Evidence',source_id='doc',
                source='unit.pdf',page=1,metadata={},score=1)]
            result = run_agent('q',OpenRouterController(MODEL),retriever,count_tokens=len,budget=1000)
            self.assertEqual(result['status'], 'answered' if citations else 'abstain')
            self.assertEqual(len(result['usage']), 2)
