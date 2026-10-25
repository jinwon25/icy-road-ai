"""검산된 원문 품질·추가 탐지 결과만으로 집계 그림을 만든다."""
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.blind_icing_validation import read,write,now
from src.data_source import sha256_file as sha


def main():
    raw=ROOT/'outputs/private/rwis_anomaly_diagnosis_20261025_v1'
    experiment=ROOT/'outputs/private/additive_icing_20261025_v1'
    for folder in [raw,experiment]:
        audit=read(folder/'audit.json')
        assert audit['status']=='passed' and audit['summary_sha256']==sha(folder/'summary.json')
    out=ROOT/'docs/assets/rwis_additive_20261025.png'
    if out.exists():raise FileExistsError('Preserve reviewed figure')
    font=Path('C:/Windows/Fonts/malgun.ttf')
    if font.exists():plt.rcParams['font.family']=font_manager.FontProperties(fname=font).get_name()
    plt.rcParams['axes.unicode_minus']=False
    totals=read(raw/'summary.json')['station_33406_totals'];reports=read(experiment/'summary.json')['reports']
    fig,axes=plt.subplots(1,2,figsize=(12,5.4),gridspec_kw={'width_ratios':[1,1.2]})
    fig.patch.set_facecolor('#f8fafc')
    ax=axes[0];labels=['동일 시각 상태 충돌','유효 시각 없음','상태 코드 무효']
    values=[totals[k] for k in ['conflict_quarantine','timestamp_absent','invalid_state']]
    ax.barh(labels[::-1],values[::-1],color=['#94a3b8','#eab308','#e87952'])
    for i,v in enumerate(values[::-1]):ax.text(v+25,i,f'{v:,}',va='center')
    ax.set_xlim(0,1750);ax.set_xlabel('평가에 사용하지 못한 10분 시각 수');ax.set_title('진천터널외부: 2,524개 시각의 원인',pad=15)
    ax.text(0,-.27,'두 겨울 34,560시각 중 유효 정답 32,036개\n충돌 행은 전부 격리한 기존 평가를 유지',transform=ax.transAxes,fontsize=10,color='#475569')
    keys=['guarded','maximum_f1','warm_hgb_cap0.5_p0.1'];names=['주 선택 절차','F1 최대 선택 절차','사후 최고 고정 후보']
    base=reports['asos_zero']['all']['f1_fixed_population'];changes=[100*(reports[k]['all']['f1_fixed_population']/base-1) for k in keys]
    ax=axes[1];colors=['#64748b','#e87952','#3b82f6']
    for i,(k,name,change,color) in enumerate(zip(keys,names,changes,colors)):
        y=2-i;ax.barh(y,change,color=color,height=.5)
        text=f'{change:+.3f}%  /  오경보 +{reports[k]["all"]["fp"]-reports["asos_zero"]["all"]["fp"]:,}'
        ax.text(.21,y,text,va='center',fontsize=9)
    ax.set_yticks([2,1,0],names);ax.axvline(0,color='#64748b',lw=.8);ax.set_xlim(-.3,.66)
    ax.set_xticks([-.2,0,.2]);ax.set_xlabel('기온 기준선 대비 일별 F1 상대 변화 (%)');ax.set_title('20모델·57정책: 안정적 개선 미확인',pad=15)
    ax.text(0,-.27,'기존 개발 9곳·두 겨울의 반복 개발 점수\n사후 최고도 +1% 기준·둘째 겨울·정밀도 조건 미충족',transform=ax.transAxes,fontsize=10,color='#475569')
    for ax in axes:
        ax.set_facecolor('#f8fafc');ax.spines[['top','right']].set_visible(False);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('원문 오류를 좁히고, 개선되지 않은 모델은 채택하지 않음',fontsize=16,x=.5,y=.98)
    fig.subplots_adjust(left=.13,right=.97,top=.80,bottom=.29,wspace=.56)
    out.parent.mkdir(parents=True,exist_ok=True);fig.savefig(out,dpi=160);plt.close(fig)
    write(experiment/'figure_receipt.json',dict(at_utc=now(),figure=out.relative_to(ROOT).as_posix(),sha256=sha(out),code_sha256=sha(Path(__file__))))
    print(out)


if __name__=='__main__':main()
