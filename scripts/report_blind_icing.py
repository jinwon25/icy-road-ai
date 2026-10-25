"""입력 분포와 감사 완료된 독립 평가를 공유 가능한 집계 그림으로 만든다."""
import argparse
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.blind_icing_validation import DEFAULT,PRIVATE,read,write,verify
from src.anchored_icing import linear_features
from src.data_source import sha256_file as sha

OUT=PRIVATE/'blind_icing_report_20261025_v1'
LABELS={'asos_zero':'ASOS 0°C 기준선','air_minus_half':'ASOS -0.5°C 대조','logit_day_anchor1':'회귀 주 후보','hgb_day_anchor1':'HGB 보조 후보'}
SITE_NAMES={'33402':'이천휴','33406':'진천터널외부','12213':'성암교','23411':'쌍암천교'}


def style():
    fonts={f.name for f in font_manager.fontManager.ttflist}
    for font in ['Malgun Gothic','Noto Sans CJK KR','NanumGothic']:
        if font in fonts:plt.rcParams['font.family']=font;break
    plt.rcParams['axes.unicode_minus']=False
    plt.rcParams['axes.spines.top']=False;plt.rcParams['axes.spines.right']=False


def inputs():
    verify(DEFAULT);OUT.mkdir(exist_ok=True)
    if (OUT/'input_profile.json').exists():raise FileExistsError('Preserve profile')
    train=pd.read_parquet(DEFAULT/'training.parquet');query=pd.read_parquet(DEFAULT/'inputs.parquet')
    assert not {'ice','road_temp'}&set(query)
    x=linear_features(train.loc[train.available]);z=linear_features(query);rows=[]
    for station,idx in query.groupby('station').groups.items():
        for col in x:
            a=x[col].dropna();b=z.loc[idx,col].dropna()
            rows.append(dict(station=station,feature=col,training_valid=len(a),query_valid=len(b),
                query_missing_fraction=float(z.loc[idx,col].isna().mean()),
                training_min=float(a.min()) if len(a) else None,training_max=float(a.max()) if len(a) else None,
                outside_training_range=int((b.lt(a.min())|b.gt(a.max())).sum()) if len(a) else len(b)))
    pd.DataFrame(rows).to_csv(OUT/'input_distribution.csv',index=False)
    q=pd.read_csv(DEFAULT/'weather_quality.csv',dtype={'station':str}).loc[lambda f:f.source.eq('new_weather')]
    cols=['air_temp','ground_temp','humidity','dewpoint_obs','wind_speed','rain_mm','snow_cm','solar_mj_m2','soil5cm']
    labels=['기온','지면온도','습도','이슬점','풍속','강수','적설','일사','지중 5cm']
    points=pd.read_csv(DEFAULT/'points.csv',dtype={'station':str,'asos_station':str})
    q=q.groupby('station')[[c+'_coverage' for c in cols]].mean()
    wx=points.asos_station.tolist();matrix=q.loc[wx].to_numpy()*100
    style();fig,ax=plt.subplots(figsize=(12,4.7));ax.imshow(matrix,vmin=0,vmax=100,cmap='Blues',aspect='auto')
    ax.set_xticks(range(len(cols)),labels);ax.set_yticks(range(len(points)),[SITE_NAMES[s] for s in points.station])
    for i in range(len(points)):
        for j in range(len(cols)):ax.text(j,i,f'{matrix[i,j]:.1f}%',ha='center',va='center',color='white' if matrix[i,j]>65 else '#123047',fontsize=10)
    ax.set_title('새 4지역의 두 겨울 기상 가용률',loc='left',fontsize=16,pad=18)
    fig.text(.02,.025,'기온·지면온도·습도·이슬점은 모두 100%. 희소 강수·적설·일사의 결측은 0으로 채우지 않음.\n자체 범위·시각 검사이며 제공기관 QC 인증이나 도로 센서 정답의 가용률을 뜻하지 않음.',fontsize=10)
    fig.tight_layout(rect=(0,.12,1,1));fig.savefig(OUT/'blind_weather_quality.png',dpi=160);plt.close(fig)
    write(OUT/'input_profile.json',dict(status='inputs_profiled_without_new_labels',features=15,sites=4,
        new_labels_read=False,source_sha256=sha(DEFAULT/'inputs.parquet'),files={p.name:sha(p) for p in OUT.iterdir() if p.is_file()}))
    print('INPUT PROFILE COMPLETE',flush=True)


def results():
    verify(DEFAULT);s=read(DEFAULT/'summary.json');audit=read(DEFAULT/'result_audit.json')
    assert audit['status']=='passed' and audit['summary_sha256']==sha(DEFAULT/'summary.json')
    OUT.mkdir(exist_ok=True)
    if (OUT/'result_profile.json').exists():raise FileExistsError('Preserve report')
    rows=[]
    for n in LABELS:
        r=s['reports'][n];m=r['144'];rows.append(dict(candidate=n,f1=m['f1_fixed_population'],precision=m['precision_available_station_mean'],
            recall=m['recall_available_station_mean'],first=r['2024']['f1_fixed_population'],second=r['2025']['f1_fixed_population'],
            fp=m['fp'],fn=m['fn'],**r['events']))
    table=pd.DataFrame(rows);table.to_csv(OUT/'candidate_metrics.csv',index=False)
    style();fig,axes=plt.subplots(1,3,figsize=(14,5.2));colors=['#667085','#98a2b3','#16708c','#6f65ab']
    for ax,col,title in zip(axes,['f1','first','second'],['두 겨울 통합','첫 겨울','둘째 겨울']):
        v=table[col].to_numpy();ax.barh(range(4),v,color=colors);ax.invert_yaxis()
        ax.set_yticks(range(4),[LABELS[n] for n in table.candidate] if col=='f1' else ['']*4)
        ax.locator_params(axis='x',nbins=4)
        high=max(v.max(),.001);ax.set_xlim(0,high*1.32);ax.set_title(title);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
        for i,value in enumerate(v):ax.text(value+high*.025,i,f'{value:.5f}',va='center',fontsize=10)
    fig.suptitle('정답 수집 전 예측을 고정한 새 4지역의 일별 F1',x=.02,ha='left',fontsize=16)
    gates=s['primary_gates'];failed=', '.join(k for k,v in gates.items() if not v)
    fig.text(.02,.07,'주 후보 채택 조건 미통과: 재현율 하락·8사건 손실·2지역 악화·관측 부족·좌표 불일치',fontsize=11,color='#9c2929')
    fig.text(.02,.025,'고정 4지점 평균 · 하루 144개 공통 유효 슬롯 · 새 지역/기존 두 겨울 · 공식 대회 점수 아님',fontsize=10)
    fig.tight_layout(rect=(0,.13,1,.91),w_pad=3);fig.savefig(OUT/'blind_icing_results.png',dpi=160);plt.close(fig)
    write(OUT/'result_profile.json',dict(status='audited_results_summarized',summary_sha256=sha(DEFAULT/'summary.json'),
        primary_success=s['primary_success'],failed_gates=failed,table_sha256=sha(OUT/'candidate_metrics.csv'),figure_sha256=sha(OUT/'blind_icing_results.png'),code_sha256=sha(Path(__file__))))
    print(table.to_string(index=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('phase',choices=['inputs','results']);parser.add_argument('--output',type=Path,default=OUT);args=parser.parse_args()
    OUT=args.output.resolve()
    if not OUT.is_relative_to((ROOT/'outputs/private').resolve()):raise ValueError('Private output directory required')
    {'inputs':inputs,'results':results}[args.phase]()
