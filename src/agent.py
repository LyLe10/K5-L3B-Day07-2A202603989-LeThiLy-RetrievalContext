"""Starter-compatible decisions/retrieval; token budget is explicit, not characters."""
from copy import deepcopy
import re
from time import perf_counter

from src.context import pack_context
from src.dense import RetrievalError
from src.retrieval import validate_search

ABSTENTION = 'Không đủ bằng chứng để trả lời.'


def run_agent(question, controller, retriever, *, filters=None, max_searches=4,
              top_k=3, budget=800, count_tokens):
    """Same starter arguments/results; required tokenizer makes budget token-based.

    Operational errors return status=error, never an evidence abstention.
    Citation checks establish membership only, not semantic entailment.
    """
    validate_search(question, filters, top_k)
    if type(max_searches) is not int or max_searches < 1 or type(budget) is not int or budget < 1:
        raise ValueError('INVALID_AGENT_CONFIG')
    started = perf_counter()
    events, candidates, history = [], [], []
    packed = dict(context='',context_ids=[],context_tokens=0,citation_map={})

    def finish(status, reason, answer=ABSTENTION, citations=None):
        events.append(dict(event=reason))
        return dict(question=question, status=status, answer=answer, citations=citations or [], events=events,
                    **packed, elapsed_ms=(perf_counter()-started)*1000,
                    config=dict(max_searches=max_searches,top_k=top_k,context_budget_tokens=budget,
                                token_counter=getattr(count_tokens,'name',type(count_tokens).__name__)),
                    usage=[e['llm'] for e in events if e.get('llm')])

    for _ in range(max_searches+1):
        call_start = perf_counter()
        try:
            action = controller.decide(question, deepcopy(history))
        except Exception as error:
            code = 'LLM_TIMEOUT' if isinstance(error, TimeoutError) else 'LLM_ERROR'
            events.append(dict(event='error',stage='llm',error=code,elapsed_ms=(perf_counter()-call_start)*1000,
                               llm=deepcopy(getattr(controller,'last_trace',None))))
            return finish('error',code,answer='')
        events.append(dict(event='decision',action=deepcopy(action),elapsed_ms=(perf_counter()-call_start)*1000,
                           llm=deepcopy(getattr(controller,'last_trace',None))))
        if not isinstance(action,dict):
            return finish('error','INVALID_ACTION',answer='')
        if action.get('action') == 'search':
            if sum(e['event']=='search' for e in events) >= max_searches:
                return finish('abstain','search_limit')
            query = action.get('query')
            try:
                validate_search(query,filters,top_k)
            except RetrievalError:
                return finish('error','INVALID_SEARCH_QUERY',answer='')
            search_start = perf_counter()
            try:
                results = retriever.search(query,filters=filters,top_k=top_k)
                if len(results)>top_k or len({c['id'] for c in results})!=len(results):
                    raise ValueError('INVALID_RETRIEVER_RESULTS')
                candidates.extend(deepcopy(results))
                packed = pack_context(candidates,budget,count_tokens)
            except Exception as error:
                code = ('RETRIEVAL_TIMEOUT' if isinstance(error,TimeoutError) or
                        (isinstance(error,RetrievalError) and str(error)=='DATABASE_TIMEOUT') else
                        'RETRIEVAL_ERROR' if isinstance(error,RetrievalError) else 'CONTEXT_OR_RESULT_ERROR')
                events.append(dict(event='error',stage='retrieval_context',query=query,filter=filters,
                                   error=code,elapsed_ms=(perf_counter()-search_start)*1000))
                return finish('error',code,answer='')
            events.append(dict(event='search',query=query,filter=deepcopy(filters),top_k=top_k,
                results=deepcopy(results),**deepcopy(packed),elapsed_ms=(perf_counter()-search_start)*1000,
                retrieval_trace=deepcopy(getattr(retriever,'last_trace',None))))
            history = [dict(tool='search',queries=[e['query'] for e in events if e['event']=='search'],
                            **deepcopy(packed))]
        elif action.get('action') == 'answer':
            answer, citations = action.get('answer'),action.get('citations')
            if not isinstance(answer,str) or not isinstance(citations,list) or any(not isinstance(c,str) for c in citations):
                return finish('error','INVALID_ANSWER',answer='')
            # Empty citation list is the starter-compatible explicit abstention signal.
            if not citations:
                return finish('abstain','insufficient_evidence')
            inline = re.findall(r'\[([^\[\]\n]+)\]',answer)
            if (not answer.strip() or not packed['context_ids'] or len(set(citations))!=len(citations)
                    or set(inline)!=set(citations) or any(c not in packed['citation_map'] for c in citations)):
                return finish('abstain','invalid_or_missing_citations')
            return finish('answered','answer',answer,citations)
        else:
            return finish('error','INVALID_ACTION',answer='')
    return finish('abstain','search_limit')
