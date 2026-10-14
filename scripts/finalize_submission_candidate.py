"""현재 소스·검산 자료·모델카드·실행 환경을 최종 후보 구성에 맞춰 고정한다."""
from datetime import datetime,timezone
from pathlib import Path
import json
import platform
import shutil
import sys
import psutil
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write,preservation
from src.data_source import sha256_file as sha

OUT=ROOT/'outputs/private/submission_candidate_20261013_v1'

REPLAY='''"""포함된 공간 제외 개발 예측의 날짜별·지점별 지표와 온도 오차를 검산."""
from pathlib import Path
import argparse,json,sys
import pandas as pd
HERE=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(HERE))
from src.qa633_metrics import daily_table,aggregate
from src.temperature_transfer import regression_report
from code_runtime import deny_network
parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
if args.output.exists():raise FileExistsError('Existing development replay preserved')
f=pd.read_parquet(HERE/'data/development_fixed_predictions.parquet');t=pd.read_parquet(HERE/'data/development_temperature_oof.parquet')
reports={}
with deny_network() as attempts:
 for name in ['equal_distance_mse_mae300','equal_nohistory_pair']:
  reports[name]={'temperature':regression_report(t,t[name]),'daily':{}}
  for n in [144,130,72,1]:
   d=daily_table(f,f[name],sorted(f.station.unique()),n);reports[name]['daily'][str(n)]=aggregate(d,sorted(f.station.unique()))[0]
assert attempts==[]
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps({'status':'fixed_development_replay','reports':reports,'official_score':False},ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
print('고정 개발 지표 재현 완료')
'''


