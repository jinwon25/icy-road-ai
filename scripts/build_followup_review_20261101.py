"""추가36적합·서리 반증·명시적 결빙 프로필·기상 탐색의 검토 자료를 만든다."""
from pathlib import Path
import json
import shutil
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import nbformat as nb
import pandas as pd
from PIL import Image as PILImage

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha

P=ROOT/'outputs/private';OUT=P/'followup_review_20261101_v1'
LABELS={'stable_history':'현재 v10','thermo_residual':'물리 입력·직접 잔차','thermo_logit':'물리 입력·logit','catboost_history':'CatBoost','half_hgb_catboost':'HGB·CatBoost 1:1 평균'}
STUDIES=['weather_thermodynamics_20261101_v1','weather_catboost_20261101_v1','frost_icing_20261101_v1']


def main():
    if OUT.exists():raise FileExistsError('Preserve followup review')
    read=lambda p:json.loads(p.read_text(encoding='utf8'))
    sources={};studies={}
    for name in STUDIES:
        folder=P/name;summary=read(folder/'summary.json');audit=read(folder/'independent_verification.json')
        assert audit['status']=='passed' and audit['summary_sha256']==sha(folder/'summary.json')
        studies[name]=summary;sources[name]=sha(folder/'summary.json');sources[name+'_audit']=sha(folder/'independent_verification.json')
    assert all(not studies[n]['accepted_candidates'] for n in STUDIES[:2])
    profile=P/'competition_profile_review_20261101_v1';profiles=read(profile/'summary.json')
    assert profiles['status']=='explicit_competition_profiles_verified' and profiles['protected_missing_rows_preserved']==18
    browser=P/'weather_explorer_validation_20261101_v4';browserproof=read(browser/'summary.json');visual=read(browser/'visual_review.json')
    assert browserproof['status']=='passed' and visual['status']=='passed' and visual['summary_sha256']==sha(browser/'summary.json')
    sources.update(profiles=sha(profile/'summary.json'),browser=sha(browser/'summary.json'),visual=sha(browser/'visual_review.json'))
    records=[];global_values={};baseline={}
    for name in STUDIES[:2]:
        for mode,report in studies[name]['reports'].items():
            if mode in baseline:assert baseline[mode]==report['baseline']
            else:baseline[mode]=report['baseline']
            global_values.setdefault(mode,{})['stable_history']=report['baseline']['pooled']['mae']
            for kind,result in report['candidates'].items():
                global_values[mode][kind]=result['metrics']['pooled']['mae']
                for scope,values in result['metrics'].items():
                    for key,stats in (values.items() if scope in ['winters','regions'] else [('all',values)]):
                        records.append(dict(model=kind,label=LABELS[kind],validation=mode,scope=scope,key=key,**stats))
    for mode,report in baseline.items():
        for scope,values in report.items():
            for key,stats in (values.items() if scope in ['winters','regions'] else [('all',values)]):
                records.append(dict(model='stable_history',label=LABELS['stable_history'],validation=mode,scope=scope,key=key,**stats))
    OUT.mkdir();metrics=pd.DataFrame(records);assert len(metrics)==80
    metrics.to_csv(OUT/'weather_comparison_metrics.csv',index=False,encoding='utf-8-sig')
    icing=[]
    for name,report in profiles['reports'].items():
        for scope,values in [('all',{'all':report['all']}),('winters',report['winters']),('regions',report['regions'])]:
            for key,stats in values.items():icing.append(dict(model=name,scope=scope,key=key,**{k:v for k,v in stats.items() if not isinstance(v,dict)}))
    pd.DataFrame(icing).to_csv(OUT/'icing_profile_metrics.csv',index=False,encoding='utf-8-sig')
    font_manager.fontManager.addfont('C:/Windows/Fonts/malgun.ttf');plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False})
    fig,axes=plt.subplots(1,2,figsize=(11.5,4.5),layout='constrained')
    kinds=list(LABELS);colors=['#234b63','#3f8c8c','#a9c7bf','#ce8b42','#906b96']
    for ax,mode,title in zip(axes,['joint','spatial'],['지역·겨울 동시 제외','두 겨울의 지역 제외']):
        values=[global_values[mode][k] for k in kinds]
        ax.barh(range(5),values,color=colors,height=.62);ax.set_yticks(range(5),[LABELS[k] for k in kinds]);ax.invert_yaxis()
        ax.axvline(values[0]*.98,color='#a34f39',ls='--',lw=1,label='2% 개선 기준')
        for i,v in enumerate(values):ax.text(v+.05,i,f'{v:.4f}',va='center',fontsize=9)
        ax.set(xlim=(0,max(values)*1.18),xlabel='상대습도 MAE (%p)',title=title);ax.spines[['top','right']].set_visible(False);ax.grid(axis='x',alpha=.15)
    axes[0].legend(loc='lower right',fontsize=9)
    fig.suptitle('추가 입력·다른 나무 구조가 안정적인 개선을 보장하지 않았다',fontsize=14)
    fig.savefig(OUT/'weather_comparison.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10.6,3.5),layout='constrained')
    labels=['기존 온도·수분(v2)','기온 0°C · F1 우선 검토'];names=['preserved_v2','asos_zero']
    for j,(year,title) in enumerate([('2024','2024/25'),('2025','2025/26')]):
        vals=[profiles['reports'][n]['winters'][year]['f1_fixed_population'] for n in names]
        axes[j].bar(range(2),vals,color=['#397b82','#c98a42'],width=.5);axes[j].set_xticks(range(2),labels,fontsize=9)
        axes[j].set(ylim=(0,.085),ylabel='일별 지점 평균 F1',title=title)
        for i,v in enumerate(vals):axes[j].text(i,v+.002,f'{v:.6f}',ha='center',fontsize=10)
        axes[j].spines[['top','right']].set_visible(False);axes[j].grid(axis='y',alpha=.15)
    fig.suptitle('F1 우선 선택의 이득과 손해를 함께 표시',fontsize=14)
    fig.savefig(OUT/'icing_profiles.png',dpi=180);plt.close(fig)
    with PILImage.open(browser/'desktop.png') as screenshot:
        screenshot.crop((0,190,screenshot.width,min(1210,screenshot.height))).save(OUT/'weather_explorer_preview.png')
    for source,target in [(OUT/'weather_comparison.png',ROOT/'docs/images/weather_followup_20261101.png'),
        (OUT/'icing_profiles.png',ROOT/'docs/images/competition_profiles_20261101.png'),
        (OUT/'weather_explorer_preview.png',ROOT/'docs/images/weather_explorer_20261101.png')]:
        if target.exists():raise FileExistsError('Preserve reviewed figure')
        shutil.copy2(source,target)
    notebook=nb.v4.new_notebook(metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},cells=[
        nb.v4.new_markdown_cell('''# 추가 검증과 실행 목적의 확인

현재 습도 모형은 v10을 유지합니다. 추가36적합은 두 제외 검증의 모든 기준을 통과하지 못했습니다.
F1 우선 프로필은 이미 알려진 기온 기준선을 명시한 대안으로, 새 독립 모델 개선이 아닙니다.
GUI는 관측 정확도·결빙확률을 뜻하지 않는 구간 추정과 입력 품질을 검토합니다.'''),
        nb.v4.new_code_cell('''from pathlib import Path
import json, hashlib, subprocess, sys, uuid
import pandas as pd
from IPython.display import display, Image
ROOT=next(p for p in [Path.cwd(),*Path.cwd().parents] if (p/'extended_training_plan.json').exists() or (p/'config/weather_catboost_20261101.json').exists())
PACKAGED=(ROOT/'extended_training_plan.json').exists()
P=ROOT/'research/latest' if PACKAGED else ROOT/'outputs/private'
read=lambda p:json.loads(p.read_text(encoding='utf8'))
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name in ['weather_thermodynamics_20261101_v1','weather_catboost_20261101_v1','frost_icing_20261101_v1']:
    audit=read(P/name/'independent_verification.json')
    assert audit['status']=='passed' and audit['summary_sha256']==digest(P/name/'summary.json')
table=pd.read_csv(P/'followup_review_20261101_v1/weather_comparison_metrics.csv')
assert len(table)==80
display(table.loc[table.scope.eq('pooled')])
display(Image(filename=str(ROOT/'docs/images/weather_followup_20261101.png')))'''),
        nb.v4.new_code_cell('''profile=read(P/'competition_profile_review_20261101_v1/summary.json')
assert profile['status']=='explicit_competition_profiles_verified' and profile['protected_missing_rows_preserved']==18
display(pd.read_csv(P/'followup_review_20261101_v1/icing_profile_metrics.csv'))
display(Image(filename=str(ROOT/'docs/images/competition_profiles_20261101.png')))
print('겨울별 반례·정밀도·재현율·사건과 함께 판단합니다. 공식 점수가 아닙니다.')'''),
        nb.v4.new_code_cell('''viewer=P/'weather_explorer_20261101_v2'
assert viewer.joinpath('index.html').exists()
proof=read(P/'weather_explorer_validation_20261101_v4/summary.json')
assert proof['status']=='passed' and proof['html_sha256']==digest(viewer/'index.html')
assert not proof['network_requests'] and not proof['page_errors']
display(Image(filename=str(ROOT/'docs/images/weather_explorer_20261101.png')))
print('브라우저에서 열 파일:',viewer/'index.html')
print('구간 선택·두 겨울 비교·품질 필터·CSV 240행 다운로드를 검증했습니다.')'''),
        nb.v4.new_code_cell('''bundle=ROOT if PACKAGED else ROOT/'outputs/private/submission_candidate_20261101_v10'
local=ROOT/'local_review' if PACKAGED else P/'followup_review_20261101_v1/local_review'
local.mkdir(parents=True,exist_ok=True)
output=local/('profile_'+uuid.uuid4().hex+'.csv')
command=[sys.executable,str(ROOT/'scripts/predict_competition_profile.py'),'--bundle',str(bundle),'--input',str(bundle/'data/weather_example.csv'),'--output',str(output),'--icing-profile','score_priority_asos_zero','--output-start','2024-12-15','--output-end','2024-12-16']
run=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf8')
assert run.returncode==0,run.stdout+run.stderr
actual=pd.read_csv(output,dtype={'station':str,'predicted_ice':'Int64'},parse_dates=['time'],float_precision='round_trip')
expected=pd.read_csv(bundle/'data/example_predictions.csv',dtype={'station':str,'predicted_ice':'Int64'},parse_dates=['time'],float_precision='round_trip')
pd.testing.assert_series_equal(actual.estimated_road_temp_c,expected.estimated_road_temp_c,check_exact=True)
assert len(actual)==144 and actual.predicted_ice.isna().equals(expected.predicted_ice.isna())
assert actual.icing_policy.eq('score_priority_asos_zero_v1').all()
print('실제 F1 우선 CLI: 144행·온도·결측 보존 확인',output)''')])
    nb.validate(notebook);target=ROOT/'notebooks/followup_review_20261101.ipynb'
    if target.exists():raise FileExistsError('Preserve notebook')
    nb.write(notebook,target)
    receipt=dict(status='followup_review_built',sources=sources,weather_metric_rows=len(metrics),icing_metric_rows=len(icing),
        notebook_code_cells=4,notebook_sha256=sha(target),global_weather_mae=global_values,
        files={p.name:sha(p) for p in OUT.iterdir() if p.is_file()},source_sha256=sha(Path(__file__)),production_model_changed=False)
    (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('FOLLOWUP REVIEW BUILT',len(metrics),len(icing),flush=True)


if __name__=='__main__':main()
