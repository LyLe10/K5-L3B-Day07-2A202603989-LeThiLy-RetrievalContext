"""Opt-in real LLM + Day 06 retrieval, one question, no benchmark input."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.agent import run_agent
from src.dense import Config,DenseRetriever,load_embedder
from src.retrieval import create_retriever
from src.llm import OllamaController,OpenRouterController,LocalTokenCounter


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--provider',choices=['ollama','openrouter'],default='ollama')
    p.add_argument('--approve-local-llm',action='store_true')
    p.add_argument('--approve-openrouter',action='store_true',help='Explicitly allow sending question/context to OpenRouter')
    p.add_argument('--day6-root',type=Path,required=True)
    p.add_argument('--method',choices=['dense','lexical','hybrid'],required=True)
    p.add_argument('--model',required=True)
    p.add_argument('--tokenizer-path',type=Path,required=True,help='Local tokenizer for the exact LLM, not E5')
    p.add_argument('--question',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--budget',type=int,default=1200)
    p.add_argument('--max-searches',type=int,default=2)
    args=p.parse_args()
    if args.provider=='ollama' and not args.approve_local_llm:
        p.error('Ollama requires --approve-local-llm')
    if args.provider=='openrouter' and not args.approve_openrouter:
        p.error('OpenRouter requires --approve-openrouter')
    controller=(OpenRouterController(args.model) if args.provider=='openrouter'
                else OllamaController(args.model))
    counter=LocalTokenCounter(args.tokenizer_path)
    config=Config(args.day6_root)
    dense=DenseRetriever(config,load_embedder(config))
    retriever=create_retriever(args.method,dense)
    result=run_agent(args.question,controller,retriever,
        count_tokens=counter,budget=args.budget,max_searches=args.max_searches)
    result.update(kind='real_llm_smoke_not_benchmark',question=args.question,method=args.method)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(dict(status=result['status'],output=str(args.output))))


if __name__=='__main__': main()
