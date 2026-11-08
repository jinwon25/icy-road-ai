"""결과와 해석을 중심으로 도로기상 분석 보고서를 조판한다."""
from pathlib import Path
import sys,html,re
import fitz,pandas as pd
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Image,Table,TableStyle,PageBreak,KeepTogether
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,sha
P=ROOT/'outputs/private';B=P/'final_jury_review_20261106/icy_road_model';W=P/'final_jury_review_20261106';O=B/'report';F=O/'figures'

def main():
 pdf=O/'analysis_report.pdf';assert not pdf.exists()
 # 현 판정법의 개발 지역 오경보를 실제 상태 원코드로 분해한다.
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib import font_manager
 import numpy as np
 evidence=read(B/'technical/development_error_analysis.json')
 raw_states=pd.read_csv(B/'results/evaluation/development_false_alarm_states.csv')
 groups=[('건조 (01·10)',[1,10]),('습윤 (02·11)',[2,11]),('적설 (03)',[3]),('기타 유효 상태 (12·13·14·15)',[12,13,14,15])]
 values=[int(raw_states.loc[raw_states.state.isin(ids),'fp'].sum()) for _,ids in groups]
 assert sum(values)==evidence['fp']==25341
 plt.rcParams.update({'font.family':font_manager.FontProperties(fname='C:/Windows/Fonts/malgun.ttf').get_name(),
  'axes.unicode_minus':False,'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':False,
  'axes.edgecolor':'#AAB8C0','text.color':'#26343D','axes.labelcolor':'#26343D'})
 fig,ax=plt.subplots(figsize=(8.8,3.2))
 ax.barh(np.arange(4),values,height=.53,color=['#29546D','#5C7D8D','#AEC0C8','#809CA9'])
 ax.set_yticks(np.arange(4),[name for name,_ in groups]);ax.invert_yaxis();ax.tick_params(axis='y',length=0,pad=10)
 ax.set_xlim(0,max(values)*1.3);ax.set_xlabel('10분 관측 기준 오경보 건수')
 for i,value in enumerate(values):ax.text(value+max(values)*.02,i,f'{value:,}  ({value/sum(values)*100:.1f}%)',va='center',fontsize=10)
 ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True);fig.tight_layout(pad=1.0)
 fig.savefig(F/'false_alarm_states.png',dpi=300,bbox_inches='tight')
 fig.savefig(F/'false_alarm_states.svg',bbox_inches='tight');plt.close(fig)

 pdfmetrics.registerFont(TTFont('Body','C:/Windows/Fonts/malgun.ttf'));pdfmetrics.registerFont(TTFont('Bold','C:/Windows/Fonts/malgunbd.ttf'))
 ink=colors.HexColor('#26343D');blue=colors.HexColor('#29546D')
 body=ParagraphStyle('BodyText',fontName='Body',fontSize=10,leading=16.2,textColor=ink,spaceAfter=10,wordWrap='CJK')
 title=ParagraphStyle('Title',parent=body,fontName='Bold',fontSize=21,leading=29,spaceAfter=17)
 cover=ParagraphStyle('Cover',parent=title,fontSize=27,leading=36,spaceAfter=15)
 small=ParagraphStyle('Small',parent=body,fontSize=8.7,leading=13.3,spaceAfter=8)
 heading=ParagraphStyle('Heading',parent=body,fontName='Bold',fontSize=12,leading=19,spaceBefore=8,spaceAfter=8)
 lead=ParagraphStyle('Lead',parent=body,fontSize=11,leading=18.5)
 stat=ParagraphStyle('Stat',parent=body,fontName='Bold',fontSize=23,leading=28,textColor=blue,spaceAfter=5)
 story=[];md=['# 전북 고속도로의 겨울철 노면온도 추정과 결빙 취약구간 검토'];figure_number=0
 def p(s,style=body):story.append(Paragraph(s,style));md.append(s.replace('<b>','').replace('</b>',''))
 def h(s):story.append(Paragraph(s,heading));md.append('### '+s)
 def page(s):
  if story:story.append(PageBreak())
  story.append(Paragraph(s,title));md.extend(['','## '+s,''])
 def table(rows,widths):
  cells=[[Paragraph(html.escape(str(v)).replace('&lt;br/&gt;','<br/>'),small) for v in row] for row in rows]
  item=Table(cells,colWidths=widths,hAlign='LEFT',repeatRows=1)
  item.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEABOVE',(0,0),(-1,0),.8,blue),('LINEBELOW',(0,0),(-1,0),.6,blue),('LINEBELOW',(0,1),(-1,-1),.35,colors.HexColor('#D6DEE2')),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#F1F5F6')),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
  story.extend([item,Spacer(1,9)])
  md.append('\n'.join(['| '+' | '.join(map(str,rows[0]))+' |','| '+' | '.join(['---']*len(rows[0]))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows[1:]]))
 def picture(name,height=260,caption=''):
  nonlocal figure_number
  figure_number+=1;caption=f'그림 {figure_number}. '+re.sub(r'^그림 [0-9]+\.\s*','',caption)
  path=F/(name+'.png');im=PILImage.open(path);w=507;ht=w*im.height/im.width
  if ht>height:w*=height/ht;ht=height
  story.extend([Image(str(path),width=w,height=ht),Spacer(1,6)])
  if caption:p(caption,small)
  md.append(f'![{caption or name}](figures/{name}.png)')
 m=read(B/'technical/evaluation_metrics.json')
 # 요약은 도로 지도와 관측에 근거한 세 가지 결과로 시작한다.
 story.append(Paragraph('전북 고속도로의<br/>겨울철 노면온도 추정과<br/>결빙 취약구간 검토',cover))
 p('서해안·통영-대전·호남 고속도로 / 2024년 11월-2026년 2월의 두 겨울',small)
 p('센서가 없는 도로의 기상과 노면온도를 추정하고,<br/>추가 관측과 시설 확인이 필요한 범위를 좁혔다.',lead)
 im=PILImage.open(F/'study_area.png');w=290;ht=w*im.height/im.width
 findings=[Paragraph('0.98°C',stat),Paragraph('학습에서 제외한 3지점의<br/>노면온도 MAE 평균',body),Spacer(1,16),
  Paragraph('14.6%',stat),Paragraph('같은 관측쌍에서 12특성 회귀 대비<br/>노면온도 MAE 감소',body),Spacer(1,16),
  Paragraph('3구간',stat),Paragraph('선정 기준에 남은 추가 계측 후보<br/>기존 목록과의 관계도 함께 제공',body)]
 layout=Table([[Image(str(F/'study_area.png'),width=w,height=ht),findings]],colWidths=[315,192],hAlign='LEFT')
 layout.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]));story.extend([layout,Spacer(1,10)])
 p('분석 대상은 500m 도로 843구간이다. AWS·ASOS의 과거 관측으로 기상과 노면온도를 추정하고, 저온·수분 조건의 빈도에 교량·선형 정보를 연결했다. 노면온도는 103,659개 관측쌍에서 지점 평균 MAE 0.978°C를 보였다. 비교 가능한 103,131쌍에서는 기본 12특성 회귀보다 MAE가 14.6% 낮았다. 구간 선정의 기준 민감도와 지형 차폐도 함께 계산했다. 결빙 F1은 0.033으로 낮아, 활용 범위는 관측 공백 보완과 현장 확인에 두었다.')
 p('로드투인사이트 / 2026 DATA·AI 분석 경진대회  문제해결 부문  |  전북 고속도로 기상·결빙 과제',small)
 md.append('요약: 노면온도 MAE 0.978°C, 12특성 회귀 대비 공통 쌍 MAE 14.6% 감소. 기준 조합 3구간과 75개 기준의 민감도를 제공한다. 결빙 F1 0.033의 한계를 포함한다.')
 page('자료와 분석 방법')
 table([['자료','범위와 역할'],['도로기상 관측','제공 17지점 중 학습14·검증3. 공개 RWIS 9지점 추가[11]'],['일반 기상 관측','AWS·ASOS의 기온, 습도, 풍속, 강수, 적설, 이슬점 등. 과거 이력과 태양위치 파생 특성'],['도로·시설·지형','전북 3노선의 중심선·교량·터널 코드와 공개 GLO-30 DSM. 500m 보고 단위 843개'],['공개 취약구간 목록','과제의 취약구간 표와 한국도로공사 공개 목록(2026.09.07). 기준일과 방향 정보를 구분'],['평가 기간','2024.11.01-2025.02.28 및 2025.11.01-2026.02.28. 각 120일, 10분 KST']],[116,391])
 h('노면온도와 도로 기상')
 p('노면온도는 학습 허용 23지점의 유효 관측쌍 793,149개로 기상·이력·태양위치 63특성의 HistGradientBoosting 회귀를 학습했다. 기온·습도·풍속은 기상 관측값과 도로 관측값의 잔차를 학습했다. 풍속에는 반경 50km의 가까운 AWS 최대 4곳에서 얻은 거리 가중 통계 35개를 더해 69특성을 사용했다.')
 p('입력 관측은 추정 시각보다 앞선 자료만 사용했다. ASOS의 허용 시간차는 최대 60분이다. 도로 기상 모형의 AWS는 최대 15분, 노면온도·결빙 입력의 AWS는 최대 60분으로 제한했다. 타 지점의 같은 시각 노면상태는 입력에서 제외했다. 제공 DEM은 정규화 값이므로 미터 고도나 경사도로 사용하지 않았다.')
 h('결빙 조건과 평가 설계')
 p('결빙 판정의 기준온도 Tref는 기본 기상 12특성으로 절대오차·제곱오차를 각각 학습한 두 회귀 모형의 평균이다. 제출 노면온도인 63특성 모형의 출력과 역할을 구분한다. Tref가 0°C 이하이고, AWS 이슬점이 Tref 이상이거나 최근 3시간의 AWS 15분 강수 최댓값 또는 ASOS 적설이 양수일 때 결빙으로 판정했다. 수분 관련 입력이 모두 없으면 판정을 보류했다.')
 p('노면온도 개발 평가는 9지점, 기상 평가는 4지역을 사용했다. 인접 자료의 유사성이 평가를 낙관적으로 만들지 않도록 지역 전체를 제외하고, 기상은 겨울도 함께 제외한 결과를 추가 산출했다[3]. 제출 평가 3지점은 학습에서 제외했다. 두 결빙 판정법의 출력을 고정한 뒤 관측과 대조했으며, 보고된 결과는 이 고정 대조의 성적이다. 보호 지점의 관측값을 이용해 새 모형을 학습하거나 문턱을 조정하지 않았다.')
 p('구간 노출의 분위수에는 실제 결빙 조건 입력 14열의 전체 시계열이 같은 조합을 한 번씩 집계했다. 후보 관측소 조합은 겨울별 68개지만 고유 입력은 각각 22개·24개다. 136개 조합의 2,350,080행을 대조했고 같은 배열인 90개 중복을 확인했다. 이 개수는 독립 관측 표본 수를 뜻하지 않는다.',small)

 page('학습에서 제외한 지점의 노면온도')
 p('부곡교·해전·삼봉의 두 겨울 관측과 동일한 10분 시각의 추정값을 비교했다. 계획 103,680시점 중 유효한 노면온도 관측·추정 쌍은 103,659개다. BIAS는 추정값에서 관측값을 뺀 값이다.')
 picture('road_temperature',228,'그림 1. 지점별 관측·추정 노면온도의 전체 밀도. 점선은 관측과 추정이 같은 선이다.')
 rows=[['지점','유효쌍','BIAS (°C)','MAE (°C)','RMSE (°C)']]
 names={'12410':'부곡교','23402':'해전','33411':'삼봉'}
 for r in m['temperature']:
  if r['station']=='pooled':continue
  rows.append([names[r['station']],f"{r['n']:,}",f"{r['bias']:.3f}",f"{r['mae']:.3f}",f"{r['rmse']:.3f}"])
 t=m['temperature_station_macro'];rows.append(['지점 평균','-',f"{t['bias']:.3f}",f"{t['mae']:.3f}",f"{t['rmse']:.3f}"]);table(rows,[90,87,110,110,110])
 p('세 지점의 MAE 평균은 0.978°C다. 부곡교와 해전에서는 약 -0.97°C의 편향이 남고, 삼봉은 약 +0.30°C다. 평균 오차가 1°C 안팎이어도 0°C 부근의 판정에는 이 편향이 영향을 줄 수 있다. 지점별 상수 보정을 평가값에 맞춰 적용하지 않았다.')
 p('표의 평균은 지점을 동일 가중한 값이다. 모든 관측쌍을 합친 MAE는 0.977566°C, RMSE는 1.282743°C이며 지점별 RMSE 평균과 집계 방식이 다르다.',small)

 page('비교 기준으로 확인한 노면온도 추정의 가치')
 p('추정값과 실측값의 오차만으로는 단순 관측소 기준보다 얼마나 나은지 알기 어렵다. 기온·지면온도와 기본 12특성 회귀를 함께 비교했다. 모든 방법에 유효한 관측쌍만 남겨 같은 시각과 같은 지점에서 평가했다.')
 picture('temperature_benchmarks',210,'같은 축에서 비교한 지점 평균 MAE. 전체 범위 103,131쌍, 관측 노면온도 -2~+2°C 범위 23,545쌍이다.')
 rows=[['지점','12특성 MAE (°C)','현재 MAE (°C)','감소율']]
 bm=pd.read_csv(B/'results/evaluation/temperature_benchmarks/metrics.csv',dtype={'station':str})
 for station,label in [('12410','부곡교'),('23402','해전'),('33411','삼봉')]:
  q=bm.loc[bm.temperature_scope.eq('all_temperature')&bm.period.eq('all')&bm.station.eq(station)].set_index('method')
  a=q.loc['weather12_regression','mae'];b=q.loc['estimated','mae']
  rows.append([label,f'{a:.3f}',f'{b:.3f}',f'{100*(1-b/a):.1f}%'])
 table(rows,[95,145,145,122])
 p('공통 관측쌍의 지점 평균 MAE는 12특성 회귀 1.146°C에서 현재 모형 0.978°C로 14.6% 감소했다. 관측 노면온도가 -2~+2°C일 때도 0.891°C에서 0.789°C로 11.4% 낮았다. 두 회귀의 입력·학습 구성이 함께 달라진 비교이므로, 이 감소를 특정 입력 하나의 효과로 해석하지 않는다.')
 p('날짜의 연속성과 세 지점에 공통으로 작용한 날씨를 고려해 겨울별 7일 연속 블록을 2,000회 재표본화했다. 현재 모형에서 12특성 회귀를 뺀 MAE 차이의 2.5~97.5백분위는 -0.202~-0.135°C였다. 이 구간은 해당 세 지점·두 겨울의 날짜 민감도이며 새로운 도로 모집단의 보장 범위는 아니다.',small)
 p('ASOS 지면온도가 없는 시각 등이 제외되어 이 비교의 분모는 앞쪽 주평가 103,659쌍보다 작다. 공통 관측쌍 비교와 각 모형의 전체 유효쌍 평가는 분모를 구분해 읽어야 한다.',small)

 page('도로 기상 추정')
 p('관측 공백 도로의 기상을 추정한 뒤, AWS 우선 기준선과 같은 지역 제외 분할에서 비교했다. 기온·습도·풍속의 MAE는 각각 1.324°C, 5.687%p, 0.500m/s다. 지역과 겨울을 동시에 제외했을 때 풍속 MAE는 0.508m/s였다.')
 weather=pd.read_csv(B/'results/evaluation/weather_metrics.csv');rows=[['대상','유효쌍','AWS 기준선 MAE','추정 MAE','감소율']]
 for target,label,unit in [('air_temperature','기온','°C'),('relative_humidity','습도','%p'),('wind_speed','풍속','m/s')]:
  q=weather.loc[weather.target.eq(target)&weather.validation.eq('spatial')].set_index('method');a=q.loc['aws_reference','mae'];b=q.loc['estimated','mae']
  rows.append([label,f"{int(q.loc['estimated','n']):,}",f'{a:.3f} {unit}',f'{b:.3f} {unit}',f'{(1-b/a)*100:.1f}%'])
 table(rows,[62,85,130,130,100])
 picture('wind_distribution',240,'그림 2. 같은 색 범위로 비교한 두 겨울 평균 풍속. 지도는 구간 추정값이며, 각 구간의 실측 검증 성적을 나타내지 않는다.')
 p('지정 검증 3지점의 기온·습도·1분 풍속은 제공 원본에서 모두 결측코드였다. 예측 103,680행을 먼저 고정한 뒤 가용성을 확인했으며, 세 기상 요소의 유효 관측쌍은 각각 0개다. 해당 성능은 NA로 두고 다른 관측소 값을 도로 실측 정답으로 대체하지 않았다. 위 표는 이 세 지점의 점수가 아니라 별도 지역 제외 평가다.',small)
 p('노면 에너지 교환에는 기온·수분·바람·복사 조건이 함께 작용한다[2]. 여기서는 열수지를 직접 적분하는 대신 관측 기반 회귀로 자료 공백을 보완했다. 기상 공간 분포를 다루는 MicroMet의 관점[4]을 참고하되, 지형 보정 물리모형을 구현한 것으로 해석하지 않는다.')
 page('결빙 판정의 성능과 오경보')
 p('노면상태 Ice만 양성으로 두고 나머지 유효 상태와 구분했다. 실제 Ice는 부곡교의 64시점·19일에 관측됐다. 해전·삼봉은 실제 결빙이 없어 분류 평균에서 제외했다. 무양성 지점 제외와 날짜별 지표의 처리에는 과제 질의응답의 집계 규칙을 적용했다[1].')
 table([['판정법','Precision','Recall','F1'],['기준온도 + 수분 대용조건','0.0195','0.5936','0.0326'],['ASOS 기온 0°C 기준선','0.0048','0.7353','0.0087']],[210,99,99,99])
 picture('icing_calendar',136,'그림 3. 부곡교에서 하루 중 Ice가 한 번 이상 관측되거나 판정된 날짜. 짙은 칸이 해당 날짜이며 회색 칸에는 양성이 없다.')
 p('두 겨울의 관측 결빙일은 각각 14일·5일이고 판정일은 26일·18일이다. 관측 양성일을 놓친 날은 2일·1일, 관측 양성 없이 판정만 발생한 날은 각각 14일이다. 기온 기준선보다 오경보를 줄였지만 정밀도는 약 2%에 머물렀다.')
 h('지표를 읽는 기준')
 p('Precision·Recall·F1은 날짜별로 계산한 뒤 지점별 기간 평균과 지점 평균을 구했다. 기준온도·수분 판정법에 포함된 날짜 수는 각각 44일·19일·47일이다. 오경보만 있는 날의 Recall과 미탐만 있는 날의 Precision은 평균에서 제외하고, 미탐의 Recall·F1은 0으로 포함했다. 하루 144유효쌍만 인정한 계산에서도 F1은 같았다.')
 p('현재 입력의 강수·이슬점·적설은 실제 노면수분의 대용값이다. 낮은 정밀도는 이 구성만으로 Ice를 확정하기 어렵다는 결과다. 노면수분·염분·제설 시각을 함께 관측해 오경보 원인을 검증하는 것이 우선이다. 온도 추정의 개선을 결빙 탐지의 개선으로 대신 평가하지 않았다.')

 page('영하·적설 조건과 실제 결빙 사이의 차이')
 p('부곡교·해전·삼봉의 보호 평가와 별도로, 현재 판정법의 오경보를 개발 9지점·두 겨울에서 분해했다. 지역 전체를 제외한 예측과 유효 정답 309,928쌍에서 오경보는 25,341건이었다. 관측 노면온도·상태는 이 진단의 원인 분석에만 사용했다.')
 numbers=Table([[Paragraph('94.3%',stat),Paragraph('98.8%',stat)],
  [Paragraph('오경보 중 실제 노면온도도 영하',body),Paragraph('오경보 중 ASOS 적설 근거가 있음',body)]],
  colWidths=[253.5,253.5],hAlign='LEFT')
 numbers.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),5),('LEFTPADDING',(0,0),(-1,-1),0)]))
 story.extend([numbers,Spacer(1,9)])
 md.append('오경보 중 94.3%는 실제 노면온도가 영하였고, 98.8%는 ASOS 적설 근거가 있었다. 두 조건은 서로 겹친다.')
 h('온도 부호만 맞춰서는 구분하기 어려웠다')
 p('실제 노면온도가 0°C 이하인 오경보는 23,891건이었다. 당시 노면상태에는 건조·습윤 등 Ice 이외의 상태가 함께 있었다. 노면온도의 오차를 줄이는 것과 현재 도로의 Ice를 구분하는 것은 별도 과제다. 도로 수분·동결·해빙과 교통에 의한 변화가 구별돼야 한다는 RoadSurf의 물리적 구분[2]도 이 차이를 설명한다.')
 picture('false_alarm_states',205,'그림 4. 개발 9지점의 오경보를 실제 노면상태로 분해한 결과. 기타 유효 상태에는 제빙 관련·임계 습윤·불확실 상태 등이 포함된다. 날짜별 평균 정밀도와 달리 전체 10분 관측 건수를 센 그림이다.')
 h('주변 적설을 도로 위 얼음의 직접 증거로 보지 않았다')
 p('ASOS 적설이 근거에 포함된 오경보는 25,030건이었지만, 실제 노면 적설 상태(03)는 오경보 중 970건(3.8%)이었다. 주변 관측소 지면의 잔존 적설과 대상 도로의 상태는 다를 수 있다. 제설·제빙 시각, 노면수분·염분과 설치 지점의 시설 조건을 추가로 확인해야 한다.')
 p('따라서 다음 공간 결과의 저온·수분 조건 비율은 실제 결빙 확률로 해석하지 않았다. 관측 공백과 도로환경을 함께 살펴, 직접 계측과 현장 확인이 필요한 범위를 선정하는 데 사용했다.')


 page('기상요소와 결빙 조건의 관계')
 p('843개 구간·두 겨울의 일별 추정 자료 202,320행에서 기상요소와 조건 빈도의 연관성을 계산했다. 표는 각 구간의 최대 120일 Pearson 상관계수의 중앙값이다. 전체 구간별 값과 유효 일수, Spearman 결과는 CSV로 제공한다.')
 ar=pd.read_csv(B/'results/conditions/association_ranges.csv')
 rows=[['AI 추정 일평균 요소','2024/25 r 중앙값','2025/26 r 중앙값']]
 for key,label in [('air_temperature_mean','기온'),('relative_humidity_mean','상대습도'),('wind_speed_mean','풍속')]:
  z=ar.loc[ar.predictor.eq(key)&ar.target.eq('cold_wet_fraction')&ar.method.eq('pearson')].set_index('winter')
  rows.append([label,f"{z.loc[2024,'median']:+.3f}",f"{z.loc[2025,'median']:+.3f}"])
 table(rows,[207,150,150])
 p('기온과 조건 빈도는 음의 연관성을 보였다. 다만 추정 모형과 조건식이 입력을 공유해 계산 구조도 반영된다. 500m 구간과 연속 날짜를 독립 관측으로 간주하지 않았고, 이 상관을 실제 Ice의 인과효과나 새 결빙 문턱으로 사용하지 않았다.')
 h('실제 Ice가 관측된 기상 조건')
 picture('observed_ice_conditions',205,'개발 9지점의 지역 제외 기준온도와 실제 Ice를 대조한 309,928개 유효쌍. 색은 수분 대용조건 유무를 구분한다.')
 p('개발 자료의 실제 Ice는 6,687시점이었다. 기준온도 -2°C 이하·수분 조건 있음에서는 18,337쌍 중 1,291쌍(7.0%)이 Ice였다. 같은 온도 범위에서 수분 조건이 검출되지 않았을 때는 39,869쌍 중 1,634쌍(4.1%)이었다. 저온·수분의 동반은 참고 근거지만 이를 실제 얼음의 충분조건으로 볼 수 없다.')
 p('온도 구간은 -2°C 이하, -2°C 초과 0°C 이하, 0°C 초과 2°C 이하, 2°C 초과로 사전 고정했다. 그림은 전체 10분 관측의 빈도다. 공식 날짜별 Precision 평균과 집계가 다르며, 지점별 빈도와 지점 동일 가중 평균도 원표에 남겼다.',small)

 page('겨울별 조건 노출과 도로환경')
 p('구간별 노출 비율은 유효한 10분 판정 중 저온·수분 조건을 만족한 비율이다. 두 겨울의 결과를 같은 척도로 비교하고, 노선별 평균은 구간 길이로 가중했다. 노면의 실제 결빙 빈도나 사고확률을 산출한 값은 아니다.')
 picture('condition_exposure',270,'그림 5. 저온·수분 조건 비율. 두 겨울의 기상 차이를 같은 색 범위로 표시했다.')
 picture('route_exposure',148,'그림 6. 노선별 길이 가중 조건 비율. 통영-대전은 17.1%에서 3.2%로, 서해안은 11.2%에서 4.5%로 달라졌다.')
 p('노선의 상대적인 순서도 겨울에 따라 바뀐다. 도로에 고정된 한 등급을 부여하기보다 대상 겨울과 관측 기간을 함께 확인해야 한다. 같은 기상 입력을 공유하는 500m 구간이 있으므로 843개를 독립적인 기상 관측으로 세지 않았다.')
 p('도로환경 점검에는 교량 코드와 25m 간격으로 재표본화한 중심선의 100m당 방향 변화를 사용했다. 교량의 냉각 특성은 도로 관리기관의 안내[5]를 참고했다. 방향 변화는 설계 곡률·회전반경과 다르며 터널 내부·입출구에 동일한 위험 가중치를 주지 않았다.')
 page('공개 목록과 기상 기준의 관계')
 p('2026년 9월 7일 공개 목록의 8개 항목이 전북 분석 중심선의 64개 500m 구간과 명목상 겹쳤다. 이정은 공식 암거 기준점 사이를 보간한 값이며, 실제 시설 범위를 측량해 확정한 결과는 아니다.')
 picture('inventory_agreement',245,'공개 목록과 명목상 겹치는 64구간 중 겨울별 기상 문턱을 충족한 개수와 위치. 음영은 현재 선정 기준인 상위 25%다. 목록 미포함 구간을 비결빙 정답으로 사용하지 않았다.')
 table([['대조 범위','구간 수','해석'],['명목상 목록 중첩','64','공개 목록 8개 항목과 추정 이정이 겹침'],['±250m 안에서 중첩 가능','81','목록 경계의 위치 민감도를 포함'],['기상 상위 25%를 두 겨울 모두 충족','0 / 64','목록 제외 조건을 적용하기 전의 비교']],[159,75,273])
 p('기상 상위 25% 조건을 충족한 목록 대조 구간은 첫 겨울 30개, 둘째 겨울 0개였다. 이 두 겨울의 기상 조건으로 기존 취약구간 목록을 재현하지 못했다. 문턱을 바꾼 전체 비교를 함께 제공하고, 이 결과에 맞춰 선정 문턱을 다시 고르지 않았다.')
 p('종합 지도에는 공개 목록의 추정 중첩을 표시한 상태에서 추가 계측 후보와 도로환경 조건을 함께 보여 준다. 기존 취약구간의 관리를 이 기상 기준으로 축소하지 않는다. 관측 상태와 관리용 지수의 목적을 명시하는 최근 도로기상 프레임워크[12]도 참고했다.')
 p('이정 연결이 없는 22구간은 목록 밖으로 확정하지 않았다. 목록의 기준일은 두 겨울 뒤이므로 이 비교는 실제 Ice의 독립 검증이나 기존 지정의 정확도 평가가 아니다.',small)

 page('추가 계측·시설 확인 범위')
 p('기상 노출과 도로환경을 같은 500m 구간에 연결하고, 다음 조건을 모두 충족하는 범위를 추렸다. ① 두 겨울 모두 실제 14입력 시계열의 중복을 제외한 75백분위 이상의 노출, ② 교량 코드 또는 선형 변화 상위 구간, ③ 판정 가용률 95% 이상, ④ 공개 취약구간 목록의 ±250m 범위 밖이며 이정 추정이 가능한 구간이다.')
 picture('inspection_locations',265,'그림 7. 추정 이정 위의 취약구간 목록과 추가 확인 범위. 방향이 없는 문제 표는 비교를 위해 양방향에 표시했다. 공개 목록은 2026.09.07 기준이다[7].')
 p('선정 결과는 서해안의 3구간·2개 연속 범위이며, 같은 진행 방향에서 총 1.5km다. 세 구간은 겨울마다 같은 하나의 결빙 조건 입력 시계열을 공유한다. 모두 교량 코드가 아닌 선형 변화 기준으로 선정됐다. 서로 독립적인 위험 발견 세 건으로 해석하지 않는다.')
 table([['검토 범위','방향과 추정 이정','조건 비율<br/>2024/25 → 2025/26'],['S01 서해안','서천·군산 → 고창·영광<br/>79.81-80.84km / 2구간','13.0% → 6.8%'],['S02 서해안','서천·군산 → 고창·영광<br/>84.28-84.81km / 1구간','13.0% → 6.8%']],[95,265,147])
 p('이정은 공식 암거 좌표·이정으로 중심선 사이를 보간한 값이다[8]. ±250m는 목록과의 관계를 살피기 위한 민감도 조건이며 측량 오차의 신뢰구간은 아니다. 지도에서 시설의 실제 범위와 그늘·배수·노면수분을 확인한 뒤 계측 위치를 정하는 자료로 사용한다. 두 범위와 구간 키는 CSV·GIS에 제공한다.')

 page('선정 기준을 바꾸면 남는 구간')
 p('상위 기상 빈도와 중심선 방향 변화의 기준을 각각 상위 40·30·25·20·10%로, 공개 목록의 경계 여유를 ±100·250·500m로 바꾼 75개 조합을 비교했다. 기준 조합은 상위 25%·상위 25%·±250m이며 모든 결과를 함께 제시한다.')
 picture('selection_sensitivity',185,'75개 자체 기준 조합의 선택 구간 수. 갈색 테두리가 기준 조합 3구간이다. 모든 그림의 색 범위는 0~86개로 같다.')
 rows=[['기준 범위','500m 구간 수','75개 조합의 선택 유지율']]
 stability=pd.read_csv(B/'results/sections/sensitivity/area_stability.csv')
 for r in stability.itertuples():
  a=100*r.minimum_selection_fraction;b=100*r.maximum_selection_fraction
  rows.append([r.inspection_area_id,int(r.segments),f'{a:.0f}%' if a==b else f'{a:.0f}~{b:.0f}%'])
 table(rows,[100,145,262])
 p('기준 조합에서는 843개 중 기상 조건을 두 겨울 모두 충족한 곳이 60개, 교량·선형 조건까지 충족한 곳이 3개였다. 이 세 구간은 공개 목록의 경계 여유를 ±100~500m로, 가용성 문턱을 90~99%로 바꿔도 유지됐다.',small)
 p('75개 조합의 선택 개수는 0~86개이고, 모두에서 유지되는 구간은 없다. 기상 상위 10%를 두 겨울 모두 요구하면 0개다. S01의 두 구간은 60개 조합(80%), S02의 한 구간은 48개 조합(64%)에서 유지됐다. 유지율은 결빙확률이나 통계적 신뢰도가 아니며, 선정되지 않은 구간의 안전을 입증하지 않는다.',small)
 h('문턱을 산정하는 정보 단위')
 table([['겨울','관측소 후보 조합','서로 다른 실제 14입력 시계열'],['2024/25',68,22],['2025/26',68,24]],[107,170,230])
 p('관측소 후보의 예비 순서가 달라도 실제로 입력된 값은 같을 수 있다. 모든 10분 시각과 14열 배열을 대조해 같은 자료를 한 번 집계했다. 조건 비율은 판정 가능한 시점 중 저온·수분 조건을 충족한 비율이며, 상대 문턱은 서로 다른 입력 시계열에서 산정한다. 재현용 원 입력과 식별자 대조표를 함께 제공한다.',small)

 page('지형에서 확인할 낮의 일사 환경')
 p('같은 기상을 공유하는 도로에도 주변 지형은 다르다. 공개 GLO-30 DSM의 네 타일에서 기존 지도와 같은 843중점을 조회하고, 16방향·3km 지평선과 10분 태양위치 근사식을 대조했다[9,10]. 제공된 정규화 DEM을 미터로 해석하지 않고 별도 공개 원본의 미터 표고를 사용했다.')
 picture('terrain_solar_context',330,'2024/25 겨울의 지형 차폐 가능 낮 시간 비율과 S01·S02의 대표 중점. 오른쪽은 같은 고도각 축의 DSM 지평선과 동지 태양 경로다.')
 examples=pd.read_csv(F/'terrain_examples.csv').set_index('area')
 a=examples.loc['S01'];b=examples.loc['S02']
 p(f'S01 대표 중점의 지형 차폐 가능 낮 비율은 {100*a.shade_fraction_2024:.1f}%, S02는 {100*b.shade_fraction_2024:.1f}%였다. 탐색을 1km로 줄이면 각각 {100*a.shade_fraction_1km_2024:.1f}%·{100*b.shade_fraction_1km_2024:.1f}%다. 같은 결빙 조건 입력을 공유해도 주변 지형 맥락은 다르다. 각 범위에서 추정 이정이 가장 앞선 중점을 예시로 사용했으며 전체 843개 중점의 원표를 제공한다.')
 h('지형 지표를 위험 배점으로 곧바로 더하지 않은 이유')
 p('차폐는 낮의 직달 일사와 관련되고 하늘 개방도는 야간 복사 교환에도 관련된다[2]. 구름·제설·수분과 함께 작용하므로 한 방향의 위험 가중치로 합산할 근거가 부족하다. 이 지형 정보는 현장에서 그늘·수분·시설을 확인할 맥락으로 제시하고, 추정 모형이나 기준 조합의 선정에는 새 가중치를 넣지 않았다.')
 p('DSM은 수목·건물·시설물을 포함하며 취득 시기 이후의 공사를 반영하지 못할 수 있다. 교량 상판 높이·도로 경사·터널 내부를 측량한 값이 아니고, 계산된 낮 시간 비율은 실제 일조·일사량 관측도 아니다.',small)
 p('produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.',small)

 page('활용 범위와 결론')
 h('관측 공백을 확인하는 기초 자료')
 p('학습에서 제외한 3지점의 노면온도 MAE 평균은 0.978°C였고, 도로 기상 공간 제외 평가에서 풍속 MAE는 0.500m/s였다. 이 결과는 기상 관측이 부족한 구간을 살피고 추가 센서의 설치 범위를 검토하는 데 사용할 수 있다. 기상 분포와 현장 관리 정보를 함께 제시하는 방식은 도로기상 의사결정 지원의 취지와도 맞는다[6].')
 h('결빙 경보로 확장하기 위한 조건')
 p('결빙 정밀도는 0.0195로 낮았고 실제 양성 지점은 1곳뿐이었다. 세 지점 전체·추가 겨울·서로 다른 관리 조건에서 결빙 성능을 더 확인해야 한다. 현재 결과로 자동 경보나 제설 시점을 결정하는 것은 근거가 부족하다. 노면수분·염분·제설·마찰 자료를 확보하고 오경보와 미탐의 비용을 정해 판정 기준을 검증할 필요가 있다.')
 p('공간 결과의 저온·수분 문턱과 도로환경 기준은 분석용 비교 기준이다. 기준 조합 3구간의 선택 유지율은 64~80%였고, 이를 확정된 신규 위험구간으로 제안하지 않는다. 두 겨울은 10년 기후 통계를 대체하지 않으며, 학습 범위 밖 기상 입력과 학습에 없던 ASOS 출처 50구간은 별도 확인 대상이다. 모형 구성과 두 고정 판정법을 대조한 평가이며, 실제 서비스 지연을 포함한 실시간 예보 검증은 수행하지 않았다.')
 h('참고문헌과 원천 자료')
 refs=[
 ('[1] AIDA. 전북 고속도로 과제 및 과제 Q&A 693·716.','https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004604/detail.do'),
 ('[2] RoadSurf 1.1: open-source road weather model library. GMD (2024).','https://doi.org/10.5194/gmd-17-4837-2024'),
 ('[3] Roberts et al. Cross-validation strategies for structured data. Ecography 40, 913-929 (2017).','https://doi.org/10.1111/ecog.02881'),
 ('[4] Liston & Elder. A meteorological distribution system for high-resolution terrestrial modeling (MicroMet). J. Hydrometeorology (2006).','https://research.fs.usda.gov/treesearch/26813'),
 ('[5] Oregon Department of Transportation. Be Ready for Ice.','https://www.oregon.gov/odot/Pages/Winter-Be-Ready-Ice.aspx'),
 ('[6] FHWA. Leveraging Road Weather Data for Performance Management Dashboards and Reports. FHWA-HOP-20-051.','https://ops.fhwa.dot.gov/publications/fhwahop20051/index.htm'),
 ('[7] 한국도로공사. 결빙 취약구간 현황. 공공데이터포털.','https://www.data.go.kr/data/15102132/fileData.do'),
 ('[8] 한국도로공사. 암거 현황. 공공데이터포털.','https://www.data.go.kr/data/15159523/fileData.do'),
 ('[9] Copernicus DEM GLO-30. 자료 설명·DSM와 이용조건.','https://doi.org/10.5270/ESA-c5d3d65'),
 ('[10] NOAA GML. Solar Calculation Details. 태양위치 근사식의 범위.','https://gml.noaa.gov/grad/solcalc/calcdetails.html'),
 ('[11] 기상청 API허브. 추가 도로기상 관측·지점 정보의 원천.','https://apihub.kma.go.kr/apiInfo.do'),
 ('[12] Nlenanya et al. Standardized Framework for Winter Weather Road Condition Indices. Aurora (2026).','https://www.intrans.iastate.edu/wp-content/uploads/2026/03/standardized_framework_road_condition_indices_w_cvr.pdf')]
 for label,url in refs:
  story.append(Paragraph(f'<link href="{html.escape(url)}" color="#29546D">{html.escape(label)}</link>',small));md.append(f'[{label}]({url})')
 def footer(c,doc):
  c.setStrokeColor(colors.HexColor('#CCD5DA'));c.setLineWidth(.4);c.line(44,37,551,37)
  c.setFont('Body',8);c.setFillColor(colors.HexColor('#64717A'));c.drawString(44,23,'로드투인사이트 / 전북 고속도로 겨울철 분석');c.drawRightString(551,23,str(doc.page))
 SimpleDocTemplate(str(pdf),pagesize=(595.28,841.89),leftMargin=44,rightMargin=44,topMargin=42,bottomMargin=49,title='전북 고속도로의 겨울철 노면온도 추정과 결빙 취약구간 검토',author='로드투인사이트').build(story,onFirstPage=footer,onLaterPages=footer)
 doc=fitz.open(pdf);assert len(doc)==14,f'Unexpected page count {len(doc)}'
 render=W/'report_pages';render.mkdir(exist_ok=True)
 for i,page in enumerate(doc):page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(render/f'{i+1:02d}.png')
 (O/'analysis_report.md').write_text(('\n\n'.join(md)+'\n').replace('~','–'),encoding='utf8')
 write(W/'report_build.json',dict(status='built_pending_visual_review',pages=len(doc),pdf_sha256=sha(pdf),sources={p.relative_to(B).as_posix():sha(p) for p in [B/'technical/evaluation_metrics.json',B/'results/sections/section_review.csv',B/'results/sections/inspection_areas.csv',B/'results/evaluation/weather_metrics.csv',B/'results/evaluation/development_predictions.parquet',B/'results/evaluation/development_false_alarm_states.csv',B/'technical/development_error_analysis.json',B/'technical/weather_information_group_audit.json',B/'results/evaluation/temperature_benchmarks/metrics.csv',B/'results/sections/sensitivity/scenario_summary.csv',B/'results/conditions/association_ranges.csv',B/'results/sections/terrain/segment_solar_context.csv',B/'data/weather_information_groups.csv']},human_version_history=False))
 print('REPORT BUILT',len(doc),'pages',flush=True)
if __name__=='__main__':main()
