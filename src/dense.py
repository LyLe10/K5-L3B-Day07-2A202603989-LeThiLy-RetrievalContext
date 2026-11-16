"""Read-only Day 06 B snapshot adapter implementing starter.Retriever.search."""
from contextlib import contextmanager
from dataclasses import dataclass
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

DATASET = 'day06-postgresql'
PROFILE = '528f0792d5fdf66a50c7d42f12de648935d70e2912072e6c6dd2eb6b3f4fd651'
SNAPSHOT = 'c7d9d92e6695709595d044e5a5a09bb8f91826fb692474c7b1806751015ec1e0'
MANIFEST = '6ec73dc52b8cb5d83f5b08baeffcb231109cc2bbd95525c3315ae72c1f29db5d'
CORPUS = '1a2f8abbcda200d11f7316d9d5069ade2e6b32f09b02f69f1b49c1046779811e'
MODEL = 'intfloat/multilingual-e5-small'
REVISION = 'fd1525a9fd15316a2d503bf26ab031a61d056e98'
COLUMNS = ('chunk_id', 'document_id', 'source', 'physical_page', 'printed_page_label',
           'section', 'start_char', 'end_char', 'text', 'metadata', 'snapshot_id',
           'manifest_sha256', 'corpus_sha256', 'source_sha256', 'page_text_sha256',
           'text_sha256', 'page_id', 'dataset_id', 'profile_id', 'strategy')
NAMESPACE = (DATASET, PROFILE, 'B', SNAPSHOT)
WHERE = 'dataset_id=%s AND profile_id=%s AND strategy=%s AND snapshot_id=%s'


class RetrievalError(RuntimeError):
    """Sanitized failure code only; never include DSN, SQL parameters or backend text."""


@dataclass(frozen=True)
class Config:
    day6_root: Path
    statement_timeout_ms: int = 10000

    def __post_init__(self):
        if not isinstance(self.day6_root, Path) or not (self.day6_root / 'starter/src/embeddings.py').is_file():
            raise RetrievalError('INVALID_DAY6_ROOT')
        if type(self.statement_timeout_ms) is not int or not 1 <= self.statement_timeout_ms <= 30000:
            raise RetrievalError('INVALID_STATEMENT_TIMEOUT')


def validate_dsn(value):
    try:
        u = urlsplit(value)
        valid = (u.scheme in ('postgresql', 'postgres') and u.hostname == '127.0.0.1'
                 and u.port == 55433 and u.path == '/day6_lab' and u.username == 'day6'
                 and bool(u.password) and not u.query and not u.fragment)
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise RetrievalError('INVALID_DATABASE_TARGET')
    return value


def read_dsn(config):
    from dotenv import dotenv_values
    try:
        # Parse only the one entry; no environment mutation and no provider key loading.
        lines = (config.day6_root / 'starter/.env').read_text(encoding='utf-8').splitlines()
        selected = [s for s in lines if s.strip().startswith(('DATABASE_URL=', 'DATABASE_URL ='))]
        from io import StringIO
        values = dotenv_values(stream=StringIO('\n'.join(selected)), interpolate=False)
        return validate_dsn(values.get('DATABASE_URL'))
    except RetrievalError:
        raise
    except Exception:
        raise RetrievalError('DATABASE_CONFIG_UNAVAILABLE') from None


def validate_vector(vector):
    try:
        if len(vector) != 384 or any(isinstance(x, (bool, str)) for x in vector):
            raise ValueError()
        values = [float(x) for x in vector]
        if not all(math.isfinite(x) for x in values) or abs(math.sqrt(math.fsum(x*x for x in values)) - 1) > 1e-5:
            raise ValueError()
        return values
    except (ValueError, TypeError, OverflowError):
        raise RetrievalError('INVALID_QUERY_VECTOR') from None


def load_embedder(config):
    """Reuse Day 06's checksum/profile/prefix/token-limit checks, disabling cache writes."""
    previous_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        package = '_day6_dense_readonly'
        path = config.day6_root / 'starter/src'
        if package not in sys.modules:
            spec = importlib.util.spec_from_file_location(package, path / '__init__.py',
                                                         submodule_search_locations=[str(path)])
            module = importlib.util.module_from_spec(spec)
            sys.modules[package] = module
            spec.loader.exec_module(module)
        embeddings = importlib.import_module(package + '.embeddings')
        if Path(embeddings.__file__).resolve() != (path / 'embeddings.py').resolve():
            raise RetrievalError('DAY6_MODULE_PATH_MISMATCH')
        if embeddings.MODEL != MODEL or embeddings.REVISION != REVISION:
            raise RetrievalError('MODEL_IDENTITY_MISMATCH')

        class ReadOnlyEmbedder(embeddings.MyEmbedder):
            def _write_cache(self, key, vector):
                pass  # Existing cache may be read; Day 06 is never written.

            def embed_documents(self, texts):
                raise RetrievalError('CORPUS_ENCODING_DISABLED')

        encoder = ReadOnlyEmbedder(MODEL)
        if encoder.profile_id != PROFILE:
            raise RetrievalError('EMBEDDING_PROFILE_MISMATCH')
        return encoder
    except RetrievalError:
        raise
    except Exception:
        raise RetrievalError('MODEL_VERIFICATION_FAILED') from None
    finally:
        sys.dont_write_bytecode = previous_bytecode


