"""결과와 해석을 중심으로 도로기상 분석 보고서를 조판한다."""
from pathlib import Path
import sys,html
import fitz,pandas as pd
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Image,Table,TableStyle,PageBreak,KeepTogether
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,sha
P=ROOT/'outputs/private';B=P/'competition_submission/icy_road_model';W=P/'editorial_review_20261106';O=B/'report';F=O/'figures'

def main():
 pdf=O/'analysis_report.pdf';assert not pdf.exists()
 pdfmetrics.registerFont(TTFont('Body','C:/Windows/Fonts/malgun.ttf'));pdfmetrics.registerFont(TTFont('Bold','C:/Windows/Fonts/malgunbd.ttf'))
 ink=colors.HexColor('#26343D');blue=colors.HexColor('#29546D')
 body=ParagraphStyle('BodyText',fontName='Body',fontSize=10,leading=16.2,textColor=ink,spaceAfter=10,wordWrap='CJK')
 title=ParagraphStyle('Title',parent=body,fontName='Bold',fontSize=21,leading=29,spaceAfter=17)
 cover=ParagraphStyle('Cover',parent=title,fontSize=27,leading=36,spaceAfter=15)
 small=ParagraphStyle('Small',parent=body,fontSize=8.7,leading=13.3,spaceAfter=8)
 heading=ParagraphStyle('Heading',parent=body,fontName='Bold',fontSize=12,leading=19,spaceBefore=8,spaceAfter=8)
 lead=ParagraphStyle('Lead',parent=body,fontSize=11,leading=18.5)
 stat=ParagraphStyle('Stat',parent=body,fontName='Bold',fontSize=23,leading=28,textColor=blue,spaceAfter=5)
 story=[];md=[]
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
  md.extend(['| '+' | '.join(map(str,rows[0]))+' |','| '+' | '.join(['---']*len(rows[0]))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows[1:]])
 def picture(name,height=260,caption=''):
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
  Paragraph('0.50m/s',stat),Paragraph('지역을 통째로 제외한<br/>풍속 추정 MAE',body),Spacer(1,16),
  Paragraph('22구간',stat),Paragraph('두 겨울 기상조건과 도로환경,<br/>공개 목록을 대조한 계측 검토 대상',body)]
 layout=Table([[Image(str(F/'study_area.png'),width=w,height=ht),findings]],colWidths=[315,192],hAlign='LEFT')
 layout.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]));story.extend([layout,Spacer(1,10)])
 p('분석 대상은 500m 도로 843구간이다. AWS·ASOS의 과거 관측으로 기상과 노면온도를 추정하고, 저온·수분 조건의 빈도에 교량·선형 정보를 연결했다. 노면온도는 103,659개 관측쌍에서 지점 평균 MAE 0.978°C를 보였다. 결빙 판정 F1은 0.033으로 낮아 경보의 단독 근거로 삼기 어렵다. 결과의 활용 범위는 관측 공백 파악과 현장 확인 대상 선정에 두었다.')
 p('2026 DATA·AI 분석 경진대회  문제해결 부문  |  전북 고속도로 기상·결빙 과제',small)
 md.extend(['# 전북 고속도로의 겨울철 노면온도 추정과 결빙 취약구간 검토','요약: 노면온도 MAE 0.978°C, 공간 제외 풍속 MAE 0.500m/s, 추가 계측 검토 22구간. 결빙 F1 0.033의 한계를 포함한다.'])
 page('자료와 분석 방법')
 table([['자료','범위와 역할'],['도로기상 관측','RWIS의 노면온도·노면상태와 도로 기상 관측. 회귀·분류 평가의 기준값'],['일반 기상 관측','AWS·ASOS의 기온, 습도, 풍속, 강수, 적설, 이슬점 등. 과거 이력과 태양위치 파생 특성'],['도로·시설 정보','전북 경계 안 3노선의 중심선과 교량·터널 코드. 500m 보고 단위 843개'],['공개 취약구간 목록','과제의 취약구간 표와 한국도로공사 공개 목록(2026.09.07). 기준일과 방향 정보를 구분'],['평가 기간','2024.11.01-2025.02.28 및 2025.11.01-2026.02.28. 각 120일, 10분 KST']],[116,391])
 h('노면온도와 도로 기상')
 p('노면온도는 기상·과거 이력·태양위치 63특성을 입력한 HistGradientBoosting 회귀로 추정했다. 기온·습도·풍속은 기상 관측값과 도로 관측값의 잔차를 학습했다. 풍속에는 반경 50km의 가까운 AWS 최대 4곳에서 얻은 거리 가중 통계 35개를 더해 69특성을 사용했다.')
 p('입력 관측은 추정 시각보다 앞선 자료만 사용했다. ASOS의 허용 시간차는 최대 60분이다. 도로 기상 모형의 AWS는 최대 15분, 노면온도·결빙 입력의 AWS는 최대 60분으로 제한했다. 타 지점의 같은 시각 노면상태는 입력에서 제외했다. 제공 DEM은 정규화 값이므로 미터 고도나 경사도로 사용하지 않았다.')
 h('결빙 조건과 평가 설계')
 p('결빙 판정의 기준온도 Tref는 기본 기상 12특성으로 절대오차·제곱오차를 각각 학습한 두 회귀 모형의 평균이다. 제출 노면온도인 63특성 모형의 출력과 역할을 구분한다. Tref가 0°C 이하이고, AWS 이슬점이 Tref 이상이거나 최근 3시간의 AWS 15분 강수 최댓값 또는 ASOS 적설이 양수일 때 결빙으로 판정했다. 수분 관련 입력이 모두 없으면 판정을 보류했다.')
 p('노면온도 개발 평가는 9지점, 기상 평가는 4지역을 사용했다. 인접 자료의 유사성이 평가를 낙관적으로 만들지 않도록 지역 전체를 제외하고, 기상은 겨울도 함께 제외한 결과를 추가 산출했다[3]. 제출 평가 3지점은 학습에서 제외했다. 두 결빙 판정법의 출력을 고정한 뒤 관측과 대조했으며, 보고된 결과는 이 고정 대조의 성적이다.')
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
 page('도로 기상 추정')
 p('관측 공백 도로의 기상을 추정한 뒤, AWS 우선 기준선과 같은 지역 제외 분할에서 비교했다. 기온·습도·풍속의 MAE는 각각 1.324°C, 5.687%p, 0.500m/s다. 지역과 겨울을 동시에 제외했을 때 풍속 MAE는 0.508m/s였다.')
 weather=pd.read_csv(B/'results/evaluation/weather_metrics.csv');rows=[['대상','유효쌍','AWS 기준선 MAE','추정 MAE','감소율']]
 for target,label,unit in [('air_temperature','기온','°C'),('relative_humidity','습도','%p'),('wind_speed','풍속','m/s')]:
  q=weather.loc[weather.target.eq(target)&weather.validation.eq('spatial')].set_index('method');a=q.loc['aws_reference','mae'];b=q.loc['estimated','mae']
  rows.append([label,f"{int(q.loc['estimated','n']):,}",f'{a:.3f} {unit}',f'{b:.3f} {unit}',f'{(1-b/a)*100:.1f}%'])
 table(rows,[62,85,130,130,100])
 picture('wind_distribution',320,'그림 2. 같은 색 범위로 비교한 두 겨울 평균 풍속. 지도는 구간 추정값이며, 각 구간의 실측 검증 성적을 나타내지 않는다.')
 p('노면 에너지 교환에는 기온·수분·바람·복사 조건이 함께 작용한다[2]. 여기서는 열수지를 직접 적분하는 대신 관측 기반 회귀로 자료 공백을 보완했다. 기상 공간 분포를 다루는 MicroMet의 관점[4]을 참고하되, 지형 보정 물리모형을 구현한 것으로 해석하지 않는다.')
 page('결빙 판정의 성능과 오경보')
 p('노면상태 Ice만 양성으로 두고 나머지 유효 상태와 구분했다. 실제 Ice는 부곡교의 64시점·19일에 관측됐다. 해전·삼봉은 실제 결빙이 없어 분류 평균에서 제외했다. 무양성 지점 제외와 날짜별 지표의 처리에는 과제 질의응답의 집계 규칙을 적용했다[1].')
 table([['판정법','Precision','Recall','F1'],['기준온도 + 수분 대용조건','0.0195','0.5936','0.0326'],['ASOS 기온 0°C 기준선','0.0048','0.7353','0.0087']],[210,99,99,99])
 picture('icing_calendar',136,'그림 3. 부곡교에서 하루 중 Ice가 한 번 이상 관측되거나 판정된 날짜. 짙은 칸이 해당 날짜이며 회색 칸에는 양성이 없다.')
 p('두 겨울의 관측 결빙일은 각각 14일·5일이고 판정일은 26일·18일이다. 관측 양성일을 놓친 날은 2일·1일, 관측 양성 없이 판정만 발생한 날은 각각 14일이다. 기온 기준선보다 오경보를 줄였지만 정밀도는 약 2%에 머물렀다.')
 h('지표를 읽는 기준')
 p('Precision·Recall·F1은 날짜별로 계산한 뒤 지점별 기간 평균과 지점 평균을 구했다. 기준온도·수분 판정법에 포함된 날짜 수는 각각 44일·19일·47일이다. 오경보만 있는 날의 Recall과 미탐만 있는 날의 Precision은 평균에서 제외하고, 미탐의 Recall·F1은 0으로 포함했다. 하루 144유효쌍만 인정한 계산에서도 F1은 같았다.')
 p('현재 입력의 강수·이슬점·적설은 실제 노면수분의 대용값이다. 낮은 정밀도는 이 구성만으로 Ice를 확정하기 어렵다는 결과다. 노면수분·염분·제설 시각을 함께 관측해 오경보 원인을 검증하는 것이 우선이다. 온도 추정의 개선을 결빙 탐지의 개선으로 대신 평가하지 않았다.')
 page('겨울별 조건 노출과 도로환경')
 p('구간별 노출 비율은 유효한 10분 판정 중 저온·수분 조건을 만족한 비율이다. 두 겨울의 결과를 같은 척도로 비교하고, 노선별 평균은 구간 길이로 가중했다. 노면의 실제 결빙 빈도나 사고확률을 산출한 값은 아니다.')
 picture('condition_exposure',270,'그림 4. 저온·수분 조건 비율. 두 겨울의 기상 차이를 같은 색 범위로 표시했다.')
 picture('route_exposure',148,'그림 5. 노선별 길이 가중 조건 비율. 통영-대전은 17.1%에서 3.2%로, 서해안은 11.2%에서 4.5%로 달라졌다.')
 p('노선의 상대적인 순서도 겨울에 따라 바뀐다. 도로에 고정된 한 등급을 부여하기보다 대상 겨울과 관측 기간을 함께 확인해야 한다. 같은 기상 입력을 공유하는 500m 구간이 있으므로 843개를 독립적인 기상 관측으로 세지 않았다.')
 p('도로환경 점검에는 교량 코드와 25m 간격으로 재표본화한 중심선의 100m당 방향 변화를 사용했다. 교량의 냉각 특성은 도로 관리기관의 안내[5]를 참고했다. 방향 변화는 설계 곡률·회전반경과 다르며 터널 내부·입출구에 동일한 위험 가중치를 주지 않았다.')
 page('추가 계측·시설 확인 범위')
 p('기상 노출과 도로환경을 같은 500m 구간에 연결하고, 다음 조건을 모두 충족하는 범위를 추렸다. ① 두 겨울 모두 고유 기상 그룹 기준 75백분위 이상의 노출, ② 교량 코드 또는 선형 변화 상위 구간, ③ 판정 가용률 95% 이상, ④ 공개 취약구간 목록의 ±250m 범위 밖이며 이정 추정이 가능한 구간이다.')
 picture('inspection_locations',265,'그림 6. 추정 이정 위의 취약구간 목록과 추가 확인 범위. 방향이 없는 문제 표는 비교를 위해 양방향에 표시했다. 공개 목록은 2026.09.07 기준이다[7].')
 p('선정 결과는 서해안·호남의 22구간, 방향별 11개 연속 범위다. 길이는 양방향 합계 11.0km이며, 이 구간들이 공유하는 기상 입력은 겨울별 5개 조합이다. 선정 개수를 독립적인 위험 발견 건수로 해석하지 않는다.')
 table([['예시','방향과 추정 이정','조건 비율<br/>2024/25 → 2025/26'],['F06 서해안','서천·군산 → 고창·영광<br/>79.8-80.8km','13.0% → 6.8%'],['F08 호남','논산JC → 호남터널남측<br/>120.6-123.6km','12.0% → 4.8%']],[95,265,147])
 p('이정은 공식 암거 좌표·이정으로 중심선 사이를 보간한 값이다[8]. ±250m는 목록과의 관계를 살피기 위한 민감도 조건이며 측량 오차의 신뢰구간은 아니다. 지도에서 시설의 실제 범위와 그늘·배수·노면수분을 확인한 뒤 계측 위치를 정하는 자료로 사용한다. 전체 11개 범위와 구간 키는 CSV·GIS에 제공한다.')
 page('활용 범위와 결론')
 h('관측 공백을 확인하는 기초 자료')
 p('학습에서 제외한 3지점의 노면온도 MAE 평균은 0.978°C였고, 도로 기상 공간 제외 평가에서 풍속 MAE는 0.500m/s였다. 이 결과는 기상 관측이 부족한 구간을 살피고 추가 센서의 설치 범위를 검토하는 데 사용할 수 있다. 기상 분포와 현장 관리 정보를 함께 제시하는 방식은 도로기상 의사결정 지원의 취지와도 맞는다[6].')
 h('결빙 경보로 확장하기 위한 조건')
 p('결빙 정밀도는 0.0195로 낮았고 실제 양성 지점은 1곳뿐이었다. 세 지점 전체·추가 겨울·서로 다른 관리 조건에서 결빙 성능을 더 확인해야 한다. 현재 결과로 자동 경보나 제설 시점을 결정하는 것은 근거가 부족하다. 노면수분·염분·제설·마찰 자료를 확보하고 오경보와 미탐의 비용을 정해 판정 기준을 검증할 필요가 있다.')
 p('공간 결과의 저온·수분 문턱과 도로환경 기준은 분석용 비교 기준이다. 두 겨울은 10년 기후 통계를 대체하지 않으며, 학습 범위 밖 기상 입력과 학습에 없던 ASOS 출처 50구간은 별도 확인 대상이다. 모형 구성과 두 고정 판정법을 대조한 평가이며, 실제 서비스 지연을 포함한 실시간 예보 검증은 수행하지 않았다.')
 h('참고문헌과 원천 자료')
 refs=[
 ('[1] AIDA. 전북 고속도로 과제 및 과제 Q&A 693·716.','https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004604/detail.do'),
 ('[2] RoadSurf 1.1: open-source road weather model library. GMD (2024).','https://doi.org/10.5194/gmd-17-4837-2024'),
 ('[3] Roberts et al. Cross-validation strategies for structured data. Ecography 40, 913-929 (2017).','https://doi.org/10.1111/ecog.02881'),
 ('[4] Liston & Elder. A meteorological distribution system for high-resolution terrestrial modeling (MicroMet). J. Hydrometeorology (2006).','https://research.fs.usda.gov/treesearch/26813'),
 ('[5] Oregon Department of Transportation. Be Ready for Ice.','https://www.oregon.gov/odot/Pages/Winter-Be-Ready-Ice.aspx'),
 ('[6] FHWA. Leveraging Road Weather Data for Performance Management Dashboards and Reports. FHWA-HOP-20-051.','https://ops.fhwa.dot.gov/publications/fhwahop20051/index.htm'),
 ('[7] 한국도로공사. 결빙 취약구간 현황. 공공데이터포털.','https://www.data.go.kr/data/15102132/fileData.do'),
 ('[8] 한국도로공사. 암거 현황. 공공데이터포털.','https://www.data.go.kr/data/15159523/fileData.do')]
 for label,url in refs:
  story.append(Paragraph(f'<link href="{html.escape(url)}" color="#29546D">{html.escape(label)}</link>',small));md.append(f'[{label}]({url})')
 def footer(c,doc):
  c.setStrokeColor(colors.HexColor('#CCD5DA'));c.setLineWidth(.4);c.line(44,37,551,37)
  c.setFont('Body',8);c.setFillColor(colors.HexColor('#64717A'));c.drawString(44,23,'전북 고속도로 겨울철 분석');c.drawRightString(551,23,str(doc.page))
 SimpleDocTemplate(str(pdf),pagesize=(595.28,841.89),leftMargin=44,rightMargin=44,topMargin=42,bottomMargin=49,title='전북 고속도로의 겨울철 노면온도 추정과 결빙 취약구간 검토',author='icy-road-ai').build(story,onFirstPage=footer,onLaterPages=footer)
 doc=fitz.open(pdf);assert len(doc)==8,f'Unexpected page count {len(doc)}'
 render=W/'report_pages';render.mkdir(exist_ok=True)
 for i,page in enumerate(doc):page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(render/f'{i+1:02d}.png')
 (O/'analysis_report.md').write_text('\n\n'.join(md)+'\n',encoding='utf8')
 write(W/'report_build.json',dict(status='built_pending_visual_review',pages=len(doc),pdf_sha256=sha(pdf),sources={p.relative_to(B).as_posix():sha(p) for p in [B/'technical/evaluation_metrics.json',B/'results/sections/section_review.csv',B/'results/sections/inspection_areas.csv',B/'results/evaluation/weather_metrics.csv']},human_version_history=False))
 print('REPORT BUILT',len(doc),'pages',flush=True)
if __name__=='__main__':main()
