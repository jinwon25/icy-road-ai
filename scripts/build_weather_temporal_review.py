"""완료·검산된 시공간 검증에서 수치표·그림·실행 노트북과 검토 기록을 만든다."""
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import nbformat as nb
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_objective_icing import read,write


def draw_spatial(result,label,unit,path):
    if path.exists():raise FileExistsError('Preserve existing spatial figure')
    fig,ax=plt.subplots(figsize=(9,4.8),layout='constrained')
    methods=['aws_fallback','instant_residual','history_residual'];colors=['#adb7c4','#215a83','#d08033']
    for j,(method,color) in enumerate(zip(methods,colors)):
        reports=result['reports'][method]
        values=[reports['pooled']['mae'],reports['winters']['2024']['mae'],
            reports['winters']['2025']['mae'],reports['cold']['mae']]
        bars=ax.bar([i-.24+j*.24 for i in range(4)],values,width=.23,color=color,label=method)
        ax.bar_label(bars,fmt='%.3f',fontsize=9,padding=3)
    ax.set_xticks(range(4),['Both winters','Winter 2024','Winter 2025','ASOS air within +/-3C'])
    ax.set_ylabel(f'{label} MAE ({unit})');ax.spines[['top','right']].set_visible(False)
    ax.set_ylim(0,ax.get_ylim()[1]*1.15)
    ax.set_title('Held-out region | both winters in training | repeated development data')
    handles,_=ax.get_legend_handles_labels()
    fig.legend(handles,['AWS first','Current inputs','Past 3h / 24h inputs'],loc='outside lower center',ncol=3,frameon=False)
    fig.savefig(path,dpi=170);plt.close(fig)