def map_chunk(row, rank):
    c = dict(zip((*COLUMNS, 'cosine_distance'), row, strict=True))
    if (tuple(c[k] for k in ('dataset_id', 'profile_id', 'strategy', 'snapshot_id')) != NAMESPACE
            or c['manifest_sha256'] != MANIFEST or c['corpus_sha256'] != CORPUS
            or c['metadata'].get('source_id') != c['document_id']
            or c['metadata'].get('physical_page') != c['physical_page']):
        raise RetrievalError('CHUNK_PROVENANCE_MISMATCH')
    c.update(id=c['chunk_id'], source_id=c['document_id'], page=c['physical_page'],
             score=1-float(c['cosine_distance']), rank=rank, retrieval_method='dense')
    c['citation'] = dict(chunk_id=c['id'], source=c['source'],
                         physical_page=c['page'], printed_page_label=c['printed_page_label'])
    return c


class DenseRetriever:
    def __init__(self, config, embedder, *, connect=None):
        self.config, self.embedder = config, embedder
        if embedder.profile_id != PROFILE:
            raise RetrievalError('EMBEDDING_PROFILE_MISMATCH')
        if connect is None:
            import psycopg
            connect = psycopg.connect
        self._connect = connect
        self._vectors = {}
        self.last_trace = None

    @contextmanager
    def transaction(self):
        conn = None
        try:
            conn = self._connect(read_dsn(self.config), connect_timeout=5,
                options=f'-c default_transaction_read_only=on -c statement_timeout={self.config.statement_timeout_ms}'
                        ' -c lock_timeout=5000 -c search_path=pg_catalog,public', autocommit=False)
            with conn.cursor() as cur:
                cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                cur.execute("SELECT current_database(),current_user,current_setting('transaction_read_only')")
                if cur.fetchone() != ('day6_lab', 'day6', 'on'):
                    raise RetrievalError('READ_ONLY_TARGET_MISMATCH')
            yield conn
        except RetrievalError:
            raise
        except Exception as error:
            code = 'DATABASE_TIMEOUT' if getattr(error, 'sqlstate', None) == '57014' else 'DATABASE_ERROR'
            raise RetrievalError(code) from None
        finally:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass

    def preflight(self, conn):
        with conn.cursor() as cur:
            cur.execute('SELECT status,expected_count,actual_count,selected_page_count,manifest_sha256,corpus_sha256 '
                        'FROM day6_ingestion.strategy_snapshots WHERE ' + WHERE, NAMESPACE)
            if cur.fetchone() != ('complete', 264, 264, 40, MANIFEST, CORPUS):
                raise RetrievalError('SNAPSHOT_MISMATCH')
            cur.execute('SELECT config_canonical FROM day6_ingestion.embedding_profiles WHERE profile_id=%s', (PROFILE,))
            row = cur.fetchone()
            if row is None or row[0] != self.embedder.profile.config_canonical:
                raise RetrievalError('DATABASE_PROFILE_MISMATCH')
            cur.execute('SELECT count(*),count(DISTINCT page_id),min(public.vector_dims(embedding)),'
                        'max(public.vector_dims(embedding)) FROM day6_ingestion.chunks WHERE ' + WHERE, NAMESPACE)
            if cur.fetchone() != (264, 40, 384, 384):
                raise RetrievalError('SNAPSHOT_CONTENT_MISMATCH')

    def search(self, query: str, *, filters: dict | None, top_k: int) -> list[dict]:
        if not isinstance(query, str) or not query.strip() or '\x00' in query:
            raise RetrievalError('INVALID_QUERY')
        if type(top_k) is not int or not 1 <= top_k <= 264:
            raise RetrievalError('INVALID_TOP_K')
        if filters is not None and (not isinstance(filters, dict) or
                (filters and (set(filters) != {'section'} or not isinstance(filters['section'], str)
                              or not filters['section'].strip() or '\x00' in filters['section']))):
            raise RetrievalError('INVALID_FILTER')
        from time import perf_counter
        start = perf_counter()
        cache_hit = query in self._vectors
        try:
            if not cache_hit:
                self._vectors[query] = validate_vector(self.embedder.embed_query(query))
            vector = validate_vector(self._vectors[query])
            with self.transaction() as conn:
                self.preflight(conn)
                with conn.cursor() as cur:
                    sql = ('SELECT ' + ','.join(COLUMNS) + ',embedding <=> %s::public.vector AS cosine_distance '
                           'FROM day6_ingestion.chunks WHERE ' + WHERE)
                    params = (json.dumps(vector), *NAMESPACE)
                    if filters:
                        sql += ' AND section=%s'
                        params += (filters['section'],)
                    cur.execute(sql + ' ORDER BY cosine_distance,chunk_id LIMIT %s', (*params, top_k))
                    results = [map_chunk(row, rank) for rank, row in enumerate(cur.fetchall(), 1)]
            self.last_trace = dict(query=query, filters=filters, top_k=top_k, results=results,
                elapsed_ms=(perf_counter()-start)*1000, query_cache_hit=cache_hit,
                profile_id=PROFILE, snapshot_id=SNAPSHOT, status='ok', service_cost_usd=0)
            return results
        except Exception as error:
            code = str(error) if isinstance(error, RetrievalError) else 'QUERY_EMBEDDING_FAILED'
            self.last_trace = dict(query=query, top_k=top_k, status='error', error=code,
                                   elapsed_ms=(perf_counter()-start)*1000)
            raise RetrievalError(code) from None


def pack_dense_context(results, budget=800):
    """Reuse starter's selection/budget logic, explicitly labeling both page systems."""
    from starter.baseline import pack_context
    labeled = [{**c, 'page': f"physical {c['page']}; printed {c['printed_page_label'] or 'unavailable'}"}
               for c in results]
    return pack_context(labeled, budget=budget)
