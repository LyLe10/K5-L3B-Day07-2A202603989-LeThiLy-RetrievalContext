"""Whole-chunk context packing with an explicit model tokenizer."""
import json


def pack_context(results, budget, count_tokens):
    if type(budget) is not int or budget < 1:
        raise ValueError('INVALID_CONTEXT_BUDGET')
    selected, seen = [], {}
    for chunk in results:
        cid = chunk['id']
        record = {k: chunk[k] for k in ('id', 'source_id', 'source', 'page', 'text')}
        record['printed_page_label'] = chunk.get('printed_page_label')
        if cid in seen:
            if seen[cid] != record:
                raise ValueError('CONFLICTING_CHUNK_ID')
            continue
        seen[cid] = record
        trial = json.dumps(selected + [record], ensure_ascii=False)
        tokens = count_tokens(trial)
        if type(tokens) is not int or tokens < 0:
            raise ValueError('INVALID_TOKEN_COUNT')
        if tokens <= budget:
            selected.append(record)
    text = json.dumps(selected, ensure_ascii=False) if selected else ''
    return dict(context=text, context_ids=[c['id'] for c in selected],
                context_tokens=count_tokens(text) if text else 0,
                citation_map={c['id']: {k: v for k, v in c.items() if k != 'text'} for c in selected})
