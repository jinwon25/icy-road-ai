"""신규 근거 계산을 제출 폴더만으로 재현할 수 있는 실행 도구를 배치한다."""
from pathlib import Path
import shutil,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.seal_protected_weather_20261106 import W
B=W/'icy_road_model'

def main():
    (B/'src/evidence_hash.py').write_text('"""근거 파일의 SHA-256 계산."""\nimport hashlib\nfrom pathlib import Path\ndef sha(path):\n    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()\n','utf8')
    # 정답을 읽지 않고 만들어 봉인했던 기상 입력과 네트워크 원 관측을 포함한다.
    weather=B/'results/evaluation/protected_weather'
    for name in ['weather_inputs.parquet','points.csv']:
        shutil.copyfile(W/'protected_weather'/name,weather/name)
    source=ROOT/'outputs/private/releases/20261007/outputs/private/point_sources/aws.parquet'
    target=B/'data/weather_sources';target.mkdir(exist_ok=True)
    shutil.copyfile(source,target/'aws.parquet')
    # 통계 계산은 프로젝트의 비공개 경로·네트워크에 의존하지 않는다.
    base=(ROOT/'src/road_weather_transfer.py').read_text('utf8')
    statistics=base[base.index('def regression_numbers('):]
    assessment=(ROOT/'scripts/assess_protected_weather_20261106.py').read_text('utf8')
    methods=assessment[assessment.index('def resampling('):assessment.index('def main():')]
    (B/'src/evidence_analysis.py').write_text('"""같은 관측쌍 회귀 비교와 날짜 블록 민감도."""\nimport numpy as np\nimport pandas as pd\nSTATIONS=["12410","23402","33411"]\n\n'+statistics+'\n\n'+methods,'utf8')
    benchmark=r'''"""고정한 회귀와 참조 기준의 같은 관측쌍 성능을 재현한다."""
from pathlib import Path
import sys,argparse,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.evidence_analysis import evaluate,resampling

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.output.exists():raise FileExistsError('Choose a new output directory')
    a.output.mkdir(parents=True)
    f=pd.read_parquet(ROOT/'results/evaluation/temperature_benchmarks/observations_predictions.parquet')
    methods={'asos_air_reference':'asos_air_temperature','aws_air_reference':'aws_air_temperature','asos_ground_reference':'asos_ground_temp',
        'weather12_regression':'reference_temperature_12','estimated':'estimated_road_temperature_c'}
    rows=[];target='observed_road_temperature_c'
    for scope,q in [('all_temperature',f),('near_freezing_observed_pm2c',f.loc[f[target].between(-2,2)])]:
        rows.extend([dict(temperature_scope=scope,**r) for r in evaluate(q,target,methods)])
    pd.DataFrame(rows).to_csv(a.output/'metrics.csv',index=False,encoding='utf-8-sig')
    uncertainty=resampling(f,target,methods,np.random.default_rng(61107))
    pd.DataFrame(uncertainty).to_csv(a.output/'paired_day_block_sensitivity.csv',index=False,encoding='utf-8-sig')
    print(json.dumps(dict(rows=len(f),metrics=len(rows),resamples=2000,training=False),ensure_ascii=False))
if __name__=='__main__':main()
'''
    (B/'code/analyze_temperature_benchmarks.py').write_text(benchmark,'utf8')
    sensitivity=r'''"""선정 기준 75조합의 결과와 구간별 선택 유지율을 재현한다."""
from pathlib import Path
from itertools import product
import sys,argparse,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.inspection_sensitivity import inspection_scenario

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.output.exists():raise FileExistsError('Choose a new output directory')
    f=pd.read_csv(ROOT/'results/sections/section_review.csv',dtype={'seg_id':str,'prediction_group':str},float_precision='round_trip')
    overlap=pd.read_csv(ROOT/'results/inventory/overlap_sensitivity.csv',dtype={'seg_id':str},float_precision='round_trip')
    base,_=inspection_scenario(f,overlap);selected=set(base.index[base.selected]);all_ids=sorted(base.index)
    rows=[];membership=[]
    for n,(w,c,m) in enumerate(product([.6,.7,.75,.8,.9],[.6,.7,.75,.8,.9],[100,250,500]),1):
        census,s=inspection_scenario(f,overlap,w,c,m);ids=set(census.index[census.selected]);intersection=ids&selected;union=ids|selected
        rows.append(dict(scenario=n,weather_quantile=w,curve_quantile=c,margin_m=m,selected_segments=len(ids),
            retained_primary_segments=len(intersection),additional_segments=len(ids-selected),
            jaccard_with_primary=len(intersection)/len(union) if union else 1.,
            **{f'weather_threshold_{y}':v for y,v in s['weather_threshold_by_winter'].items()},curve_threshold=s['curve_threshold_deg_100m']))
        membership.append([sid in ids for sid in all_ids])
    matrix=np.array(membership,dtype=bool);a.output.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(a.output/'scenario_summary.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(matrix.T,index=all_ids,columns=[f'scenario_{i:02d}' for i in range(1,76)]).rename_axis('seg_id').to_csv(a.output/'scenario_membership.csv',encoding='utf-8-sig')
    pd.DataFrame(dict(seg_id=all_ids,selected_scenarios=matrix.sum(axis=0),declared_scenarios=75,selection_fraction=matrix.mean(axis=0))).to_csv(a.output/'segment_stability.csv',index=False,encoding='utf-8-sig')
    print(json.dumps(dict(scenarios=len(rows),primary_segments=len(selected),ice_outcomes_used=False),ensure_ascii=False))
if __name__=='__main__':main()
'''
    (B/'code/analyze_inspection_sensitivity.py').write_text(sensitivity,'utf8')
    # 같은 계산을 유지하고 루트·입출력만 제출 폴더 안의 실행 경로로 바꾼다.
    condition=(ROOT/'scripts/analyze_condition_evidence_20261106.py').read_text('utf8')
    condition=condition.replace('from src.data_source import sha256_file as sha','from src.evidence_hash import sha')
    condition=condition.replace('import sys,json,shutil','import sys,json,shutil,argparse')
    condition=condition.replace('from scripts.seal_protected_weather_20261106 import W,write','''def write(p,x):
    with p.open('x',encoding='utf8') as out:json.dump(x,out,ensure_ascii=False,indent=2,allow_nan=False);out.write('\\n')''')
    condition=condition.replace("    O=W/'condition_evidence';O.mkdir();B=W/'icy_road_model'","    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args()\n    O=a.output;O.mkdir(parents=True);B=ROOT")
    condition=condition.replace("ROOT/'outputs/private/submission_candidate_20261106_v14/exports/prediction_group_daily.csv'","ROOT/'data/prediction_group_daily.csv.gz'")
    assert "W/" not in condition and 'outputs/private/' not in condition
    (B/'code/analyze_segment_conditions.py').write_text(condition,'utf8')
    terrain=(ROOT/'scripts/derive_segment_terrain_20261106.py').read_text('utf8')
    terrain=terrain.replace('from src.data_source import sha256_file as sha','from src.evidence_hash import sha')
    terrain=terrain.replace('import json,sys,time','import json,sys,time,argparse')
    terrain=terrain.replace('from scripts.seal_protected_weather_20261106 import W,write','''def write(p,x):
    with p.open('x',encoding='utf8') as out:json.dump(x,out,ensure_ascii=False,indent=2,allow_nan=False);out.write('\\n')''')
    terrain=terrain.replace("    O=W/'terrain_context';O.mkdir()","    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args()\n    O=a.output;O.mkdir(parents=True)")
    terrain=terrain.replace("ROOT/'outputs/private/releases/20261007/outputs/private/external/copernicus_dem'","ROOT/'data/copernicus_dem'")
    terrain=terrain.replace("W/'icy_road_model/results/weather/weather_segments_500m.csv'","ROOT/'results/weather/weather_segments_500m.csv'")
    assert "=W/" not in terrain and 'outputs/private/' not in terrain
    (B/'code/derive_terrain_context.py').write_text(terrain,'utf8')
    print('신규 분석 실행 도구 4개와 오프라인 원본 입력 배치 완료',flush=True)

if __name__=='__main__':main()
