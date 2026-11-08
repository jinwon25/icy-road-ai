"""오경보 해석·재현 자료를 포함한 제출 사본을 두 채널로 검증·압축한다."""
from pathlib import Path
import sys,json,re,shutil,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,sha
from scripts.package_review_v8 import archive
from scripts.package_competition_submission import manifest
from scripts.review_submission_bundle import verify_directory
from scripts.check_markdown import inspect_documents
P=ROOT/'outputs/private';W=P/'precision_submission_update_20261106';B=W/'icy_road_model';D=W/'icy_road_documents'

def main():
    studies=['icing_precision_comparison_20261106','icing_multistate_comparison_20261106',
             'icing_local_context_20261106','icing_snow_age_20261106_checked']
    assert all(not read(P/name/'summary.json')['promote'] for name in studies)
    assert read(P/'icing_precision_review_20261106/independent_audit.json')['status']=='passed'
    checks=read(W/'delivery_checks.json');assert checks['status']=='passed'
    assert not (W/'submission_receipt.json').exists()
    ai=B/'AI_USAGE.md'
    ai.write_text(ai.read_text('utf8')+'\n추가 후보는 기상 이력, 노면상태 구분 학습, AWS·실제 DSM 입력, 적설 증가 경과 조건으로 비교했다. 정밀도·F1·재현율과 결빙 사건 보존 기준을 함께 충족한 후보가 없어 제출 모형은 유지했다. 보고서에는 현재 판정법의 오경보 분포와 해석, 재현 코드·자료를 보강했다.\n','utf8')
    pairs=[('report/analysis_report.pdf','report/analysis_report.pdf'),('AI_USAGE.md','AI_USAGE.md'),
           ('report/figures/false_alarm_states.png','figures/false_alarm_states.png'),
           ('results/evaluation/development_false_alarm_states.csv','data/development_false_alarm_states.csv'),
           ('results/evaluation/development_moisture_evidence.csv','data/development_moisture_evidence.csv')]
    for src,dst in pairs:
        (D/dst).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(B/src,D/dst)
    guide=D/'README.md'
    guide.write_text(guide.read_text('utf8')+'\n[오경보의 실제 노면상태](figures/false_alarm_states.png)와 [수분 근거](data/development_moisture_evidence.csv)를 함께 제공한다. 개발 9지점의 오경보 25,341건을 분해한 결과이며 보호 3지점의 평가와 구분한다. 원래 모형과 수치 예측은 그대로 유지했다. 분석 Notebook과 오경보 재현 코드는 모델자료 ZIP에 포함했다.\n','utf8')
    old=read(W/'original_model_manifest.json')['files']
    allowed={'README.md','AI_USAGE.md','report/analysis_report.pdf','report/analysis_report.md',
             'notebooks/analysis.ipynb','validation/delivery_checks.json','validation/report_visual_review.json',
             'validation/notebook_analysis.log'}
    unchanged=0;changed=[];removed=[]
    for relative,record in old.items():
        target=B/relative
        if not target.exists():
            assert relative in allowed,relative;removed.append(relative);continue
        if sha(target)==record['sha256']:unchanged+=1
        else:assert relative in allowed,relative;changed.append(relative)
    checks.update(unchanged_original_files=unchanged,changed_documentation_files=changed,
                  removed_obsolete_validation_logs=removed,additional_model_adopted=False,
                  report_error_analysis_added=True,core_model_and_training_data_unchanged=True,
                  numerical_predictions_unchanged=True)
    # 각 보호 대상 학습 모형과 기존 모든 입력·예측·실행 파일은 허용 목록 밖이어서 해시가 같아야 한다.
    for folder in [B,D]:
        errors=inspect_documents(folder,[p.relative_to(folder).as_posix() for p in folder.rglob('*.md')])
        assert not errors,errors
        for path in folder.rglob('*'):
            if path.is_file() and path.suffix in ['.md','.py','.json','.html','.csv','.txt','.ipynb']:
                payload=path.read_bytes()
                assert not re.search(rb'(?:github_pat_[A-Za-z0-9_]{40,}|RGAPI-[A-Za-z0-9-]{30,}|sk-[A-Za-z0-9_-]{30,})',payload),path
    # 산출물 검증 영수증을 실제 최종 상태로 갱신한다.
    (W/'delivery_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n','utf8')
    (B/'validation/delivery_checks.json').write_bytes((W/'delivery_checks.json').read_bytes())
    manifest(B,'model');manifest(D,'documents')
    archives={name:archive(folder,W/('icy_road_'+name+'.zip'),'icy_road_'+name) for name,folder in [('documents',D),('model',B)]}
    receipt=dict(status='two_channel_archives_verified',archives=archives,checks=checks,report_pages=9,
                 demo_seconds=60.32,competition_submitted=False)
    write(W/'submission_receipt.json',receipt)
    for folder in [B,D]:verify_directory(folder)
    print(json.dumps(archives,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
