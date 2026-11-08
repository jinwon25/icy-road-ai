"""검산을 통과한 기상 추정 연구의 CSV·그림·실행 노트북을 만든다."""
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import nbformat as nbf
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_objective_icing import read,write


def main():
    study=ROOT/'outputs/private/road_weather_transfer_20261031_v1'
    out=ROOT/'outputs/private/road_weather_review_20261031_v1'
    if out.exists():raise FileExistsError('Preserve completed weather review')
    summary=read(study/'summary.json');audit=read(study/'independent_verification.json')
    assert audit['status']=='passed' and audit['summary_sha256']==sha(study/'summary.json')
    controls=ROOT/'outputs/private/weather_calibration_controls_20261031_v1'
    control_summary=read(controls/'summary.json');control_audit=read(controls/'independent_verification.json')
    assert control_audit['status']=='passed' and control_audit['summary_sha256']==sha(controls/'summary.json')
    out.mkdir(parents=True);rows=[]
    for target,result in summary['reports'].items():
        for model,metrics in result['metrics'].items():
            rows.append(dict(target=target,model=model,scope='all',group='all',**metrics['pooled']))
            for scope in ['regions','winters']:
                for name,m in metrics[scope].items():rows.append(dict(target=target,model=model,scope=scope,group=name,**m))
        f=pd.read_parquet(study/target/'predictions.parquet')
        # 파라미터별 관측·두 기준선·두 고정 후보를 동일 10분 행에 함께 제시한다.
        path=out/(target+'_10min.csv.gz');f.to_csv(path,index=False,encoding='utf-8',compression='gzip')
        reloaded=pd.read_csv(path,dtype={'station':str},parse_dates=['time'])
        pd.testing.assert_frame_equal(f,reloaded,check_exact=False,rtol=1e-14,atol=1e-12)
        for model in ['weighted_training_median','weighted_residual_offset']:
            metrics=control_summary['reports'][target]['metrics'][model]
            rows.append(dict(target=target,model=model,scope='all',group='all',**metrics['pooled']))
            for scope in ['regions','winters']:
                for name,m in metrics[scope].items():rows.append(dict(target=target,model=model,scope=scope,group=name,**m))
    table=pd.DataFrame(rows);table.to_csv(out/'observation_estimation_metrics.csv',index=False,encoding='utf-8-sig')
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':10})
    fig,axes=plt.subplots(1,3,figsize=(12,4.8));fig.subplots_adjust(left=.065,right=.99,bottom=.25,top=.79,wspace=.35)
    titles={'air_temperature':'기온 (°C)','relative_humidity':'상대습도 (%p)','wind_speed':'풍속 (m/s)'}
    labels=['ASOS','AWS 우선','학습 상수','상수 보정','잔차 학습','직접 학습']
    models=['asos','aws_fallback','weighted_training_median','weighted_residual_offset','residual_hgb','direct_hgb']
    for ax,(target,title) in zip(axes,titles.items()):
        metrics=summary['reports'][target]['metrics']|control_summary['reports'][target]['metrics']
        values=[metrics[m]['pooled']['mae'] for m in models]
        ax.bar(np.arange(6),values,color=['#9aa9b8','#526779','#bcbcbc','#b89561','#177f89','#479cba'],width=.65)
        ax.set_xticks(np.arange(6),labels,rotation=40,ha='right');ax.set_title(title);ax.set_ylim(0,max(values)*1.22)
        for i,v in enumerate(values):ax.text(i,v+max(values)*.02,f'{v:.3f}',ha='center',fontsize=10)
        ax.spines[['top','right']].set_visible(False);ax.set_axisbelow(True);ax.grid(axis='y',alpha=.18)
    axes[0].set_ylabel('평균절대오차 (작을수록 좋음)')
    fig.suptitle('미관측 개발 4지역 · 두 겨울 기상 관측값 추정',fontsize=16,y=.97)
    fig.text(.065,.04,'동일 유효 행 비교 · 반복 개발 자료 · 신규 독립 성능 또는 결빙 F1 개선을 뜻하지 않음',fontsize=10,color='#526779')
    fig.savefig(out/'mae_comparison.png',dpi=180);plt.close(fig)
    notebook=ROOT/'notebooks/road_weather_transfer_review_20261031.ipynb'
    if notebook.exists():raise FileExistsError('Preserve existing weather notebook')
    nb=nbf.v4.new_notebook();nb.metadata.kernelspec=dict(display_name='Python 3',language='python',name='python3')
    nb.cells=[
        nbf.v4.new_markdown_cell('# 미관측 도로 기상값 추정 검토\n\n기온·습도·풍속의 지역 제외 결과입니다. 노면온도·결빙 모델은 변경하지 않습니다. 기본 실행은 집계 확인과 저장 모형의 10분 추론이며, 마지막 셀의 `RUN_REFIT=True`는 대표 3모델을 메모리에서 재학습합니다. 원 비공개 프로젝트의 별도 연구 입력이 필요합니다. [설계·출처·한계](../docs/research/ROAD_WEATHER_TRANSFER_20261031.md)를 먼저 확인합니다.'),
        nbf.v4.new_code_cell("from pathlib import Path\nimport sys, json\nimport numpy as np\nimport pandas as pd\nimport joblib\nfrom threadpoolctl import threadpool_limits\nROOT = Path.cwd() if (Path.cwd()/'src').is_dir() else Path.cwd().parent\nsys.path.insert(0, str(ROOT))\nfrom src.data_source import sha256_file\nfrom src.road_weather_transfer import features, baselines, constrain, balanced_weights\nfrom src.offline_runtime import deny_network\nstudy = ROOT/'outputs/private/road_weather_transfer_20261031_v1'\nsummary = json.loads((study/'summary.json').read_text('utf-8'))\naudit = json.loads((study/'independent_verification.json').read_text('utf-8'))\nassert audit['status'] == 'passed' and sha256_file(study/'summary.json') == audit['summary_sha256']\nsettings = json.loads((study/'plan.json').read_text('utf-8'))['settings']\nmetrics = pd.read_csv(ROOT/'outputs/private/road_weather_review_20261031_v1/observation_estimation_metrics.csv')\nmetrics.loc[metrics.scope.eq('all'), ['target','model','n','mae','rmse','bias','correlation','r2']]"),
        nbf.v4.new_markdown_cell('## 동일 시각의 관측과 추론\n\n학습에서 제외된 호남 백양 지역을 예로 사용합니다. 입력 함수는 허용된 기상 열만 선택합니다. 기본 재추론 72행은 저장된 전체 지역 평가의 앞부분이며 새 평가가 아닙니다.'),
        nbf.v4.new_code_cell("receipt = json.loads((ROOT/settings['input_output']/'receipt.json').read_text('utf-8'))\ndata_path = ROOT/settings['input_output']/'development.parquet'\nassert sha256_file(data_path) == receipt['data_sha256']\nf = pd.read_parquet(data_path).sort_values(['station','time']).reset_index(drop=True)\nx = features(f)\nexamples = []\nfor target in settings['targets']:\n    a, b = baselines(f, target)\n    good = f[target].notna() & np.isfinite(a) & np.isfinite(b)\n    q = f.loc[f.group.eq('honam_baekyang') & good].head(72)\n    model = joblib.load(study/target/'residual_hgb_honam_baekyang.joblib')\n    with deny_network() as attempts, threadpool_limits(limits=2):\n        p = constrain(model.predict(x.loc[q.index]) + b[q.index], target)\n    assert not attempts\n    saved = pd.read_parquet(study/target/'predictions.parquet')\n    np.testing.assert_array_equal(p, saved.loc[saved.group.eq('honam_baekyang'),'residual_hgb'].head(72))\n    example = q[['station','time']].copy()\n    example['target'] = target\n    example['observed'] = q[target]\n    example['prediction'] = p\n    examples.append(example)\npd.concat(examples).groupby('target').head(6)"),
        nbf.v4.new_markdown_cell('## 선택 실행: 대표 모형 재학습\n\n전체 두 겨울에서 호남 백양을 제외하고, 지점·겨울별 가중치를 같게 맞춰 세 잔차 모형을 다시 적합합니다. 원 파일에 쓰지 않으며 기존 추론과 정확히 대조합니다. 전체 24회 적합과 별도 검산 코드는 `scripts/evaluate_road_weather_transfer.py`, `scripts/audit_road_weather_transfer.py`에 있습니다.'),
        nbf.v4.new_code_cell("RUN_REFIT = False\nif RUN_REFIT:\n    from sklearn.ensemble import HistGradientBoostingRegressor\n    for target in settings['targets']:\n        a, b = baselines(f, target)\n        good = f[target].notna() & np.isfinite(a) & np.isfinite(b)\n        train = f.loc[f.group.ne('honam_baekyang') & good]\n        q = f.loc[f.group.eq('honam_baekyang') & good]\n        model = HistGradientBoostingRegressor(**settings['model'])\n        with deny_network() as attempts, threadpool_limits(limits=2):\n            model.fit(x.loc[train.index], train[target].to_numpy()-b[train.index], sample_weight=balanced_weights(train))\n            p = constrain(model.predict(x.loc[q.index])+b[q.index], target)\n        assert not attempts\n        saved = pd.read_parquet(study/target/'predictions.parquet')\n        np.testing.assert_array_equal(p, saved.loc[saved.group.eq('honam_baekyang'),'residual_hgb'])\n        print(target, len(q), '재학습 일치')\nelse:\n    print('기본 실행 완료. 전체 독립 검산에서 대표 3모델 재학습을 별도로 확인했습니다.')")
    ]
    nbf.write(nb,notebook)
    write(out/'receipt.json',dict(status='weather_review_built',source_summary_sha256=sha(study/'summary.json'),
        audit_sha256=sha(study/'independent_verification.json'),metric_rows=len(table),
        calibration_summary_sha256=sha(controls/'summary.json'),calibration_audit_sha256=sha(controls/'independent_verification.json'),
        notebook=notebook.relative_to(ROOT).as_posix(),notebook_sha256=sha(notebook),
        files={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print('REVIEW',len(table),'metric rows',flush=True)


if __name__=='__main__':main()
