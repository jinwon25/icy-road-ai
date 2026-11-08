"""최종 안정화 습도의 두 검증·채택 기상값을 그림·표·실행 노트북으로 정리한다."""
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import nbformat as nb
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write
from src.data_source import sha256_file as sha


def main():
    study=ROOT/'outputs/private/weather_humidity_stable_20261101_v1'
    summary=read(study/'summary.json');audit=read(study/'independent_verification.json')
    assert summary['primary_success'] and audit['status']=='passed' and audit['summary_sha256']==sha(study/'summary.json')
    out=ROOT/'outputs/private/weather_history_review_20261101_v2'
    if out.exists():raise FileExistsError('Preserve stable weather review')
    out.mkdir(parents=True)
    methods=['aws_fallback','instant_residual','stable_history'];colors=['#adb7c4','#215a83','#d08033']
    rows=[]
    for mode,r in summary['reports'].items():
        for method,metrics in r['metrics'].items():
            for scope,value in [('all',metrics['pooled']),('cold_input',metrics['cold']),
                *[('winter_'+k,v) for k,v in metrics['winters'].items()],
                *[('region_'+k,v) for k,v in metrics['regions'].items()]]:
                rows.append(dict(validation=mode,method=method,scope=scope,**value))
    pd.DataFrame(rows).to_csv(out/'humidity_validation_metrics.csv',index=False,encoding='utf-8-sig')
    fig,axes=plt.subplots(1,2,figsize=(9,4.4),layout='constrained')
    for ax,mode,title in zip(axes,['joint','spatial'],['Region AND winter held out','Region held out; both winters learned']):
        for j,(method,color) in enumerate(zip(methods,colors)):
            r=summary['reports'][mode]['metrics'][method]
            bars=ax.bar([-.24+j*.24,1-.24+j*.24],[r['winters'][str(y)]['mae'] for y in [2024,2025]],
                width=.23,color=color,label=method)
            ax.bar_label(bars,fmt='%.3f',fontsize=9,padding=3)
        ax.set_xticks([0,1],['Winter 2024','Winter 2025']);ax.set_title(title,fontsize=11)
        ax.set_ylabel('Humidity MAE (%p)');ax.set_ylim(0,ax.get_ylim()[1]*1.18)
        ax.spines[['top','right']].set_visible(False)
    handles,_=axes[0].get_legend_handles_labels()
    fig.legend(handles,['AWS first','Current 34 inputs','Stable 82 inputs'],loc='outside lower center',ncol=3,frameon=False)
    fig.suptitle('Humidity | independent local-window sums | repeated development regions',fontsize=12)
    validation_image=ROOT/'docs/images/weather_humidity_stable_20261101.png'
    if validation_image.exists():raise FileExistsError('Preserve stable humidity figure')
    fig.savefig(validation_image,dpi=190);plt.close(fig)
    initial=read(ROOT/'outputs/private/road_weather_transfer_20261031_v1/summary.json')
    fig,axes=plt.subplots(1,3,figsize=(9,3.5),layout='constrained')
    adopted=[]
    for ax,target,label in zip(axes,['air_temperature','relative_humidity','wind_speed'],
        ['Air temperature (C)','Relative humidity (%p)','Wind speed (m/s)']):
        old=initial['reports'][target]['metrics'];a=old['aws_fallback']['pooled']['mae']
        b=summary['reports']['spatial']['metrics']['stable_history']['pooled']['mae'] if target=='relative_humidity' else old['residual_hgb']['pooled']['mae']
        bars=ax.bar([0,1],[a,b],color=[colors[0],colors[2]])
        ax.bar_label(bars,fmt='%.3f',fontsize=9,padding=3);ax.set_xticks([0,1],['AWS first','Adopted'])
        ax.set_title(label,fontsize=11);ax.set_ylabel('MAE');ax.set_ylim(0,max(a,b)*1.22)
        ax.spines[['top','right']].set_visible(False)
        adopted.append(dict(target=target,aws_mae=a,adopted_mae=b,reduction_pct=(1-b/a)*100,
            history_inputs=target=='relative_humidity'))
    fig.suptitle('Held-out region | same two winters | repeated development data',fontsize=12)
    adopted_image=ROOT/'docs/images/weather_adopted_20261101.png'
    if adopted_image.exists():raise FileExistsError('Preserve adopted weather figure')
    fig.savefig(adopted_image,dpi=190);plt.close(fig)
    pd.DataFrame(adopted).to_csv(out/'adopted_weather_metrics.csv',index=False,encoding='utf-8-sig')
    notebook=ROOT/'notebooks/weather_humidity_stable_review_20261101.ipynb'
    if notebook.exists():raise FileExistsError('Preserve stable review notebook')
    book=nb.v4.new_notebook(metadata=dict(kernelspec=dict(display_name='Python 3',language='python',name='python3')))
    book.cells=[nb.v4.new_markdown_cell('# 최종 습도 이력 모형 검토\n\n독립적인 고정 길이 과거 창의 합산을 사용합니다. 지역·겨울 동시 제외와 두 겨울 지역 제외를 구분합니다. 반복 개발 자료로 공식 점수·새 독립 표본이 아닙니다.'),
        nb.v4.new_code_cell("from pathlib import Path\nimport sys,json\nimport pandas as pd\nimport numpy as np\nROOT=next(p for p in [Path.cwd(),*Path.cwd().parents] if (p/'config/weather_humidity_stable_20261101.json').is_file())\nsys.path.insert(0,str(ROOT))\nfrom src.data_source import sha256_file as sha\nplan=json.loads((ROOT/'config/weather_humidity_stable_20261101.json').read_text('utf-8'))\nout=ROOT/plan['output']\nsummary=json.loads((out/'summary.json').read_text('utf-8'))\naudit=json.loads((out/'independent_verification.json').read_text('utf-8'))\nassert audit['status']=='passed' and audit['summary_sha256']==sha(out/'summary.json')\nassert summary['primary_success'] and len(summary['fits'])==12\nfor name,digest in summary['files'].items(): assert sha(out/name)==digest,name\nprint('12개 신규 적합·파일·검산 확인')"),
        nb.v4.new_code_cell("rows=[]\nfor mode,r in summary['reports'].items():\n    for method,values in r['metrics'].items():\n        rows.append(dict(validation=mode,method=method,**values['pooled']))\ndisplay(pd.DataFrame(rows))\ndisplay(pd.DataFrame({mode:r['gates'] for mode,r in summary['reports'].items()}))\nprint('독립 문맥 불변 특성 값:',audit['prefix_bit_exact_feature_values'])"),
        nb.v4.new_code_cell("import joblib\nfrom threadpoolctl import threadpool_limits\nfrom src.road_weather_transfer import baselines\nf=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)\nx=pd.read_parquet(out/'features.parquet')\na,b=baselines(f,'relative_humidity')\nquery=f.group.eq('honam_baekyang') & f.relative_humidity.notna() & np.isfinite(a) & np.isfinite(b)\nmodel=joblib.load(out/'spatial/honam_baekyang.joblib')\nwith threadpool_limits(limits=2): actual=np.clip(model.predict(x.loc[query])+b[query],0,100)\nnp.testing.assert_array_equal(actual,np.load(out/'spatial/honam_baekyang.npy',allow_pickle=False))\nprint('대표 지역 모형 실제 재추론 일치:',len(actual),'행')"),
        nb.v4.new_code_cell("from IPython.display import Image,display\ndisplay(Image(filename=str(ROOT/'docs/images/weather_humidity_stable_20261101.png')))\ndisplay(Image(filename=str(ROOT/'docs/images/weather_adopted_20261101.png')))"),
        nb.v4.new_markdown_cell('실제 최종 모형의 전체 재학습·432행 추론 검증은 별도 실행 묶음 `weather_history_supplement_20261101_v2`의 노트북을 사용합니다. 첫 구현의 문맥 의존 오류와 카운터 수정도 보존해 추적할 수 있습니다.')]
    nb.write(book,notebook)
    write(out/'receipt.json',dict(status='stable_weather_review_built',study_summary_sha256=sha(study/'summary.json'),
        study_audit_sha256=sha(study/'independent_verification.json'),metric_rows=len(rows),
        files={p.relative_to(ROOT).as_posix():sha(p) for p in [validation_image,adopted_image,notebook,
            out/'humidity_validation_metrics.csv',out/'adopted_weather_metrics.csv']}))
    print('STABLE WEATHER REVIEW BUILT',len(rows),flush=True)


if __name__=='__main__':main()
