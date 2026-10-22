"""Benchmark the authenticated production API on uploaded, annotated material."""
import argparse
import getpass
import json
import os
from pathlib import Path
import statistics
import time
import re

from evaluation.evaluate_coverage import metrics as coverage_metrics

import requests


def location_metrics(actual, expected):
    actual=list(dict.fromkeys(actual));expected=set(expected)
    matches=len(set(actual)&expected)
    return {'location_precision':matches/len(actual) if actual else 0,
            'location_recall':matches/len(expected) if expected else None,
            'reciprocal_rank':next((1/(i+1) for i,v in enumerate(actual) if v in expected),0) if expected else None}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--api',default='http://127.0.0.1:8000')
    parser.add_argument('--course-id',type=int,required=True);parser.add_argument('--source-id',type=int,required=True)
    parser.add_argument('--email');parser.add_argument('--cases',default=str(Path(__file__).with_name('course_cases.json')))
    parser.add_argument('--split',choices=['development','holdout'],default='development')
    parser.add_argument('--output',default='evaluation/results/live_responses.json')
    args=parser.parse_args();base=args.api.rstrip('/'); token=os.getenv('AURA_BENCHMARK_TOKEN','')
    if not token:
        email=args.email or input('Your Aura account email: ').strip()
        auth=requests.post(base+'/auth/login',json={'email':email,'password':getpass.getpass('Aura password (hidden): ')},timeout=30)
        auth.raise_for_status();token=auth.json()['access_token']
    cases=[case for case in json.loads(Path(args.cases).read_text()) if case.get('split','development') == args.split];records=[]
    for case in cases:
        start=time.perf_counter()
        try:
            response=requests.post(base+'/chat',headers={'Authorization':'Bearer '+token},json={
                'course_id':args.course_id,'source_id':args.source_id,'question':case['question'],
                'answer_mode':'intelligence','top_k':6},timeout=(5,1200))
            response.raise_for_status();data=response.json()
            sources=data.get('sources',[]);positions=[s.get('page') or s.get('slide') for s in sources if s.get('page') or s.get('slide')]
            validation=data.get('citation_validation',{})
            coverage=data.get('coverage',{}).get('status','unknown')
            sections=data.get('sections',[])
            sourced=[s for s in sections if s.get('kind')=='sourced']
            beyond=[s for s in sections if s.get('kind')=='beyond']
            numbers=[int(a or b) for s in sourced for a,b in re.findall(r'\[(\d+)\]|【(\d+)】',s.get('text',''))]
            provenance={
                'citations_resolve':all(1<=number<=len(sources) for number in numbers),
                'no_document_citations_in_beyond':all(not re.search(r'\[\d+\]|【\d+】',s.get('text','')) for s in beyond),
                'sourced_claims_model_checked':validation.get('source_validation',{}).get('valid') is True if sourced else None,
                'note':'Source support is the runtime judge decision, not independent human truth. Empty sections do not demonstrate provenance success.'}
            records.append({**case,'response':data['answer'],'retrieved_contexts':[s.get('content','') for s in sources],
                'source_locations':positions,'latency_seconds':time.perf_counter()-start,
                'citation_validation':validation,'predicted_coverage':coverage,'sections':sections,
                'clarifying_question':data.get('clarifying_question'),'depth':data.get('depth'),
                'provenance':provenance,
                **location_metrics(positions,case['expected_positions'])})
        except (requests.RequestException,ValueError,KeyError) as error:
            records.append({**case,'error':type(error).__name__,'latency_seconds':time.perf_counter()-start})
        print(case['id'], 'completed' if 'response' in records[-1] else 'FAILED',flush=True)
    covered=[r for r in records if not r['off_material'] and 'response' in r]
    summary={key:statistics.mean(r[key] for r in covered) if covered else None for key in ('location_precision','location_recall','reciprocal_rank','latency_seconds')}
    summary.update(coverage=coverage_metrics([{'expected':r.get('expected_coverage','not_covered' if r['off_material'] else 'fully_covered'),
        'predicted':r.get('predicted_coverage','unknown'),'latency_seconds':r['latency_seconds']} for r in records]),
        completed=sum('response' in r for r in records),failed=sum('error' in r for r in records))
    output={'mode':'live_authenticated_production_api','course_id':args.course_id,'source_id':args.source_id,
        'split':args.split,'note':'Coverage labels apply to the complete four-page demo fixture. Coverage errors remain unknown. Provenance source support is model judged and needs human calibration. No live results are fabricated.',
        'summary':summary,'records':records}
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(output,indent=2));print('Saved',path);print(json.dumps(summary,indent=2))


if __name__=='__main__':main()

