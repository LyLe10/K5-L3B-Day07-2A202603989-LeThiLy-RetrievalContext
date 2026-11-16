"""Read-only smoke preflight. Never calls an inference API or prints credentials."""
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.llm import OpenRouterController


def main():
    model = 'qwen/qwen3-next-80b-a3b-instruct:free'
    controller = OpenRouterController(model, timeout=60, max_output_tokens=512)
    key_present = bool(os.environ.get('OPENROUTER_API_KEY', '').strip())
    report = dict(kind='real_llm_smoke_preflight', python=sys.version.split()[0],
        model=controller.model, provider='openrouter', key_present=key_present,
        timeout=controller.timeout, max_output_tokens=controller.max_output_tokens,
        planned_limits=dict(cases=2, shared_llm_calls=6, retrieval_calls_per_case=2,
                            retries=0, fallback=False, prompt_price_cap=0, completion_price_cap=0),
        actual_llm_calls=0, actual_retrieval_calls=0,
        benchmark_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'data').rglob('*')) if p.is_file() and 'local' not in p.parts},
        status='STOPPED' if not key_present else 'KEY_CHECK_PASSED_OTHER_CHECKS_PENDING',
        errors=['OPENROUTER_KEY_MISSING_IN_EXECUTION_ENVIRONMENT'] if not key_present else [],
        database_check='NOT_RUN', tokenizer_check='NOT_RUN',
        cases=[dict(case_id=c, status='NOT_RUN') for c in ['A','B']])
    output = ROOT/'results/milestone4b_real_llm_preflight.json'
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k:report[k] for k in ('status','key_present','actual_llm_calls','errors')}))


if __name__ == '__main__':
    main()
