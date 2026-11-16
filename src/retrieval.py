"""Snapshot B TF-IDF and reciprocal rank fusion; no benchmark inputs."""
from copy import deepcopy
from time import perf_counter

from starter.baseline import TfidfIndex
from src import dense as d


def validate_search(query, filters, top_k):
    if not isinstance(query, str) or not query.strip() or '\x00' in query:
        raise d.RetrievalError('INVALID_QUERY')
    if type(top_k) is not int or not 1 <= top_k <= 264:
        raise d.RetrievalError('INVALID_TOP_K')
    if filters is not None and (not isinstance(filters, dict) or
            (filters and (set(filters) != {'section'} or not isinstance(filters['section'], str)
                          or not filters['section'].strip() or '\x00' in filters['section']))):
        raise d.RetrievalError('INVALID_FILTER')


def load_snapshot(dense):
    """Read texts/provenance only, using the existing verified read-only adapter."""
    with dense.transaction() as conn:
        dense.preflight(conn)
        with conn.cursor() as cur:
            cur.execute('SELECT ' + ','.join(d.COLUMNS) +
                        ' FROM day6_ingestion.chunks WHERE ' + d.WHERE +
                        ' ORDER BY chunk_id', d.NAMESPACE)
            chunks = [d.map_chunk((*row, 1.0), i) for i, row in enumerate(cur.fetchall(), 1)]
    if len(chunks) != 264 or len({c['id'] for c in chunks}) != 264:
        raise d.RetrievalError('SNAPSHOT_CONTENT_MISMATCH')
    for c in chunks:
        for key in ('score', 'rank', 'retrieval_method', 'cosine_distance'):
            c.pop(key)
    return chunks


class LexicalRetriever:
    def __init__(self, chunks):
        # Validate provenance without accepting alternate A/B corpora.
        if len(chunks) != 264 or len({c['id'] for c in chunks}) != 264:
            raise d.RetrievalError('SNAPSHOT_CONTENT_MISMATCH')
        self.chunks = deepcopy(chunks)
        for c in self.chunks:
            d.map_chunk(tuple(c[k] for k in d.COLUMNS) + (1.0,), 1)
        self.index = TfidfIndex(self.chunks)
        self.last_trace = None

    def search(self, query: str, *, filters: dict | None, top_k: int) -> list[dict]:
        started = perf_counter()
        try:
            validate_search(query, filters, top_k)
            # IDF always uses the complete frozen corpus, even with a section filter.
            results = self.index.search(query, top_k=264)
            results = [c for c in results if not filters or c['section'] == filters['section']][:top_k]
            results = [dict(deepcopy(c), strategy='B', retrieval_method='lexical', rank=i)
                       for i, c in enumerate(results, 1)]
            self.last_trace = dict(query=query, filters=filters, top_k=top_k, results=results,
                                   status='ok', snapshot_id=d.SNAPSHOT, profile_id=d.PROFILE,
                                   elapsed_ms=(perf_counter()-started)*1000, service_cost_usd=0)
            return results
        except d.RetrievalError as error:
            self.last_trace = dict(status='error', error=str(error), elapsed_ms=(perf_counter()-started)*1000)
            raise


class HybridRetriever:
    def __init__(self, dense, lexical, *, rrf_k=60, candidate_k=20):
        if type(rrf_k) is not int or rrf_k < 1 or type(candidate_k) is not int or not 1 <= candidate_k <= 264:
            raise d.RetrievalError('INVALID_HYBRID_CONFIG')
        self.dense, self.lexical = dense, lexical
        self.rrf_k, self.candidate_k = rrf_k, candidate_k
        self.last_trace = None

    def search(self, query: str, *, filters: dict | None, top_k: int) -> list[dict]:
        started = perf_counter()
        try:
            validate_search(query, filters, top_k)
            depth = max(top_k, self.candidate_k)
            candidates, scores, provenance = {}, {}, {}
            for name, retriever in [('dense', self.dense), ('lexical', self.lexical)]:
                seen = set()
                for c in retriever.search(query, filters=filters, top_k=depth):
                    cid = c['id']
                    if cid in seen:
                        continue
                    seen.add(cid)
                    rank = len(seen)
                    if cid in candidates and any(c.get(k) != candidates[cid].get(k) for k in d.COLUMNS):
                        raise d.RetrievalError('CHUNK_PROVENANCE_MISMATCH')
                    candidates.setdefault(cid, deepcopy(c))
                    scores[cid] = scores.get(cid, 0) + 1 / (self.rrf_k + rank)
                    provenance.setdefault(cid, {})[name] = dict(rank=rank, score=c['score'])
            results = []
            for rank, cid in enumerate(sorted(scores, key=lambda cid: (-scores[cid], cid))[:top_k], 1):
                c = candidates[cid]
                c.pop('cosine_distance', None)
                c.update(score=scores[cid], rank=rank, retrieval_method='hybrid',
                         component_ranks=provenance[cid])
                results.append(c)
            self.last_trace = dict(query=query, filters=filters, top_k=top_k, results=results,
                rrf_k=self.rrf_k, candidate_k=depth, status='ok', snapshot_id=d.SNAPSHOT,
                elapsed_ms=(perf_counter()-started)*1000, service_cost_usd=0,
                components=dict(dense=deepcopy(self.dense.last_trace), lexical=deepcopy(self.lexical.last_trace)))
            return results
        except d.RetrievalError as error:
            self.last_trace = dict(status='error', error=str(error), elapsed_ms=(perf_counter()-started)*1000)
            raise


def create_retriever(method, dense, *, lexical=None):
    if method not in ('dense', 'lexical', 'hybrid'):
        raise d.RetrievalError('INVALID_RETRIEVAL_METHOD')
    if method == 'dense':
        return dense
    if lexical is None:
        lexical = LexicalRetriever(load_snapshot(dense))
    return lexical if method == 'lexical' else HybridRetriever(dense, lexical)
