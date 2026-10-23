"""Serve only aggregate synthetic eval metrics, never student prompts or run traces."""
from collections import Counter
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LABELS=('fully_covered','partially_covered','not_covered')


def calibration_summary(packet=None):
    required=30
    rows=packet.get('records',[]) if isinstance(packet,dict) else []
    expected_ids={f'cal-{i:02d}' for i in range(1,31)}
    valid=isinstance(rows,list) and len(rows)==required and all(isinstance(r,dict) and isinstance(r.get('id'),str) for r in rows) and {r['id'] for r in rows}==expected_ids
    reviewed=[r for r in rows if isinstance(r,dict) and r.get('human_label') in LABELS and r.get('reviewed_by')=='human'] if valid else []
    agreement=sum(r.get('predicted')==r['human_label'] for r in reviewed)/len(reviewed) if reviewed else None
    gold=Counter(r['human_label'] for r in reviewed); pred=Counter(r.get('predicted') if r.get('predicted') in LABELS else 'unknown' for r in reviewed)
    chance=sum(gold[label]*pred[label] for label in LABELS)/len(reviewed)**2 if reviewed else 0
    kappa=(agreement-chance)/(1-chance) if agreement is not None and chance<1 else None
    matrix={label:{prediction:0 for prediction in (*LABELS,'unknown')} for label in LABELS}
    for row in reviewed:
        matrix[row['human_label']][row.get('predicted') if row.get('predicted') in LABELS else 'unknown']+=1
    covered=sum(gold[label] for label in ('fully_covered','partially_covered'))
    false_absences=sum(matrix[label]['not_covered'] for label in ('fully_covered','partially_covered'))
    false_absence_rate=false_absences/covered if covered else None
    live=isinstance(packet,dict) and packet.get('mode')=='live_synthetic' and isinstance(packet.get('model'),str) and bool(packet['model']) and all(r.get('predicted') in LABELS for r in reviewed)
    ready=live and len(reviewed)==required and agreement is not None and agreement>=.8 and kappa is not None and kappa>=.6 and false_absence_rate is not None and false_absence_rate<=.05
    return {'reviewed':len(reviewed),'required':required,'agreement':agreement,'kappa':kappa,'ready':ready,
        'confusion_matrix':matrix,'false_absence_rate':false_absence_rate,
        'notice':'Ready for limited use on this small synthetic calibration set.' if ready else 'Do not trust an LLM judge yet: collect 30 live outputs and have a person label them. Targets: agreement ≥80%, Cohen kappa ≥0.60, false not-covered rate ≤5% on covered questions.'}



def evaluation_status():
    report_path=ROOT/'evaluation/reports/phase4.json'
    calibration_path=ROOT/'evaluation/results/judge_calibration.json'
    try: report=json.loads(report_path.read_text(encoding='utf-8'))
    except (OSError,ValueError): report={}
    if not isinstance(report,dict): report={}
    try: packet=json.loads(calibration_path.read_text(encoding='utf-8'))
    except (OSError,ValueError): packet=None
    return {'mode':'controlled_offline','checked_at':report.get('checked_at'),
        'checks':[{k:row[k] for k in ('category','passed','total')} for row in report.get('summary',[]) if isinstance(row,dict) and all(k in row for k in ('category','passed','total'))],
        'calibration':calibration_summary(packet),
        'limitations':['These are controlled synthetic regressions, not live model accuracy or a learning-gain claim.',
                      'Run the opt-in live collector and review 30 judge outputs before using judge scores as evidence.']}
