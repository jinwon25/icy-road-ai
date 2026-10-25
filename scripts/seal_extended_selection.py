"""선택안과 독립 감사 영수증을 연결한 뒤에만 제출 구성에 사용한다."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import preservation


def read(p):return json.loads(p.read_text('utf-8'))


def main():
    p=argparse.ArgumentParser();p.add_argument('--comparison',required=True,type=Path);p.add_argument('--audit',action='append',required=True,type=Path);a=p.parse_args()
    target=a.comparison/'selection.json'
    if target.exists():raise FileExistsError('Preserve sealed selection')
    proposed=read(a.comparison/'selection_proposal.json');summary=read(a.comparison/'summary.json')
    assert proposed==summary['selection'] and proposed['status']=='selection_pending_model_audits'
    assert sha(ROOT/'config/extended_final_selection_20261024.json')==proposed['comparison_plan_sha256']
    assert sha(ROOT/'config/solar_loss_pair_20261024.json')==proposed['loss_pair_plan_sha256']
    audited={};audit_files=[]
    for path in a.audit:
        receipt=read(path/'receipt.json');dispatch=read(path/'feature_dispatch_receipt.json')
        assert receipt['status']=='saved_models_replayed_and_verified' and not receipt['protected_labels_read']
        assert dispatch['audit_receipt_sha256']==sha(path/'receipt.json')
        for name,digest in dispatch['signatures'].items():assert sha(ROOT/name)==digest
        audit_files.append((path/'receipt.json').resolve().relative_to(ROOT).as_posix())
        audit_files.append((path/'feature_dispatch_receipt.json').resolve().relative_to(ROOT).as_posix())
        for item in receipt['checks']:audited[item['candidate']]=item
    for component in proposed['components']:
        name=component['name'];folder=ROOT/component['folder'];assert audited[name]['predictions_sha256']==component['predictions_sha256']==sha(folder/'predictions.parquet')
        assert audited[name]['report_sha256']==sha(folder/'report.json')
        assert audited[name]['models']==4 and audited[name]['prediction_rows']==310777
    class_audits=[]
    for prefix,models in [('terrain',20),('thermal',40)]:
        folder=ROOT/f'outputs/private/{prefix}_classification_audit_20261024_v1';receipt=read(folder/'receipt.json')
        assert receipt['status']=='classification_models_nested_selection_and_daily_f1_verified' and len(receipt['model_checks'])==models
        assert receipt['search_summary_sha256']==sha(ROOT/f'outputs/private/{prefix}_classification_20261024_v1/summary.json')
        class_audits.append(dict(receipt=(folder/'receipt.json').relative_to(ROOT).as_posix(),sha256=sha(folder/'receipt.json')))
    assert preservation()==(47,549)
    result=dict(proposed,status='audited_final_selection',saved_model_audits=audit_files,classification_audits=class_audits,
        comparison_summary_sha256=sha(a.comparison/'summary.json'),sealing_code_sha256=sha(Path(__file__)))
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    print(result['selected'],result['temperature_report']['regression']['pooled']['mae'],flush=True)


if __name__=='__main__':main()
