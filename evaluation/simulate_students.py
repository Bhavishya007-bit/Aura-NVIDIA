"""Seeded multi-session simulation using Aura's actual BKT update rule.

Latent learning is a synthetic assumption, not measured human learning.
"""
import argparse
import json
from pathlib import Path
import random
import statistics
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.learning import update_probability, recommended_difficulty


def simulate(seed=42, students=60, sessions=8):
    if not 1 <= students <= 10000 or not 1 <= sessions <= 100: raise ValueError('Simulation size out of bounds.')
    profiles={'new': [.10,.10,.10], 'uneven':[.75,.15,.45], 'experienced':[.8,.7,.85]}
    records=[]
    for policy in ('adaptive','random'):
        for index in range(students):
            name=list(profiles)[index%3]; rng=random.Random(seed+index)
            latent=list(profiles[name]); initial_latent=list(latent); mastery=[.2]*3; counts=[0]*3
            bank=[set() for _ in range(3)]; repeats=0; attempts=0; rows=[]
            for session in range(sessions):
                for _ in range(5):
                    # Three diagnostic items before adaptive selection, once per learner.
                    diagnostic=attempts<3
                    topic=attempts if diagnostic else (min(range(3),key=lambda t:mastery[t]) if policy=='adaptive' else rng.randrange(3))
                    difficulty=recommended_difficulty(mastery[topic],counts[topic])
                    penalty={'beginner':0,'intermediate':.08,'advanced':.16}[difficulty]
                    probability=max(.02,min(.98,latent[topic]*.9+(1-latent[topic])*.05-penalty))
                    correct=rng.random()<probability
                    unused=[q for q in range(12) if q not in bank[topic]]
                    question=rng.choice(unused) if unused else rng.randrange(12)
                    repeats+=int(question in bank[topic]);bank[topic].add(question)
                    mastery[topic]=update_probability(mastery[topic],correct,'numerical',diagnostic)
                    if not diagnostic: latent[topic]+= .035*(1-latent[topic])  # declared synthetic learning assumption
                    counts[topic]+=1;attempts+=1
                rows.append({'session':session+1,'estimated_mastery':list(mastery),'latent_knowledge':list(latent),'questions':attempts})
            records.append({'policy':policy,'profile':name,'student':index,'estimated_mastery_gain':statistics.mean(mastery)-.2,
                'synthetic_latent_gain':statistics.mean(latent)-statistics.mean(initial_latent),
                'repetition_rate':repeats/attempts,'sessions':rows})
    groups=[]
    for policy in ('adaptive','random'):
        for profile in profiles:
            subset=[r for r in records if r['policy']==policy and r['profile']==profile]
            if not subset: continue
            groups.append({'policy':policy,'profile':profile,'students':len(subset),
                **{key:statistics.mean(r[key] for r in subset) for key in ('estimated_mastery_gain','synthetic_latent_gain','repetition_rate')}})
    return {'seed':seed,'students_per_policy':students,'sessions':sessions,'questions_per_session':5,
        'question_bank_per_topic':12,'assumptions':'Synthetic response probabilities; synthetic learning rate .035; production BKT rule and difficulty thresholds. Question-bank exhaustion intentionally allows repeats. This tests policy behavior, not measured learner gains or the production question generator.',
        'summary':groups,'student_runs':records}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--seed',type=int,default=42);parser.add_argument('--students',type=int,default=60)
    parser.add_argument('--sessions',type=int,default=8);parser.add_argument('--output',default='evaluation/results/student_simulation.json')
    args=parser.parse_args();result=simulate(args.seed,args.students,args.sessions)
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2))
    print(json.dumps(result['summary'],indent=2));print('Saved',path)
