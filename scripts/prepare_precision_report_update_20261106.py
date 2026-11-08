"""기존 제출물은 보존하고 오경보 분석을 보강할 별도 사본을 만든다."""
from pathlib import Path
import json,shutil
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'outputs/private'
source=P/'competition_submission/icy_road_model';W=P/'precision_submission_update_20261106'
assert not W.exists()
W.mkdir();B=W/'icy_road_model';D=W/'icy_road_documents'
def ignore(path,names):
    excluded={'__pycache__','local_review'}
    if Path(path)==source:excluded.add('manifest.json')
    return [name for name in names if name in excluded]
shutil.copytree(source,B,ignore=ignore)
shutil.copytree(P/'competition_submission/icy_road_documents',D)
shutil.copyfile(source/'manifest.json',W/'original_model_manifest.json')
shutil.copyfile(P/'competition_submission/submission_receipt.json',W/'original_submission_receipt.json')
shutil.copyfile(D/'manifest.json',W/'original_documents_manifest.json')
# 신규 사본의 생성물만 작업 폴더로 옮기며 원 제출본은 변경하지 않는다.
for path,target in [(B/'report/analysis_report.pdf',W/'original_analysis_report.pdf'),
                    (D/'manifest.json',W/'copied_documents_manifest.json')]:
    assert path.resolve().is_relative_to(W.resolve()) and target.resolve().is_relative_to(W.resolve())
    path.replace(target)
columns=['station','time','group','winter','ice','road_temp','temperature_both','physical_both',
         'aws_dewpoint','aws_age_minutes','rain15_max_3h','asos_snow_cm']
f=pd.read_parquet(P/'two_winter_models_20261024_v1/runtime_predictions.parquet',columns=columns)
labels=pd.read_parquet(P/'icing_state_targets_20261106/targets.parquet',columns=['station','time','state_raw'])
assert not set(f.station)&{'12410','33411','23402','33402','33406','12213','23411'}
f=f.merge(labels,on=['station','time'],validate='one_to_one')
f.to_parquet(B/'results/evaluation/development_predictions.parquet',index=False,compression='zstd')
for src,dest in [('false_alarm_surface_states.csv','development_false_alarm_states.csv'),
                 ('water_sources.csv','development_moisture_evidence.csv')]:
    shutil.copyfile(P/'icing_precision_diagnosis_20261106'/src,B/'results/evaluation'/dest)
summary=json.loads((P/'icing_precision_diagnosis_20261106/summary.json').read_text('utf8'))
(B/'technical/development_error_analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf8')
print('DRAFT',B,flush=True)
