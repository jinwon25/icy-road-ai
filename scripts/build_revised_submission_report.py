"""검산된 수치·실패 사례·문헌 적용 근거로 심사용 보고서와 편집 원고를 생성."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import html
import re
import shutil
import sys
import fitz
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager
from matplotlib.colors import Normalize
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Image, Spacer, PageBreak

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_method_blending import read, write
from src.data_source import sha256_file as sha

PRIVATE = ROOT / 'outputs/private'
RESEARCH = PRIVATE / 'freezing_weight_20261014_v1'
DIAG = PRIVATE / 'submission_diagnostics_20261014_v1'
CANDIDATE = PRIVATE / 'submission_candidate_20261013_v1'
REFERENCES = [
    ('R1', 'KISTI. 전북도 고속도로 결빙 위험도 분석 문제 및 평가 방법.', 'https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004604/detail.do', '공식 과제·평가·산출물'),
    ('R2', 'KISTI. 결빙 평가 Q&A 633. 답변 2026-10-13.', 'https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=633', '미탐일 지표 처리'),
    ('R3', 'KISTI. 결과물 제출방법 공지 564.', 'https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=564', '구성·재현·AI 활용 기록'),
    ('R4', 'XGBoost-Based Corrections for Road Surface Temperature Forecasts. J. Appl. Meteor. Climatol., 65(6), 2026.', 'https://doi.org/10.1175/JAMC-D-25-0189.1', '결빙점 부근 가중 학습의 동기. 출판사 색인의 초록·결과 부분 확인'),
    ('R5', 'Ma, G., et al. LSTM-Based Road Surface Temperature Forecasting for Winter Road Icing Risk Management. Applied Sciences, 16, 9487, 2026.', 'https://doi.org/10.3390/app16199487', '과거 노면온도를 요구하는 국내 예측 사례. 출판사 색인 확인'),
    ('R6', 'Li, W., et al. A hybrid method for winter road surface temperature prediction using improved LSTMs and stacking-based ensemble learning. GMD, 19, 9035-9061, 2026.', 'https://doi.org/10.5194/gmd-19-9035-2026', '시간 이력·OOF 결합·지점 전이 조건'),
    ('R7', 'Karsisto, V. E. RoadSurf 1.1: open-source road weather model library. GMD, 17, 4837-4853, 2024.', 'https://doi.org/10.5194/gmd-17-4837-2024', '열수지·수분 저장량·현지 물성 필요성'),
    ('R8', 'Colas, G., et al. Traffic impact modelling in SURFEX-TEB V9.0 model for improved road surface temperature prediction. GMD, 18, 9945-9966, 2025.', 'https://doi.org/10.5194/gmd-18-9945-2025', '교통의 열·복사·난류 영향'),
    ('R9', 'Roberts, D. R., et al. Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. Ecography, 40, 913-929, 2017.', 'https://doi.org/10.1111/ecog.02881', '공간 구조에 맞춘 평가. 기존 저자 대학 사본 사용'),
    ('R10', 'Cawley, G. C., and Talbot, N. L. C. On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation. JMLR, 11, 2079-2107, 2010.', 'https://jmlr.org/papers/v11/cawley10a.html', '반복 탐색의 선택 편향'),
    ('R11', 'scikit-learn 1.6.1. HistGradientBoostingRegressor.', 'https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html', '손실함수·표본 가중치 구현'),
    ('R12', 'scores. Block bootstrapping technique, 공식 라이브러리 문서.', 'https://scores.readthedocs.io/en/stable/tutorials/Block_Bootstrapping.html', '시계열 상관을 고려한 블록 재표집'),
    ('R13', 'FHWA. Manual of Practice for an Effective Anti-Icing Program, FHWA-RD-95-202, 1996.', 'https://www.fhwa.dot.gov/publications/research/safety/95202/002.cfm', '기상·노면·순찰·처리 이력의 통합 판단'),
]


def figures(out, summary, diagnostic):
    font_manager.fontManager.addfont('C:/Windows/Fonts/malgun.ttf')
    plt.rcParams.update({'font.family':'Malgun Gothic', 'font.size':10, 'axes.unicode_minus':False,
        'axes.spines.top':False, 'axes.spines.right':False, 'figure.facecolor':'white', 'savefig.facecolor':'white'})
    station = pd.read_csv(DIAG / 'station_performance.csv', dtype={'station':str})
    a = station.loc[station.method.eq('trio')].set_index('station')
    b = station.loc[station.method.eq('pair')].set_index('station').reindex(a.index)
    fig, ax = plt.subplots(figsize=(9,3.2))
    y = np.arange(len(a))
    for i in y:
        ax.plot([a.mae.iloc[i], b.mae.iloc[i]],[i,i],color='#bec8cf',lw=2,zorder=1)
    ax.scatter(a.mae,y,color='#7d8c98',s=40,label='기존 3종 평균',zorder=3)
    ax.scatter(b.mae,y,color='#176b88',s=42,label='현재 2종 평균',zorder=3)
    ax.set_yticks(y,a.index);ax.invert_yaxis();ax.set_xlabel('지점별 MAE (°C, 작을수록 좋음)')
    ax.grid(axis='x',alpha=.2);ax.legend(loc='upper right',fontsize=9)
    fig.tight_layout();fig.savefig(out / 'figures/station_mae.png',dpi=200);plt.close(fig)
    fig, axes = plt.subplots(1,2,figsize=(9,3.1))
    definitions=[('오경보 20,255행',[1081,19174],['관측온도 > 0°C','관측온도 ≤ 0°C']),
                 ('미탐 4,952행',[2280,2672],['추정온도 > 0°C','추정 저온·수분 조건 미충족'])]
    for ax,(title,values,labels) in zip(axes,definitions):
        bars=ax.barh([1,0],values,color=['#c88042','#176b88'],height=.5)
        ax.set_yticks([1,0],labels,fontsize=9);ax.set_xlim(0,max(values)*1.28)
        for bar,value in zip(bars,values):
            ax.text(value+max(values)*.025,bar.get_y()+bar.get_height()/2,f'{value:,}\n({value/sum(values):.1%})',va='center',fontsize=9)
        ax.set_title(title,loc='left',fontsize=11);ax.set_xlabel('10분 관측 행');ax.grid(axis='x',alpha=.2)
    fig.tight_layout(w_pad=2);fig.savefig(out/'figures/error_breakdown.png',dpi=200);plt.close(fig)
    fig, axes = plt.subplots(4,1,figsize=(9,6.8),gridspec_kw={'height_ratios':[2, .75,2,.75]})
    for index,(mode,title) in enumerate([('fn','미탐이 가장 많았던 날'),('fp','오경보가 가장 많았던 날')]):
        f=pd.read_csv(DIAG/f'{mode}_case.csv',parse_dates=['time'])
        ax,strip=axes[index*2:index*2+2]
        ax.plot(f.time,f.road_temp,color='#242d35',lw=1.3,label='관측 노면온도')
        ax.plot(f.time,f.equal_nohistory_pair,color='#176b88',lw=1.4,label='현재 모델 추정')
        ax.axhline(0,color='#c88042',ls='--',lw=.8);ax.set_ylabel('°C');ax.grid(alpha=.15)
        ax.set_title(f'{title}  |  {f.station.iloc[0]}  {f.time.iloc[0]:%Y-%m-%d}',loc='left',fontsize=11)
        ax.legend(loc='best',fontsize=8,ncol=2);ax.tick_params(axis='x',labelbottom=False)
        for level,col,color in [(1,'ice','#242d35'),(0,'current_pair','#176b88')]:
            positive=f.loc[f[col].eq(1),'time']
            strip.scatter(positive,np.full(len(positive),level),marker='s',s=13,color=color)
        strip.set_yticks([0,1],['모델 1','관측 Ice']);strip.set_ylim(-.55,1.55)
        strip.xaxis.set_major_locator(mdates.HourLocator(byhour=[0,6,12,18]))
        strip.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'));strip.set_xlabel('한국 시간')
        for axis in (ax,strip):axis.set_xlim(f.time.iloc[0],f.time.iloc[-1])
    fig.tight_layout(h_pad=1.0);fig.savefig(out/'figures/error_cases.png',dpi=200);plt.close(fig)
    fig, axes=plt.subplots(1,2,figsize=(9,3.1))
    for ax,metric,label in zip(axes,['mae','daily_f1'],['MAE 차이 (현재 - 기존, °C)','일별 F1 차이 (현재 - 기존)']):
        records=[r for r in diagnostic['resampling'] if r['metric']==metric]
        mid=np.array([r['median'] for r in records]);lower=np.array([r['lower'] for r in records]);upper=np.array([r['upper'] for r in records])
        ax.errorbar(mid,range(3),xerr=[mid-lower,upper-mid],fmt='o',color='#176b88',capsize=5)
        ax.axvline(0,color='#c88042',lw=1,ls='--');ax.set_yticks(range(3),[f"{r['block_days']}일 블록" for r in records])
        ax.set_xlabel(label,fontsize=9);ax.grid(axis='x',alpha=.2);ax.invert_yaxis()
        ax.ticklabel_format(axis='x',style='plain',useOffset=False)
    fig.tight_layout(w_pad=2);fig.savefig(out/'figures/date_sensitivity.png',dpi=200);plt.close(fig)
    boundary=gpd.read_file(PRIVATE/'segment_exposure_20261009_v1/boundary.gpkg')
    fig,axes=plt.subplots(1,2,figsize=(9,4.9))
    for ax,year in zip(axes,[2024,2025]):
        geo=gpd.read_file(CANDIDATE/'figures'/f'candidate_conditions_500m_{year}.gpkg')
        assert geo.cold_wet_fraction.max() <= .20 and geo.crs.to_epsg()==5179
        boundary.to_crs(geo.crs).plot(ax=ax,color='#f4f6f7',edgecolor='#b8c5ce',linewidth=.5)
        geo.assign(exposure_percent=100*geo.cold_wet_fraction).plot(ax=ax,column='exposure_percent',cmap='viridis',vmin=0,vmax=20,linewidth=2.4)
        xmin,ymin,xmax,ymax=geo.total_bounds
        for route,short in [('서해안고속국도','서해안선'),('호남고속국도','호남선'),('통영-대전고속국도','통영-대전선')]:
            part=geo.loc[geo.route_nm.eq(route)]
            center=part.geometry.union_all().centroid
            dx=-13000 if short=='서해안선' else 17000 if short=='통영-대전선' else 13000
            ax.annotate(short,(center.x,center.y),xytext=(center.x+dx,center.y+7000),fontsize=8,ha='center',
                bbox=dict(facecolor='white',edgecolor='none',alpha=.9,pad=2),arrowprops=dict(arrowstyle='-',color='#778891',lw=.6))
        ax.annotate('N',xy=(.9,.91),xytext=(.9,.79),xycoords='axes fraction',textcoords='axes fraction',ha='center',fontsize=9,
                    arrowprops=dict(arrowstyle='-|>',color='#33434e',lw=1))
        xx,yy=xmin+8000,ymin-6500
        ax.plot([xx,xx+20000],[yy,yy],color='#3d4a53',lw=2)
        ax.text(xx+10000,yy-4500,'20 km',ha='center',fontsize=8)
        ax.set_axis_off();ax.set_title(f'{year}-{year+1} 겨울',fontsize=12)
    fig.subplots_adjust(left=.015,right=.985,bottom=.14,top=.92,wspace=.06)
    cax=fig.add_axes([.28,.08,.44,.025])
    cb=fig.colorbar(plt.cm.ScalarMappable(norm=Normalize(0,20),cmap='viridis'),cax=cax,orientation='horizontal',ticks=[0,5,10,15,20])
    cb.set_label('유효 시점 중 추정 저온·수분 조건 비율 (%)',fontsize=9)
    fig.savefig(out/'figures/condition_map.jpg',dpi=230);plt.close(fig)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=PRIVATE/'report_upgrade_20261014_v1');args=parser.parse_args()
    out=args.output.resolve()
    if not out.is_relative_to(PRIVATE.resolve()):raise ValueError('Private project destination required')
    out.mkdir(exist_ok=False);(out/'figures').mkdir();(out/'preview').mkdir()
    summary=read(RESEARCH/'summary.json');diagnostic=read(DIAG/'summary.json')
    for folder in [RESEARCH,DIAG]:assert read(folder/'independent_verification.json')['summary_sha256']==sha(folder/'summary.json')
    assert read(PRIVATE/'report_references_20261014_v1/review_receipt.json')['blank_application_unchanged']
    figures(out,summary,diagnostic)
    pdfmetrics.registerFont(TTFont('Malgun','C:/Windows/Fonts/malgun.ttf'))
    pdfmetrics.registerFont(TTFont('MalgunBold','C:/Windows/Fonts/malgunbd.ttf'))
    pdfmetrics.registerFontFamily('Malgun',normal='Malgun',bold='MalgunBold',italic='Malgun',boldItalic='MalgunBold')
    common=dict(fontName='Malgun',fontSize=10.1,leading=16,textColor=colors.HexColor('#253442'),wordWrap='CJK')
    styles={'body':ParagraphStyle('body',**common,spaceAfter=9),
            'small':ParagraphStyle('small',**(common|{'fontSize':8.4,'leading':12.7}),spaceAfter=7),
            'table':ParagraphStyle('table',**(common|{'fontSize':8.4,'leading':12.4}),spaceAfter=0),
            'title':ParagraphStyle('title',fontName='MalgunBold',fontSize=27,leading=37,textColor=colors.HexColor('#163c55'),spaceAfter=19,wordWrap='CJK'),
            'h1':ParagraphStyle('h1',fontName='MalgunBold',fontSize=18,leading=26,textColor=colors.HexColor('#163c55'),spaceAfter=17,wordWrap='CJK'),
            'h2':ParagraphStyle('h2',fontName='MalgunBold',fontSize=12,leading=19,textColor=colors.HexColor('#163c55'),spaceBefore=8,spaceAfter=8,wordWrap='CJK')}
    story=[];manuscript=[]
    width=A4[0]-92
    def text(value,style='body'):
        story.append(Paragraph(value,styles[style]))
        plain=re.sub('<[^>]+>','',value.replace('<br/>','\n'))
        manuscript.append(('## ' if style=='h1' else '### ' if style=='h2' else '# ' if style=='title' else '')+html.unescape(plain))
    def table(rows, widths):
        data=[[Paragraph(html.escape(str(c)),styles['table']) for c in row] for row in rows]
        tab=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
        tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7eff3')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.8,colors.HexColor('#8ca4b2')),
            ('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#d5dfe4')),
            ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
            ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.extend([tab,Spacer(1,11)])
        manuscript.append('\n'.join(['| '+' | '.join(map(str,rows[0]))+' |','| '+' | '.join(['---']*len(rows[0]))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows[1:]]))
    def image(name,height,caption):
        story.extend([Image(str(out/'figures'/name),width=width,height=height),Spacer(1,7)])
        manuscript.append(f'![{caption}](figures/{name})');text(caption,'small')
    def page():story.append(PageBreak())
    scores=summary['scores'];base=scores['equal_distance_mse_mae300'];pair=scores['equal_nohistory_pair']
    pooled_improvement=100*(1-pair['temperature']['pooled']['mae']/base['temperature']['pooled']['mae'])
    macro_improvement=100*(1-pair['temperature']['station_macro']['mae']/base['temperature']['station_macro']['mae'])
    near_improvement=100*(1-scores['freezing_pair']['temperature']['near_freezing']['mae']/pair['temperature']['near_freezing']['mae'])
    text('전북 고속도로의<br/>노면온도 추정과 결빙 조건 분석','title')
    text('2026 DATA·AI 분석 경진대회  |  비공개 검토본<br/>기준일 2026년 10월 14일','small')
    text('도로기상관측장비가 없는 구간을 관리하려면, 주변 기상으로 추정할 수 있는 부분과 현장에서 확인해야 하는 부분을 구분해야 한다. 이 분석은 공공 기상으로 노면온도를 추정하고, 저온과 수분 조건이 겹치는 시간대를 전북 고속도로 구간에 연결한다.')
    text('현재 결과','h2')
    text(f'첫 겨울 개발 9곳에서 현재 2종 평균 모델의 전체 행 MAE는 1.200531°C였다. 기존 3종 평균보다 {pooled_improvement:.2f}% 작았다. 다만 일별 F1은 0.030633에 머물렀다. 온도 추정의 개선만으로 결빙 판정이 충분해지지는 않았다.')
    table([['확인 항목','결과'],['노면온도','지점 균등 MAE 1.200440°C / 전체 행 MAE 1.200531°C'],
        ['결빙 판정','일별 지점 평균 P 0.052803 / R 0.774688 / F1 0.030633'],
        ['실행 결과','보호 3곳 두 겨울 103,680행 중 103,662행 추정, 입력 부족 18행'],
        ['공간 산출물','500 m 843구간 / 1 km 423구간, 두 겨울 지도·공간파일'],
        ['추가 모델 연구',f'결빙점 가중 학습으로 -2~2°C MAE {near_improvement:.2f}% 감소. 기존 탐지 사건 손실로 교체 보류']],[115,width-115])
    text('분석에서 얻은 판단','h2')
    text('오경보 20,255행 중 19,174행은 관측 노면온도도 0°C 이하였다. 온도를 더 정확히 맞히는 것과 실제 Ice를 구분하는 것은 다른 문제다. 현 단계에서는 강수·적설 대리변수를 보완할 노면 수분과 제설 이력의 확보가 모델 규모 확대보다 우선한다.')
    text('P와 F1은 정의되는 9곳, R은 양성 관측이 있는 8곳의 평균이다. 위 수치는 반복 개발 검증이며 공식 보호 지점 점수가 아니다. 지도는 저온·수분 조건 노출을 나타내며 현장 출동·제설을 자동 결정하는 등급은 아니다.','small')
    page()
    text('1  분석 대상과 자료의 범위','h1')
    text('공식 과제는 관측 공백의 추정, 결빙 영향요인 분석, 구간별 기준표와 지도를 요구한다.[R1] 이 중 공공 기상만으로 산출할 수 있는 노면온도와 저온·수분 조건을 구현했다. 도로환경은 공간 결과의 해석에 사용하며, 현재 온도 모델의 입력에는 포함하지 않았다.')
    table([['자료','사용 범위와 역할'],['RWIS 학습 정답','허용된 23곳의 2024-11-01~2025-02-28. 유효 노면온도 학습 행 397,126개'],
        ['공간 개발 검증','외부 개발 9곳, 4개 공간 그룹. 예측 155,257행 / 온도 유효 155,236행 / 상태 유효 155,118행'],
        ['공공 기상','배포 자료의 AWS 34곳·ASOS 10곳 및 기존 허용 공공 기상. 시점별 가장 최근 과거 관측을 결합'],
        ['두 번째 겨울','2025-11-01~2026-02-28의 공공 기상을 추론에만 사용. 새 정답 학습·선택 없음'],
        ['도로·환경','전북 경계로 자른 고속도로 형상과 시설 속성. 500 m·1 km 구간의 중점에 기상 입력을 연결'],
        ['분리한 자료','보호 3곳, 이미 개봉한 평가 8·4·2곳, 둘째 겨울 정답은 이번 학습·선택·평가에서 제외']],[105,width-105])
    text('관측 공백을 추정하는 문제','h2')
    text('목표 시각보다 엄격히 이전인 60분 이내 기상 관측만 입력에 연결한다. 같은 지점의 노면온도나 노면상태는 입력으로 사용하지 않는다. 학습에는 첫 겨울 전체 기간을 사용하므로 이 결과는 관측이 없는 위치의 사후 공간 추정이다. 미리 발행된 예보만으로 미래 시각을 예측한 성능으로 설명하지 않는다.')
    text('결측과 관측 상태','h2')
    text('상태 코드 04를 Ice로 삼고, 확인된 나머지 상태 코드는 비결빙으로 처리한다. 상태 미상 139행은 정답으로 채우지 않는다. 개발 자료의 예측 공백 21행에는 기존 고정 판정을 적용했지만, 실행 후보는 입력 부족을 null로 반환한다. 보호 3곳의 공백 18행도 같은 방식으로 남긴다.')
    text('이 차이는 모델 비교의 분모와 실제 출력의 가용성이 서로 다른 개념임을 뜻한다. 최종 CSV의 결측 표현과 평가 페널티는 공식 확정 형식에 맞춰야 한다.','small')
    page()
    text('2  모델 구성과 공간 검증','h1')
    text('동일한 12개 기상·시간 변수를 사용하는 두 회귀 모델을 학습했다. 제곱오차 모델은 큰 오차에 더 민감하고, 절대오차 모델은 중앙적인 경향을 학습한다. 두 추정값을 1:1로 평균해 노면온도를 구한다.[R11]')
    table([['단계','구현'],['입력','ASOS/AWS 기온, AWS 습도·풍속·강수·이슬점, 기상 자료 경과시간 2개, 시간·계절 주기 4개'],
        ['온도 회귀','HistGradientBoostingRegressor / 손실 MSE와 MAE / 각 300회 / 학습률 0.05 / 최대 잎 15 / 최소 잎 표본 100 / L2 10'],
        ['결빙 조건','평균 노면온도 ≤ 0°C 이고, 이슬점 ≥ 추정온도 또는 최근 강수 > 0 또는 적설 > 0'],
        ['표시 정보','두 모델 모두 저온인지, 한 모델만 저온인지, 입력이 충분한지를 함께 저장']],[105,width-105])
    text('검증 지점을 모델 선택에서 분리','h2')
    text('개발 9곳을 서천·백양·금산·서상 4개 공간 그룹으로 묶었다. 평가할 그룹 G의 지점은 학습에서 제외한다. G에 적용할 후보를 고를 때도 다른 그룹 H의 예측을 사용하되, 해당 예측을 만든 모델은 G와 H를 모두 제외하고 학습한다. 같은 지역의 정답이 학습과 선택을 거쳐 되돌아오는 것을 막기 위한 구조다.[R9, R10]')
    text('이번 새 연구는 단일 그룹 제외 4개와 이중 그룹 제외 6개의 총 10개 학습 조건에 각각 두 손실을 적용했다. 20개 모델의 학습 지점·행·가중치 해시를 저장하고, 별도 코드로 예측 1,242,056값을 재현했다. 대표 조건의 두 모델도 다시 학습해 동일 출력을 확인했다.')
    text('공식형 일별 지표의 해석','h2')
    text('날짜마다 TP·FP·FN으로 P=TP/(TP+FP), R=TP/(TP+FN), F1=2TP/(2TP+FP+FN)을 계산한 뒤 지점별 날짜 평균과 지점 평균을 구한다. 실제 결빙을 모두 놓친 날은 R과 F1에 0을 넣고 P는 제외한다.[R2] P·R·F1의 포함 날짜 수가 달라, 평균 P와 평균 R의 조화평균은 보고한 F1과 같지 않다.')
    text('이 보고서의 주 비교는 정답 144슬롯이 있는 날짜다. 부분 관측 날짜의 공식 허용량은 미확정이어서 130·72·1슬롯 결과도 별도로 보존했다. 반복 연구에 사용한 개발 자료이므로 공간 제외 자체가 새 독립 평가를 대신하지는 않는다.','small')
    page()
    text('3  현재 후보의 지점별 성능','h1')
    image('station_mae.png',177,'그림 1. 동일한 개발 9곳에서 비교한 노면온도 MAE. 각 지점은 해당 공간 그룹을 제외한 모델로 추정했다.')
    station=pd.read_csv(DIAG/'station_performance.csv',dtype={'station':str});rows=[['지점','MAE °C','BIAS °C','Ice 행','TP','FP','FN']]
    for _,r in station.loc[station.method.eq('pair')].iterrows():
        rows.append([r.station,f'{r.mae:.3f}',f'{r.bias:+.3f}',f'{r.tp+r.fn:,}',f'{r.tp:,}',f'{r.fp:,}',f'{r.fn:,}'])
    table(rows,[55,66,70,66,66,90,width-413])
    text(f'지점을 동일하게 가중한 MAE는 1.232051→1.200440°C로 {macro_improvement:.2f}% 감소했다. 유효 행을 한데 합친 MAE는 1.232271→1.200531°C로 {pooled_improvement:.2f}% 감소했다. 이전 보고서의 1.200531°C에 붙였던 “지점 평균” 표기는 “전체 행 MAE”로 바로잡는다.')
    text('Ice 6,611행 중 6,340행(95.9%)이 33408에 집중되어 있다. 나머지 지점에서는 Ice가 매우 드물어 일별 평균과 전체 행 비율의 의미가 크게 달라진다. 현재 후보의 전체 행 Recall은 1,659/6,611=0.251이며, 일별 지점 평균 Recall 0.775와 구분해야 한다.')
    page()
    text('4  결빙점 가중 학습과 모델 결합','h1')
    text('최근 도로온도 후처리 연구는 0°C 부근 표본에 더 큰 학습 비중을 주는 방식을 제시한다.[R4] 이를 현재 입력 조건에 맞춰 검증했다. 학습 노면온도 y에 대해 w=1+4·exp[-0.5·(y/2)²]를 계산하고 평균이 1이 되도록 정규화했다. 이 식과 폭·계수는 결과를 보기 전에 고정한 응용 가설이며, 원 논문의 식을 그대로 복제한 것은 아니다.')
    rows=[['후보','지점 MAE','-2~2°C MAE','일별 F1','기존 사건 손실']]
    names=[('현재 2종 평균','equal_nohistory_pair'),('가중 MSE','freezing_mse300'),('가중 MAE','freezing_mae300'),
           ('가중 2종 평균','freezing_pair'),('기존 50% + 가중 50%','blend_half'),('기존 75% + 가중 25%','blend_quarter')]
    for label,key in names:
        r=scores[key];rows.append([label,f"{r['temperature']['station_macro']['mae']:.6f}",f"{r['temperature']['near_freezing']['mae']:.6f}",f"{r['ice']['daily']['144']['f1_available_station_mean']:.6f}",r.get('retention',{}).get('lost_events',0)])
    table(rows,[150,82,92,82,width-406])
    text(f'가중 2종 평균은 실제 노면온도 -2~2°C인 42,268행의 MAE를 1.099361→0.912887°C로 {near_improvement:.2f}% 줄였다. 반면 전체 지점 평균 오차는 커졌고, 현재 후보가 잡던 사건 2개를 놓쳤다. 기존 모델에 가중 평균을 25% 섞으면 지점 MAE가 1.194391°C로 작아지지만 일별 F1은 낮아지고 사건 1개가 사라졌다.')
    text('제출 후보를 유지한 이유','h2')
    text('온도 평균 오차, 저온 오차, 각 지점의 손실, 일별 P·R·F1, FP·FN, 기존 탐지 사건을 함께 비교했다. 내부 선택의 네 공간 그룹 모두 새 후보가 전체 조건을 만족하지 못했다. 외부 개발 결과에서 좋아 보이는 조합을 골라 이 결정을 바꾸지 않았다.')
    text('이 결과는 결빙점 가중 학습의 온도 개선 가능성을 보여 준다. 동시에 결빙 분류에 사용할 때의 비용도 드러낸다. 가중 모델은 비교 가능한 연구 산출물로 남기고, 실제 제출 후보의 모델 파일과 예측값은 유지한다.')
    text('손실 사건은 관측 Ice가 연속되는 10분 슬롯 묶음 중, 현재 모델이 한 번 이상 탐지했지만 새 후보는 한 번도 탐지하지 못한 사건이다. 총 탐지 사건 수만 비교하면 이런 교환이 가려질 수 있어 사건의 시작 시각과 지점까지 대조했다.','small')
    page()
    text('5  온도 오차만으로 설명되지 않는 오판','h1')
    image('error_breakdown.png',174,'그림 2. 현재 2종 평균 후보의 오류를 관측 노면온도와 모델 조건으로 분해했다. 개발 상태 유효 155,118행 기준이다.')
    text('오경보의 94.7%는 관측 노면온도도 0°C 이하인 시점이다. 이 구간에서는 온도 추정만 고쳐도 실제 비결빙을 구분하기 어렵다. 공기 중 이슬점·최근 강수·주변 적설은 노면에 남아 있는 물의 양이나 결빙점을 직접 측정하지 않는다.')
    text('미탐 4,952행 중 2,280행은 추정온도가 0°C를 넘었고, 2,672행은 추정온도가 낮아도 수분 대리조건을 만족하지 못했다. 또 관측 Ice 6,611행 중 2,124행에는 0°C보다 높은 노면온도가 함께 기록되어 있었다. 이 동시 기록만으로 센서 오류나 제설 효과를 단정할 수는 없다. 센서의 관측 범위·시각과 실제 도로 상태를 대조할 사례다.')
    table([['설명해야 할 현상','추가로 대조할 정보'],['저온인데 비결빙','노면 수막·잔류 염분, 제설 직후 경과시간, 강수 이후 건조 과정'],
        ['수분 대리조건이 없는데 Ice','현장 수분·잔설, 공공 관측소와 도로 구간의 강수 차이'],
        ['양의 노면온도와 Ice 동시 기록','온도·상태 센서 위치와 대표 면적, 장비 시각, 유지보수 기록']],[145,width-145])
    text('물리 기반 RoadSurf는 열수지와 물·눈·얼음 저장량을 계산하고, 현지 도로 물성의 조정을 요구한다.[R7] 교통량도 열·복사·난류에 영향을 줄 수 있다.[R8] 이 변수들이 없는 현재 자료에서 원인을 임의로 채우기보다, 위 세 현상을 확인할 관측을 먼저 정하는 것이 다음 개선의 출발점이다.')
    text('표의 항목은 오류 원인의 확정 진단이 아니라 확인할 가설이다. 관측된 상태와 온도의 불일치를 이유로 어려운 정답 행을 제거하거나 평가 분모를 줄이지 않았다.','small')
    page()
    text('6  실제 하루 자료에서 본 미탐과 오경보','h1')
    image('error_cases.png',377,'그림 3. 현재 후보에서 FN 또는 FP가 가장 큰 지점일을 고르고, 동률은 지점·날짜 오름차순으로 정했다. 사후 오류 설명용 사례이며 전체 기간의 전형적인 하루를 뜻하지 않는다.')
    text('33408의 2024-12-19에는 관측 Ice 132슬롯을 모두 놓쳤다. 12207의 2025-01-09에는 실제 Ice가 없는 144슬롯을 모두 결빙으로 판정했다. 두 사례 모두 정답 144슬롯이 있어 관측 공백으로 설명되는 사례가 아니다.')
    text('첫 사례에서는 추정 저온이 100슬롯이었지만 수분 조건은 하루 내내 충족되지 않았다. 강수 대리값은 0이고 주변 적설 입력은 없었다. 두 번째 사례에서는 하루 내내 저온·수분 조건을 만족했고, 주변 적설 입력은 5.1~6.8 cm였다. 주변 기상의 수분 조건과 실제 도로 상태가 달라질 수 있음을 보여 준다. 날짜별 입력과 판정은 CSV로 함께 제공한다.')
    page()
    text('7  날짜와 공간 구성에 따른 민감도','h1')
    image('date_sensitivity.png',174,'그림 4. 3·7·14일 연속 블록을 각각 2,000회 재표집한 차이의 중앙값과 2.5~97.5백분위 범위. 모든 지점과 두 모델에 같은 날짜 인덱스를 적용했다.')
    text('10분 행을 독립 표본처럼 섞으면 같은 한파와 연속 관측의 상관을 무시할 수 있다. 이를 피하려고 날짜 블록을 사용했다.[R12] 7일 블록에서 현재 후보와 기존 후보의 지점 평균 MAE 차이는 -0.04884~-0.01396°C였다. 온도 개선의 방향은 세 블록 길이에서 유지됐다.')
    text('F1 차이는 작았다. 3일 블록의 범위는 -0.000018~0.000837로 0을 포함했다. 7·14일 조건의 범위가 양수라고 해서 새로운 지역의 개선을 보장할 수는 없다. 이는 고정된 9곳과 이미 선택된 모델에서 날짜 구성만 바꾼 민감도다. 계절 경계는 순환 처리했고, 학습 및 반복 선택의 불확실성은 재현하지 않았다.')
    rows=[['평균에서 제외한 그룹','남은 지점','MAE 차이 °C','F1 차이']]
    labels={'honam_baekyang':'백양','seohaean_seocheon':'서천','tongyeong_geumsan':'금산','tongyeong_seosang':'서상'}
    for r in diagnostic['group_sensitivity']:
        rows.append([labels[r['excluded_group']],r['stations'],f"{r['mae_difference']:+.6f}",f"{r['f1_difference']:+.6f}"])
    table(rows,[170,80,120,width-370])
    text('서상 3곳을 평균에서 빼면 MAE 차이는 -0.000471°C까지 줄어든다. 평균 개선이 특정 지역에 크게 의존한다는 뜻이다. 해당 지역을 새로 제외해 재학습한 실험이 아니라 기존 예측의 평균 구성만 바꾼 진단이다.')
    text('14일 F1 재표집 2,000회 중 1회는 한 모델의 지점 평균이 정의되지 않아 쌍으로 제외했다. 1,999회만 보고하며, 다른 조건은 2,000회를 모두 사용했다.','small')
    page()
    text('8  구간 지도와 현장 확인 기준','h1')
    image('condition_map.jpg',277,'그림 5. 전북 500 m 구간 중점의 두 겨울 추정 조건 노출. 두 지도에 동일한 0~20% 색 범위를 적용했다. 분모는 각 위치의 유효 추정 시점이다.')
    text('유효 10분 추정 중 저온과 수분 조건이 겹친 비율을 계산한다. 이것을 관측 Ice 비율이나 사고확률로 표시하지 않는다. 같은 기상 입력 조합을 공유하는 구간은 같은 추정값을 가질 수 있어, 500 m 도형의 세밀함을 기상 추정의 실제 공간 해상도로 해석해서는 안 된다.')
    table([['화면의 상태','기상 근거','함께 확인할 도로 정보'],['저온·수분 합의','두 온도 모델 모두 ≤ 0°C, 수분 조건 충족','교량·음영·곡선부와 최근 노면·제설 상태'],
        ['저온·수분 불일치','평균은 ≤ 0°C, 두 온도 모델의 부호가 다름','센서 또는 순찰 관측으로 경계 상태 확인'],
        ['조건 미충족','기상 결합 기준을 만족하지 않음','노면 관측이 다르면 현장 근거를 우선'],
        ['입력 부족','기상 또는 수분 입력 불충분','자료를 보완한 후 판정']],[110,180,width-290])
    text('교량·터널 코드와 구간 중점은 공식 이정 및 실제 시설 범위와 대조가 필요하다. 현재 표에는 검증하지 않은 A/B/C 등급이나 정량 점수를 부여하지 않았다. 1 km 결과도 중점 추정이며 500 m 결과의 길이 가중 집계와는 다르다.','small')
    page()
    text('9  문헌에서 가져온 방법과 적용 조건','h1')
    text('선행 연구는 필요한 입력과 검증 대상이 맞는지 먼저 확인했다. 다른 나라·센서·예측 시간의 점수를 이 과제의 목표치나 달성 성능으로 옮기지 않았다.')
    table([['방법·일차 자료','이 과제에서의 판단'],['결빙점 가중 회귀 [R4]','새 가중 MSE·MAE와 고정 결합을 실제 비교했다. 저온 오차 개선과 사건 손실을 함께 보고 제출 모델 교체를 보류했다.'],
        ['국내 LSTM 예측 [R5]','과거 노면온도를 사용하는 지점별 단기 예측이다. 목표 지점의 노면 관측이 없는 현재 입력 조건과 달라 직접 이식하지 않았다.'],
        ['LSTM·스태킹 [R6]','시간 이력과 OOF 결합의 근거를 검토했다. 현재 기상 이력·결합 실험 결과와 연결하되, RST 이력이나 다른 지역의 성능을 대체 입력으로 삼지 않았다.'],
        ['RoadSurf 열·수분 모형 [R7]','수분 저장량·물성의 필요성을 오류 해석에 반영했다. 지역별 초기값·복사·물성 없이 물리 모형을 재현했다고 주장하지 않았다.'],
        ['교통 영향 물리 모형 [R8]','교통이 도로온도에 영향을 줄 수 있는 경로를 검토했다. 실제 교통량 없이 임의 계수를 적용하지 않았다.'],
        ['공간 검증·선택 편향 [R9, R10]','공간 그룹 분리와 내부 후보 선택을 유지했다. 반복 개발 성능과 새 지역 성능을 구분했다.'],
        ['날짜 블록 재표집 [R12]','동일 날짜를 여러 지점에 함께 적용했다. 세 블록 길이를 모두 제시하고 유리한 길이만 보고하지 않았다.'],
        ['겨울 도로 운영 지침 [R13]','기상·노면·순찰·처리 이력의 결합 원칙을 현장 확인 순서에 반영했다. 현지 제설 기준이나 살포량으로 전용하지 않았다.']],[146,width-146])
    text('추가 자료의 우선순위','h2')
    text('첫째, 33408의 긴 Ice 기록과 양의 노면온도가 함께 나타나는 시각을 센서 이력으로 대조한다. 둘째, 최근 강수와 실제 노면 수분의 차이를 확인한다. 셋째, 미사용 지점에서 현재 후보와 고정된 비교 후보를 한 번 평가한다. 이 순서는 이번 오류 분포에서 정한 분석 판단이다.')
    page()
    text('10  실행 방법과 제출 판단','h1')
    text('실행 후보는 허용 23곳의 첫 겨울 유효 노면온도 397,126행으로 학습한 고정 2모델이다. Python 3.11과 CPU를 사용하며 GPU는 필요하지 않다. 포함한 기상 예제와 모델로 외부 접속 없이 추론할 수 있다.')
    table([['목적','패키지 루트에서 실행'],['설치','python -m pip install -r requirements.txt'],
        ['예제 추론','python -X utf8 code/predict.py --input data/weather_example.csv --output validation/new_example.csv'],
        ['대표 모델 재학습','python -X utf8 code/train.py --output validation/new_models'],
        ['보호 위치 CSV','python -X utf8 code/export_predictions.py --kind protected --output validation/target_csv'],
        ['개발 점수 검산','python -X utf8 code/reproduce_development.py --output validation/new_metrics']],[100,width-100])
    text('CSV는 부동소수점 값을 무손실로 읽는다. 과거에는 기본 파서의 마지막 비트 차이로 트리 분기가 바뀌어 예제 온도 5행이 달라졌고, 읽기 방식을 수정해 재현을 확인했다. 기존 출력 경로는 덮어쓰지 않는다.')
    text('제출 준비 상태','h2')
    table([['완료한 내용','확인할 조건'],['저장 모델·예측·지도·실행 데모','최종 CSV 열·행키·결측 표기·파일명은 공식 형식으로 확정 필요'],
        ['학습·검증 소스와 수치 검산','새 지점의 개선 재현과 최종 모델 채택 판단 필요'],
        ['조건 기준표와 공간 결과','공식 이정·시설 범위·현장 상태를 대조해 운영 수준 결정 필요'],
        ['보고서와 AI 활용 기록','참가자의 해석·제출 문구 검토 및 공식 제출 일정 확인 필요']],[205,width-205])
    text('현재 공지의 결과 제출 시작일과 마감 날짜는 별도 안내 대상이다. 참가신청 종료 11월 6일을 결과물 마감으로 사용하지 않는다.[R3] 대회 제공 자료와 파생 결과는 참가 권한 안에서 비공개로 보관한다.')
    text('분석 설계·코드·실험·문서 개편에 Codex 지원을 사용했다. 주요 선택과 검증은 AI_USAGE.md에 기록한다. 실제로 하지 않은 현장 조사나 참가자 검토를 수행한 것으로 쓰지 않았다.','small')
    page()
    text('참고 문헌과 근거 자료','h1')
    for identifier,title,url,role in REFERENCES:
        text(f'<b>[{identifier}]</b> {html.escape(title)}<br/><link href="{html.escape(url,quote=True)}" color="#176b88">{html.escape(url)}</link><br/>{html.escape(role)}','small')
    target=out/'전북_고속도로_결빙_분석_보고서.pdf'
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#cad6dd'));canvas.line(46,39,A4[0]-46,39)
        canvas.setFont('Malgun',7.4);canvas.setFillColor(colors.HexColor('#607784'))
        canvas.drawString(46,26,'전북 고속도로 결빙 분석  |  비공개 검토본  |  2026-10-14')
        canvas.drawRightString(A4[0]-46,26,str(doc.page))
    document=SimpleDocTemplate(str(target),pagesize=A4,leftMargin=46,rightMargin=46,topMargin=43,bottomMargin=54,
        title='전북 고속도로의 노면온도 추정과 결빙 조건 분석',author='icy-road-ai')
    document.build(story,onFirstPage=footer,onLaterPages=footer)
    (out/'전북_고속도로_결빙_분석_보고서.md').write_text('\n\n'.join(manuscript)+'\n',encoding='utf-8')
    for name in ['station_performance.csv','weather_condition_associations.csv','leave_one_group_sensitivity.csv','fn_case.csv','fp_case.csv']:
        shutil.copy2(DIAG/name,out/name)
    write(out/'references.json',[dict(id=i,title=t,url=u,application=r) for i,t,u,r in REFERENCES])
    with fitz.open(target) as pdf:
        assert len(pdf)==12, 'Unexpected report overflow'
        for i,p in enumerate(pdf):p.get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(out/'preview'/f'page_{i+1:02d}.png')
        texts=[p.get_text() for p in pdf]
        write(out/'render_receipt.json',dict(created_at_utc=datetime.now(timezone.utc).isoformat(),pages=len(pdf),
            pdf_sha256=sha(target),text_lengths=[len(t) for t in texts],visual_review_pending=True,
            source_experiment_summary_sha256=sha(RESEARCH/'summary.json'),source_diagnostic_summary_sha256=sha(DIAG/'summary.json')))
        (out/'extracted_text.txt').write_text('\n\n'.join(texts),encoding='utf-8')
        print('PDF 생성',len(pdf),'쪽',target,flush=True)


if __name__ == '__main__':
    main()