def main():
    config=ROOT/'config/weather_temporal_memory_20261101.json';plan=read(config)
    source=ROOT/plan['output'];summary=read(source/'summary.json');audit=read(source/'independent_verification.json')
    assert audit['status']=='passed' and audit['summary_sha256']==sha(source/'summary.json')
    spatial_plan=read(ROOT/'config/weather_air_history_spatial_20261101.json')
    spatial_out=ROOT/spatial_plan['output'];spatial=read(spatial_out/'summary.json')
    spatial_audit=read(spatial_out/'independent_verification.json')
    assert spatial_audit['status']=='passed' and spatial_audit['summary_sha256']==sha(spatial_out/'summary.json')
    humidity_plan=read(ROOT/'config/weather_humidity_history_spatial_20261101.json')
    humidity_out=ROOT/humidity_plan['output'];humidity=read(humidity_out/'summary.json')
    humidity_audit=read(humidity_out/'independent_verification.json')
    assert humidity_audit['status']=='passed' and humidity_audit['summary_sha256']==sha(humidity_out/'summary.json')
    out=ROOT/'outputs/private/weather_temporal_review_20261101_v1'
    if out.exists():raise FileExistsError('Preserve completed review')
    out.mkdir(parents=True)
    rows=[]
    for target,result in summary['reports'].items():
        for method,reports in result['metrics'].items():
            for scope,value in [('pooled',reports['pooled']),('cold_input',reports['cold']),
                *[('query_winter_'+k,v) for k,v in reports['directions'].items()],
                *[('region_'+k,v) for k,v in reports['regions'].items()]]:
                rows.append(dict(validation='region_and_winter',target=target,method=method,scope=scope,**value))
    for method,reports in spatial['reports'].items():
        for scope,value in [('pooled',reports['pooled']),('cold_input',reports['cold']),
            *[('winter_'+k,v) for k,v in reports['winters'].items()],
            *[('region_'+k,v) for k,v in reports['regions'].items()]]:
            rows.append(dict(validation='region_only',target='air_temperature',method=method,scope=scope,**value))
    for method,reports in humidity['reports'].items():
        for scope,value in [('pooled',reports['pooled']),('cold_input',reports['cold']),
            *[('winter_'+k,v) for k,v in reports['winters'].items()],
            *[('region_'+k,v) for k,v in reports['regions'].items()]]:
            rows.append(dict(validation='region_only',target='relative_humidity',method=method,scope=scope,**value))
    table=pd.DataFrame(rows);table.to_csv(out/'metrics.csv',index=False,encoding='utf-8-sig')
    targets=list(summary['reports']);labels=['Air temperature (C)','Relative humidity (%p)','Wind speed (m/s)']
    fig,axes=plt.subplots(1,3,figsize=(12,4.6),layout='constrained')
    methods=['aws_fallback','instant_residual','history_residual'];colors=['#adb7c4','#215a83','#d08033']
    for ax,target,label in zip(axes,targets,labels):
        reports=summary['reports'][target]['metrics']
        for j,(method,color) in enumerate(zip(methods,colors)):
            values=[reports[method]['directions'][str(year)]['mae'] for year in [2024,2025]]
            bars=ax.bar([-.24+j*.24,1-.24+j*.24],values,width=.23,color=color,label=method)
            ax.bar_label(bars,fmt='%.3f',fontsize=8,padding=3)
        ax.set_xticks([0,1],['Reverse hindcast\n2025 -> 2024','Forward\n2024 -> 2025'])
        ax.set_title(label);ax.set_ylabel('MAE');ax.spines[['top','right']].set_visible(False)
        ax.set_ylim(0,ax.get_ylim()[1]*1.16)
    handles,_=axes[0].get_legend_handles_labels()
    fig.legend(handles,['AWS first','Current inputs','Past 3h / 24h inputs'],loc='outside lower center',ncol=3,frameon=False)
    fig.suptitle('Held-out region AND held-out winter | repeated development data',fontsize=13)
    figure=ROOT/'docs/images/weather_space_time_20261101.png'
    if figure.exists():raise FileExistsError('Preserve existing figure')
    fig.savefig(figure,dpi=170);plt.close(fig)
    spatial_figure=ROOT/'docs/images/weather_air_history_spatial_20261101.png'
    draw_spatial(spatial,'Air temperature','C',spatial_figure)
    humidity_figure=ROOT/'docs/images/weather_humidity_history_spatial_20261101.png'
    draw_spatial(humidity,'Relative humidity','%p',humidity_figure)
    notebook=ROOT/'notebooks/weather_space_time_review_20261101.ipynb'
    if notebook.exists():raise FileExistsError('Preserve existing notebook')
    cells=[nb.v4.new_markdown_cell('# 도로 기상: 지역·겨울 동시 제외 검증\n\n학습에서 평가 지역의 두 겨울과 평가 겨울의 모든 지역을 제외합니다. 역방향은 사후 재현이며 미래 예측 검증이 아닙니다. 기존 개발 자료를 사용했으므로 새 독립 표본으로 해석하지 않습니다. 기존 제출 모델·ZIP은 변경하지 않습니다.'),
        nb.v4.new_code_cell('''from pathlib import Path
import sys, json
import pandas as pd
import numpy as np
ROOT=next(p for p in [Path.cwd(), *Path.cwd().parents] if (p/'config/weather_temporal_20261101.json').is_file())
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
plan=json.loads((ROOT/'config/weather_temporal_memory_20261101.json').read_text('utf-8'))
out=ROOT/plan['output']
summary=json.loads((out/'summary.json').read_text('utf-8'))
audit=json.loads((out/'independent_verification.json').read_text('utf-8'))
assert audit['status']=='passed' and audit['summary_sha256']==sha(out/'summary.json')
assert len(summary['fits'])==48 and summary['production_model_changed'] is False
for name,digest in summary['files'].items(): assert sha(out/name)==digest, name
print('48개 모델과 입력·예측 파일 해시 확인 완료')'''),
        nb.v4.new_code_cell('''rows=[]
for target,result in summary['reports'].items():
    for method,metrics in result['metrics'].items():
        rows.append(dict(target=target,method=method,**metrics['pooled']))
display(pd.DataFrame(rows))
display(pd.DataFrame({target:r['history_gates'] for target,r in summary['reports'].items()}))'''),
        nb.v4.new_markdown_cell('## 대표 여섯 모형의 실제 재추론\n\n기온·습도·풍속 각각 현재 입력과 과거 이력 모형을 2025년 호남 백양에 재적용합니다. 전체 48모형 검산과 대표 6모형 재학습은 독립 검산 영수증에 기록되어 있습니다.'),
        nb.v4.new_code_cell('''import joblib
from threadpoolctl import threadpool_limits
from src.road_weather_transfer import baselines,constrain
f=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)
checked=0
for target in plan['targets']:
    asos,baseline=baselines(f,target)
    query=f.group.eq('honam_baekyang') & f.winter.eq(2025) & np.isfinite(f[target]) & np.isfinite(asos) & np.isfinite(baseline)
    for candidate in plan['candidates']:
        x=pd.read_parquet(out/(candidate+'_features.parquet'))
        stem=f'{candidate}_honam_baekyang_2025'
        model=joblib.load(out/target/(stem+'.joblib'))
        with threadpool_limits(limits=2):
            actual=constrain(model.predict(x.loc[query])+baseline[query],target)
        np.testing.assert_array_equal(actual,np.load(out/target/(stem+'.npy'),allow_pickle=False))
        checked+=1
        del x
print('대표 재추론 일치:',checked,'개 모델')'''),
        nb.v4.new_code_cell("from IPython.display import Image,display\ndisplay(Image(filename=str(ROOT/'docs/images/weather_space_time_20261101.png')))"),
        nb.v4.new_markdown_cell('## 두 겨울 자료 복원 조건의 추가 기온 비교\n\n두 겨울을 학습에 쓰면서 평가 지역 전체를 제외하는 별도 4모형입니다. 위의 지역·겨울 동시 제외와 학습 조건이 다릅니다. 기존 개발 자료에 대한 후속 비교이며 새 독립 표본이 아닙니다.'),
        nb.v4.new_code_cell('''spatial_plan=json.loads((ROOT/'config/weather_air_history_spatial_20261101.json').read_text('utf-8'))
spatial_out=ROOT/spatial_plan['output']
spatial=json.loads((spatial_out/'summary.json').read_text('utf-8'))
spatial_audit=json.loads((spatial_out/'independent_verification.json').read_text('utf-8'))
assert spatial_audit['status']=='passed' and spatial_audit['summary_sha256']==sha(spatial_out/'summary.json')
for name,digest in spatial['files'].items(): assert sha(spatial_out/name)==digest, name
display(pd.DataFrame({name:r['pooled'] for name,r in spatial['reports'].items()}).T)
display(pd.Series(spatial['gates'],name='사전 채택 기준'))
display(Image(filename=str(ROOT/'docs/images/weather_air_history_spatial_20261101.png')))'''),
        nb.v4.new_markdown_cell('## 겨울 전이를 통과한 습도의 지역 제외 확인\n\n습도는 지역·겨울 동시 제외에서 다섯 기준을 통과해 실제 자료 복원 조건에서도 별도 4모형을 검증했습니다. 새 독립 평가라고 해석하지 않으며, 개선된 습도를 결빙 정확도로 대신하지 않습니다.'),
        nb.v4.new_code_cell('''humidity_plan=json.loads((ROOT/'config/weather_humidity_history_spatial_20261101.json').read_text('utf-8'))
humidity_out=ROOT/humidity_plan['output']
humidity=json.loads((humidity_out/'summary.json').read_text('utf-8'))
humidity_audit=json.loads((humidity_out/'independent_verification.json').read_text('utf-8'))
assert humidity_audit['status']=='passed' and humidity_audit['summary_sha256']==sha(humidity_out/'summary.json')
for name,digest in humidity['files'].items(): assert sha(humidity_out/name)==digest, name
display(pd.DataFrame({name:r['pooled'] for name,r in humidity['reports'].items()}).T)
display(pd.Series(humidity['gates'],name='사전 채택 기준'))
display(Image(filename=str(ROOT/'docs/images/weather_humidity_history_spatial_20261101.png')))'''),
        nb.v4.new_markdown_cell('전체 실행은 저장소 루트에서 `python scripts/evaluate_weather_space_time_memory.py`와 `python scripts/audit_weather_temporal.py --config config/weather_temporal_memory_20261101.json`을 사용합니다. 완료 출력은 덮어쓰지 않습니다. 새 반복은 별도 설정·출력 경로가 필요합니다. 원래 48적합 설정을 유지하고 검증된 완료 모델 15개를 재사용해 메모리 사용만 줄였습니다. 11월 6일은 사용자 제공 작업 마감 기준이며 공식 날짜 확인과 구별합니다.')]
    book=nb.v4.new_notebook(cells=cells,metadata=dict(kernelspec=dict(display_name='Python 3',language='python',name='python3')))
    nb.write(book,notebook)
    write(out/'receipt.json',dict(status='weather_temporal_review_built',source_summary_sha256=sha(source/'summary.json'),
        source_audit_sha256=sha(source/'independent_verification.json'),metric_rows=len(table),
        spatial_summary_sha256=sha(spatial_out/'summary.json'),spatial_audit_sha256=sha(spatial_out/'independent_verification.json'),
        humidity_summary_sha256=sha(humidity_out/'summary.json'),humidity_audit_sha256=sha(humidity_out/'independent_verification.json'),
        files={p.relative_to(ROOT).as_posix():sha(p) for p in [out/'metrics.csv',figure,spatial_figure,humidity_figure,notebook]},
        production_model_changed=False,competition_submitted=False))
    print('REVIEW',len(table),'metric rows',flush=True)


if __name__=='__main__':main()
