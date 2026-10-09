"""일회 평가·독립 감사가 끝난 새 8지점의 온도 오차와 FP·FN을 그린다."""
from pathlib import Path
import argparse,json,sys
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.fresh_station_validation import DEFAULT_OUT,PRIVATE,verify_seal
from src.research_delivery import file_sha


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',type=Path,default=DEFAULT_OUT)
    args=parser.parse_args();out=args.experiment.resolve()
    if not out.is_relative_to(PRIVATE.resolve()):parser.error('Private experiment required')
    verify_seal(out);audit=json.loads((out/'independent_verification.json').read_text('utf-8'))
    assert audit['status'] in {'passed','passed_with_collection_interval_deviation'} and audit['metrics_reproduced'] is True
    destination=out/'fresh_validation_review.jpg'
    if destination.exists():raise FileExistsError('Preserve figure')
    summary=json.loads((out/'summary.json').read_text('utf-8'));station=pd.read_csv(out/'station_metrics.csv',dtype={'station':str})
    ids=sorted(summary['temperature']['weather_hgb23']['stations']);pos=np.arange(len(ids));width=.36
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':11})
    fig,axes=plt.subplots(3,1,figsize=(12,12),constrained_layout=True)
    for j,(policy,label,color) in enumerate([('original_weather_ridge','기존 14지점 기상 Ridge','#9ba8b7'),('weather_hgb23','첫 겨울 23지점 기상 HGB','#2873b3')]):
        values=[summary['temperature'][policy]['stations'][s]['mae'] for s in ids]
        axes[0].bar(pos+(j-.5)*width,[v if v is not None else np.nan for v in values],width,label=label,color=color)
    axes[0].set_ylabel('동일 유효 시각 MAE (°C)');axes[0].set_title('학습에 없는 지점의 노면온도 오차: 지점별 비교');axes[0].legend()
    for ax,metric,title in [(axes[1],'fp','오경보 (FP)'),(axes[2],'fn','놓친 결빙 (FN)')]:
        for j,(policy,label,color) in enumerate([('original_ice','기존 14지점 분류','#9ba8b7'),('thermal_moisture','고정 온도·수분 가안','#2873b3')]):
            part=station[station.policy.eq(policy)].set_index('station');values=part.reindex(ids)[metric].to_numpy()
            ax.bar(pos+(j-.5)*width,values,width,label=label,color=color)
        ax.set_title(title);ax.set_ylabel('10분 시점 수');ax.legend()
    for ax in axes:ax.set_xticks(pos,ids);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    base=summary['metrics']['original_ice'];candidate=summary['metrics']['thermal_moisture']
    fig.suptitle(f"첫 겨울 미사용 8지점의 사전 고정 가안 평가\n유효 상태 {base['n']:,}시점 · Ice {base['tp']+base['fn']:,}시점 · F1 {base['f1']:.4f} → {candidate['f1']:.4f}\n같은 겨울의 공간 검증 / 공식 점수·다음 겨울 검증이 아님",fontsize=15)
    fig.savefig(destination,dpi=180);plt.close(fig)
    (out/'figure_receipt.json').write_text(json.dumps(dict(summary_sha256=file_sha(out/'summary.json'),figure_sha256=file_sha(destination),source_sha256=file_sha(__file__)),indent=2),'utf-8')
    print('Rendered fresh station figure:',destination)


if __name__=='__main__':main()
