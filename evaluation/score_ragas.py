"""Pinned RAGAS 0.2.15 API, local Ollama judge and local embeddings."""
import argparse
import json
import math
import os
from pathlib import Path

os.environ.setdefault('RAGAS_DO_NOT_TRACK','true')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',default='evaluation/results/live_responses.json')
    parser.add_argument('--output',default='evaluation/results/ragas_metrics.json')
    parser.add_argument('--judge',default='gemma3:4b');parser.add_argument('--embedding-model',default='nomic-embed-text')
    parser.add_argument('--ollama',default='http://127.0.0.1:11434');args=parser.parse_args()
    from ragas import EvaluationDataset, evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.metrics import Faithfulness, ResponseRelevancy, LLMContextPrecisionWithReference, LLMContextRecall
    from ragas.run_config import RunConfig
    from langchain_ollama import ChatOllama, OllamaEmbeddings
    data=json.loads(Path(args.input).read_text())
    valid=[r for r in data['records'] if not r['off_material'] and 'response' in r]
    if not valid: raise SystemExit('No completed on-material responses to score. Run collect_live.py first.')
    judge=LangchainLLMWrapper(ChatOllama(model=args.judge,base_url=args.ollama,temperature=0,num_predict=2048,num_ctx=8192))
    embeddings=LangchainEmbeddingsWrapper(OllamaEmbeddings(model=args.embedding_model,base_url=args.ollama))
    dataset=EvaluationDataset.from_list([{k:r[k] for k in ('response','retrieved_contexts','reference')} | {'user_input':r['question']} for r in valid])
    result=evaluate(dataset,metrics=[Faithfulness(llm=judge),ResponseRelevancy(llm=judge,embeddings=embeddings),
        LLMContextPrecisionWithReference(llm=judge),LLMContextRecall(llm=judge)],
        run_config=RunConfig(timeout=600,max_retries=1,max_workers=1),raise_exceptions=False)
    rows=result.to_pandas().to_dict(orient='records')
    metrics=['faithfulness','answer_relevancy','llm_context_precision_with_reference','context_recall']
    clean=[]
    for case,row in zip(valid,rows):
        scores={key:(float(row[key]) if isinstance(row.get(key),(int,float)) and math.isfinite(row[key]) else None) for key in metrics}
        clean.append({'id':case['id'],**scores})
    summary={key:sum(r[key] for r in clean if r[key] is not None)/sum(r[key] is not None for r in clean)
        if any(r[key] is not None for r in clean) else None for key in metrics}
    report={'framework':'ragas','version':'0.2.15','judge_model':args.judge,'embedding_model':args.embedding_model,
        'note':'Local model-judged scores, not human truth. Null metrics indicate failed evaluations and are never replaced with zero or a fabricated success. Off-material behavior is scored separately by collect_live.py.',
        'summary':summary,'metric_failure_counts':{key:sum(r[key] is None for r in clean) for key in metrics},'records':clean}
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(summary,indent=2));print('Saved',path)


if __name__=='__main__':main()