def main():
    if (OUT/'candidate_manifest.json').exists():raise FileExistsError('Preserve final manifest')
    freezes=preservation()
    assert read(OUT/'validation/independent_verification.json')['status']=='submission_candidate_independent_audit_passed'
    assert read(OUT/'validation/cli_demo_receipt.json')['commands'][0]['returncode']==0
    assert read(OUT/'validation/demo_browser_receipt.json')['console_errors']==[]
    # 제출 공지의 상위 디렉터리와 실제 소스를 연결한다. 기존 code/project 사본은 이력으로 보존하되 압축에서 제외한다.
    for folder in ['src','scripts','config','tests','notebooks','docs','.github']:
        shutil.copytree(ROOT/folder,OUT/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'),dirs_exist_ok=True)
    for name in ['requirements-delivery.txt','requirements-dev.txt','AI_USAGE.md']:
        shutil.copy2(ROOT/name,OUT/name)
    fixed=ROOT/'outputs/private/qa633_development_20261013_v1/fixed_predictions.parquet'
    shutil.copy2(fixed,OUT/'data/development_fixed_predictions.parquet')
    temp_source=ROOT/'outputs/private/weather_memory_controls_20261013_v1/outer_predictions.parquet'
    temp=pd.read_parquet(temp_source,columns=['station','time','road_temp','equal_distance_mse_mae300','equal_nohistory_pair'])
    assert set(temp.station)=={'12207','12408','23205','23404','33205','33408','33207','33413','33414'}
    assert temp.time.lt('2025-03-01').all();temp.to_parquet(OUT/'data/development_temperature_oof.parquet',index=False,compression='zstd')
    shutil.copy2(ROOT/'src/offline_runtime.py',OUT/'code/code_runtime.py')
    (OUT/'code/reproduce_development.py').write_text(REPLAY,encoding='utf-8')
    # 독립 실행 예제에 필요한SciPy도 실제 사용 버전으로 고정한다.
    requirements=(OUT/'requirements.txt').read_text('utf-8');(OUT/'requirements.txt').write_text(requirements+'scipy==1.15.3\n',encoding='utf-8')
    environment=read(OUT/'environment.json')|dict(cpu=platform.processor(),logical_cpus=psutil.cpu_count(),ram_bytes=psutil.virtual_memory().total,
        training_thread_limit=2,inference_thread_limit=2)
    write(OUT/'environment_complete.json',environment)
    card=dict(name='weather12_MSE_MAE300_equal_mean',status='representative_submission_candidate_not_promoted',
        training_stations=read(OUT/'training_plan.json')['allowed_stations'],training_rows=397126,training_period_kst=['2024-11-01','2025-03-01'],
        temperature_unit='degree_Celsius',ice_output='0/1/null fixed cold_moisture criterion; uncalibrated',
        source_development=dict(rows=155257,valid_ice_rows=155118,temperature_mae_station_mean=1.200530946,
            daily_precision_defined_station_mean=.052802601704912216,daily_recall_defined_station_mean=.7746879109406813,daily_f1_defined_station_mean=.03063282424209388,
            recall_defined_stations=8,recall_all_nine_stations=None,coverage_condition_144_is_provisional=True),
        limitations=['반복 개발·새 지점 일반화 미입증','기존 온도3종 평균보다 일평균Precision 하락','입력부족은기존분류fallback 대신null',
            '도로염분·제설·실제시설범위·일사차폐 미측정','성분차이는오차범위나확률이아님','공식CSV·마감일·일부일별정책 미확정'],
        protected_labels_used=False,opened_assessment_labels_used=False,second_winter_training=False,official_score=False,model_promoted=False)
    write(OUT/'model/model_card.json',card)
    readme=(OUT/'README.md').read_text('utf-8').replace('`code/project/`는 실제 개발에 사용한 전체 코드·설정·검사·노트북·문서이며',
        '`src/`·`scripts/`·`config/`·`tests/`·`notebooks/`·`docs/`는 실제 개발에 사용한 전체 코드·설정·검사·노트북·문서이며')
    readme+='''
## 고정 개발 지표와 영상

```powershell
python -X utf8 code/reproduce_development.py --output validation/new_development_metrics.json
```

`data/development_fixed_predictions.parquet`와 `development_temperature_oof.parquet`는 허용 외부 개발9곳의 첫 겨울 공간 제외 예측과 그 개발 정답입니다. 보호·이미 개봉한 평가·둘째 겨울 정답은 없습니다. 같은 고정 예측의 지표 재현이며 새 독립 평가나 모든 과거 연구 재학습이 아닙니다. `demo/inference_demo.webm`은 실제 로컬 브라우저에서 시각을 선택하는 약12초 화면 녹화입니다. HTML과 실제CLI원문을 함께 제공합니다.

최초 기본CSV파서의 온도5행 불일치는 `float_precision='round_trip'`으로 수정했습니다. 실패한 최초CLI자료는 원본 작업 폴더에 보존하고 전달 압축에서는 제외합니다. 실제 실행에 쓰는 `code/predict.py`는 무손실 읽기와 접속 차단을 적용합니다.
'''
    (OUT/'README.md').write_text(readme,encoding='utf-8')
    render=read(OUT/'validation/pdf_render_receipt_v4.json')
    assert render['pdf_sha256']==sha(OUT/'reports/결빙_분석_제출후보_보고서.pdf')
    write(OUT/'validation/visual_review.json',dict(pdf_pages_reviewed=6,maps_reviewed=2,demo_desktop_reviewed=True,demo_mobile_reviewed=True,
        pdf_sha256=render['pdf_sha256'],pdf_v4_unchanged_pages_verified=[n for n in range(1,7) if sha(OUT/f'validation/pdf_preview_v3/page_{n}.png')==sha(OUT/f'validation/pdf_preview_v4/page_{n}.png')],
        current_pdf_visual_review_passed=True,html_sha256=sha(OUT/'demo/index.html'),map_hashes={n:sha(OUT/'figures'/n) for n in ['candidate_condition_map_500m.jpg','candidate_condition_map_1000m.jpg']}))
    excluded_prefixes=('code/project/','code/project_','validation/pdf_preview','validation/refit_models/','validation/video_raw/','validation/cli_targets',
        'validation/cli_segment','validation/cli_example.csv','validation/report_before_','validation/predict_parser_v1.py','validation/mark_artifact_operation_started.mjs')
    allowed_validation={'independent_verification.json','cli_demo_receipt.json','csv_io_fix_receipt.json','demo_browser_receipt.json','video_receipt.json','visual_review.json',
        'thermal_summary.json','thermal_independent_verification.json','thermal_decisions.json'}
    files={}
    for p in sorted(OUT.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts or p.suffix=='.pyc':continue
        rel=p.relative_to(OUT).as_posix()
        if any(rel.startswith(prefix) for prefix in excluded_prefixes):continue
        if rel.startswith('validation/') and p.name not in allowed_validation:continue
        if rel.startswith('data/weather_groups/') or rel.startswith('data/prediction_groups/') or p.suffix not in {'.log'}:
            files[rel]=dict(sha256=sha(p),bytes=p.stat().st_size)
    assert not any('secret.env' in n or n.endswith(('.hwp','.pem','.key')) for n in files)
    assert preservation()==freezes
    write(OUT/'candidate_manifest.json',dict(status='private_technical_submission_candidate',created_at_utc=datetime.now(timezone.utc).isoformat(),
        files=files,total_bytes=sum(x['bytes'] for x in files.values()),technical_preparation_complete=True,
        new_independent_performance_passed=False,official_csv_schema_confirmed=False,official_risk_grade_validated=False,
        model_promoted=False,submitted=False,protected_or_opened_assessment_labels_included=False,
        development_labels_included=True,second_winter_weather_only=True,source_development_sha256=sha(fixed),
        exclusions=list(excluded_prefixes),old_frozen_files=freezes[0],reserved_frozen_files=freezes[1]))
    print('후보 구성',len(files),sum(x['bytes'] for x in files.values()))


if __name__=='__main__':main()
