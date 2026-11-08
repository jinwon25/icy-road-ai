"""현재 결과·최신 규정·최종 관측 대조를 한 번에 읽는 새 12쪽 보고서."""
from pathlib import Path
import sys,html,json
import fitz,numpy as np,pandas as pd
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Image,Table,TableStyle,PageBreak
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,sha
P=ROOT/'outputs/private';OUT=P/'final_report_20261106_v14';ASSETS=P/'final_release_assets_20261106_v14'

def main():
 assert not OUT.exists();wind=read(P/'wind_direction_terrain_20261106_v1/summary.json');assert wind['status']=='controlled_wind_direction_terrain_complete'
 OUT.mkdir();pdfmetrics.registerFont(TTFont('Malgun','C:/Windows/Fonts/malgun.ttf'));pdfmetrics.registerFont(TTFont('MalgunBold','C:/Windows/Fonts/malgunbd.ttf'))
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib.font_manager import FontProperties
 plt.rcParams['font.family']=FontProperties(fname='C:/Windows/Fonts/malgun.ttf').get_name();plt.rcParams['axes.unicode_minus']=False
 f=pd.read_csv(ASSETS/'exports/final_observed_predictions_10min.csv',dtype={'station_id':str},float_precision='round_trip');m=read(ASSETS/'metrics_summary.json')
 fig,axs=plt.subplots(1,3,figsize=(10.5,3.2),constrained_layout=True)
 for ax,(sid,q) in zip(axs,f.groupby('station_id')):
  q=q.dropna(subset=['observed_road_temperature_c','estimated_road_temperature_c']);a=q.observed_road_temperature_c;b=q.estimated_road_temperature_c
  ax.hexbin(a,b,gridsize=45,mincnt=1,bins='log',cmap='Blues');lo=min(a.min(),b.min());hi=max(a.max(),b.max());ax.plot([lo,hi],[lo,hi],color='#c25138',lw=1)
  ax.set_title(f'{sid} · n={len(q):,}');ax.set_xlabel('관측 노면온도 (°C)');ax.set_ylabel('추정 노면온도 (°C)');ax.grid(alpha=.15)
 fig.savefig(OUT/'temperature_observed_predicted.png',dpi=190);plt.close(fig)
 body=ParagraphStyle('body',fontName='Malgun',fontSize=9.2,leading=15.3,spaceAfter=10,textColor=colors.HexColor('#253d48'),wordWrap='CJK')
 title=ParagraphStyle('title',parent=body,fontName='MalgunBold',fontSize=21,leading=29,spaceAfter=18)
 heading=ParagraphStyle('heading',parent=body,fontName='MalgunBold',fontSize=12,leading=19,spaceBefore=8,spaceAfter=10)
 small=ParagraphStyle('small',parent=body,fontSize=7.6,leading=12,spaceAfter=7)
 story=[];md=[]
 def p(s):story.append(Paragraph(s,body));md.append(s.replace('<b>','').replace('</b>',''))
 def h(s):story.append(Paragraph(s,heading));md.append('### '+s)
 def page(s):
  if story:story.append(PageBreak())
  story.append(Paragraph(s,title));md.extend(['','## '+s,''])
 def table(rows,widths=None):
  if widths is None:widths=[495/len(rows[0])]*len(rows[0])
  t=Table([[Paragraph(html.escape(str(v)),small) for v in r] for r in rows],colWidths=widths,hAlign='LEFT')
  t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8f1f3')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#cad8dd')),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]));story.append(t);story.append(Spacer(1,9))
  md.extend(['| '+' | '.join(map(str,rows[0]))+' |','| '+' | '.join(['---']*len(rows[0]))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows[1:]]+[''])
 def image(path,maxheight=370):
  path=Path(path);im=PILImage.open(path);w=495;ht=w*im.height/im.width
  if ht>maxheight:w*=maxheight/ht;ht=maxheight
  story.append(Image(str(path),width=w,height=ht));story.append(Spacer(1,10));md.append('그림: '+path.name)
 page('관측 공백 도로의 기상·노면온도\n그리고 결빙 조건')
 p('2026 DATA·AI 분석 경진대회 | 전북 고속도로 과제<br/>최종 분석 보고서 v14 · 2026년 11월 6일')
 h('관측 공백을 채우되, 조건 노출과 실제 결빙을 구별했습니다')
 p('서해안·통영–대전중부·호남 고속도로의 두 겨울 기상과 노면온도를 추정하고 500m 구간의 기상 노출·도로환경을 함께 제시합니다. 기상 관측망의 추가 공간 정보는 풍속 오차를 줄였으며, 최신 Q&A의 관측 대조·집계 규칙과 제공 DEM 해석을 반영했습니다.')
 table([['핵심 결과','수치·산출물','평가 범위'],['노면온도','MAE 지점 평균 0.977562°C','제외 3지점 고정 예측, 103,659 유효쌍'],['결빙 기존 v2','F1 0.032627 / P 0.019495 / R 0.593588','실제 Ice가 있는 1지점. 공식 서버 점수 아님'],['풍속 69특성','공간 제외 MAE 0.499955m/s','지역·겨울 동시 제외 0.508379m/s'],['공간 전달','843구간·240일·202,320 일별 행','CSV·GIS·오프라인 지도·실행 데모']],[90,195,210])
 p('추가 결빙 학습은 채택 조건을 충족하지 못해 기존 v2를 유지했습니다. 낮은 정밀도와 개발·최종 자료의 프로필 순위 역전을 공개합니다. 저온·수분 조건 비율과 도로환경 검토는 실제 Ice 발생확률·사고확률·공식 위험등급으로 검증되지 않았습니다.')
 p('현재 문서는 과거 버전의 부록을 이어 붙이지 않고 최종 구성을 다시 정리한 보고서입니다. 과거 보고서와 코드·모형·자료는 모델자료에 보존합니다. 참가자가 완성물을 직접 확인한 것으로 기재하지 않습니다.')
 page('01 · 최신 공식 규정과 평가')
 p('공개 응답 80개와 상세 공지·일반 Q&A·과제 Q&A 62건을 재확인했습니다. 문제해결 부문 심사는 창의성 20·우수성 50·효과성 30입니다. 별도 과제 항목별 수치 배점이 공지된 것처럼 합산하지 않습니다.')
 table([['규정','최종 적용'],['마감','2026년 11월 6일 23:59 KST. 참가 승인 완료는 사용자 확인'],['Q&A693','필수 관측·예측 열, 정확한 10분 시각, 실제 Ice 없는 지점 제외'],['입력 제한','다른 도로의 동시 노면상태 금지. 현재 최종 모형 입력에 없음'],['제공 DEM','정규화 값으로 미터가 아님. 물리 고도·경사로 사용하지 않음'],['Q&A716','근거를 적은 새 기준 가능. 두 겨울을 최근 10년 기후값으로 대체하지 않음'],['564·659','학습·추론 Notebook·모형·환경·README·실행 결과와 설명 데모'],['AI618·서약','AI 지원 기록, 로컬 예측, 승인된 대회 목적 사용·자료 보안']],[100,395])
 p('분류 집계는 날짜별 P/R/F1 → 지점별 평균 → 실제 결빙이 있는 지점 평균입니다. 오경보만 있는 날의 Recall과 미탐만 있는 날의 Precision은 정의되지 않아 제외하고, 미탐의 Recall/F1은 0으로 포함합니다. 부분 날짜의 최소 유효량은 공식 미확정이므로 1·144시점 두 결과를 보고합니다.')
 p('원문 URL·서약 확인·배점 대응은 docs/competition/OFFICIAL_RULES_AND_RUBRIC_20261106.md에 있습니다. 원자료·인증정보는 공개하지 않고 코드 제출 의무를 대회 중 공개 허용으로 해석하지 않습니다.')
 page('02 · 자료 흐름과 평가 분리')
 table([['단계','입력과 처리','통제'],['제공 자료','10월 7일 수정 배포 RWIS·AWS·ASOS·도로 중심선','원 배포본·파일 해시 보존'],['기상 전처리','지점·시각 정규화, 엄격한 과거 ASOS/AWS 유효 관측','동시·미래 원천 차단, 결측·가용성 유지'],['노면온도','기상·과거 이력·태양 특성 63개 HGB','도로 상태·정규화 DEM·주변 노면 정답 제외'],['기상 보완','기온·습도 및 69특성 풍속','도로 실측 기상만 목표로 사용'],['개발 평가','4개 지역을 통째로 제외. 겨울 동시 제외도 비교','보호 3곳과 기개봉 외부 4곳은 연구에서 제외'],['최종 대조','모형·두 프로필·예측 파일 봉인 후 관측 결합','정답을 읽은 뒤 새 가중치·임계값 학습 없음']],[75,215,205])
 p('노면온도 개발은 9지점·310,091 유효쌍입니다. 풍속 최종 학습은 허용 13지점·447,628 유효행입니다. 같은 지점의 날짜를 임의 분할하는 방법에 의존하지 않고, 지역을 제외한 결과와 지역·겨울을 동시에 제외한 결과를 구별합니다.')
 p('제외 지점은 부곡교 12410·해전 23402·삼봉 33411입니다. 최종 관측은 필수 제출 대조표와 고정 평가를 위해 봉인 이후에 읽었습니다. 현재는 ‘보호 정답을 한 번도 읽지 않았다’고 표현하지 않습니다. 최종 대조를 확인한 뒤 기존 v2 유지 방침을 문서화했으며 두 고정 프로필의 결과를 모두 제공합니다.')
 h('결측의 의미를 보존')
 p('103,680개 계획 시점 중 원 관측 행이 없는 3개는 NA, 추론 입력이 부족한 18개도 NA입니다. 없는 행을 비결빙 0으로 채우거나 관측을 추론 입력에 합치지 않습니다. 최종 표는 CSV·Parquet를 함께 제공하고 키 중복·시각·수치를 대조했습니다.')
 page('03 · 최종 모델과 실제 개선')
 table([['대상','현재 구성','개발 검증 결과'],['노면온도 v3','기상·과거 이력·태양 특성 63개, MAE HGB','MAE 1.145698°C; 이전 대비 13.66% 감소'],['기온','기상 잔차 보정','AWS 우선 기준 대비 MAE 22.10% 감소'],['습도','안정화된 과거 기상 이력 모형','AWS 우선 기준 대비 MAE 12.91% 감소'],['풍속','기본 기상 34 + 주변 AWS 35 = 69특성','지역 제외 0.563455→0.499955m/s'],['풍속 시공간','같은 고정 설정, 겨울도 함께 제외','0.567465→0.508379m/s, 10.41% 감소'],['결빙 v2','저온 합의와 수분 대용조건','새 손실함수 미채택. 고정 프로필 유지']],[80,220,195])
 p('풍속 관측망은 50km 안 최대 4개 AWS를 사용하며, 현재보다 엄격히 과거이고 15분 이내인 관측을 거리 제곱 역수로 결합합니다. 이웃 유효 개수·거리·관측소 간 범위도 입력 품질로 제공합니다. 풍속 관측 높이·국지 고도감률의 물리 보정을 수행했다고 주장하지 않습니다.')
 p('모형별 개선 수치는 반복 사용한 개발 지역에서 얻은 결과입니다. 서로 다른 목표의 MAE 감소를 결빙 F1 증가로 연결하지 않습니다. 외부 AI 예측 API·인증키 없이 CPU와 포함 캐시로 최종 추론을 실행합니다.')
 h('재현 자산')
 p('노면온도 code/train.py, 현재 기본 code/predict_final.py, 별도 풍속·습도의 학습 및 추론 스크립트·고정 환경·학습 자료·학습된 모형을 포함합니다. 전체 원자료에서 모든 과거 연구를 재구성하려면 원 비공개 작업공간이 추가로 필요하며 최종 실행 재현과 구별합니다.')
 page('04 · 제외 3지점 노면온도 대조')
 image(OUT/'temperature_observed_predicted.png',245)
 table([['지점','유효쌍','BIAS (°C)','MAE (°C)','RMSE (°C)']]+[[r['station'],f"{r['n']:,}",f"{r['bias']:.6f}",f"{r['mae']:.6f}",f"{r['rmse']:.6f}"] for r in m['temperature']], [75,85,110,110,115])
 p('BIAS는 예측-관측입니다. 지점별 동일 가중 평균은 BIAS -0.549055°C·MAE 0.977562°C·RMSE 평균 1.274557°C입니다. 모든 유효쌍을 합산한 RMSE 1.282743°C와 분모가 다릅니다. 그림은 전체 유효쌍의 밀도이며 붉은 선은 일치선입니다.')
 p('부곡교·해전은 약 -0.97°C의 낮은 쪽 편향, 삼봉은 약 +0.30°C 편향이 남습니다. 이 고정 대조로 지점별 상수 보정이나 임계값을 재설정하지 않았습니다. 관측 센서 오차와 미관측 지역으로의 전이는 별도 검증이 필요합니다.')
 page('05 · 결빙 지표와 낮은 정밀도')
 table([['고정 프로필','Precision','Recall','F1','F1 날짜'],['주 제출: 기존 v2','0.019495','0.593588','0.032627','47'],['비교: ASOS 0°C','0.004759','0.735338','0.008698','133']],[145,85,85,85,95])
 p('전체 3지점 중 실제 Ice는 부곡교의 64시점에만 있습니다. 해전·삼봉은 산출불가로 표시하고 지점 평균에서 제외합니다. v2의 P/R/F1 평균에 사용한 날짜는 각각 44·19·47일이며 동일한 분모가 아닙니다. 최소 144유효쌍 날짜만 인정하는 민감도에서도 v2 F1은 같습니다.')
 table([['집계 범위','TP','FP','FN','TN'],['v2 전체 3지점 합계 진단','39','7,963','25','95,581'],['기온 기준선 전체 합계 진단','52','36,651','12','66,893']],[215,70,70,70,70])
 p('위 합계는 오경보 규모를 확인하는 진단입니다. 이를 합산해 공식 방식의 날짜·지점 F1을 대체하지 않습니다. 정밀도가 낮아 자동 경보·제설 판단에 바로 사용하기 어렵습니다. 실제 수분·염수·제설·노면 상태의 시간 이력과 추가 센서 자료가 다음 개선의 우선순위입니다.')
 h('개발 순위가 최종에 이어지지 않았습니다')
 p('최신 규칙으로 재집계한 개발 9지점(실제 Ice 8지점) F1은 v2 0.029393·기온 기준선 0.040882입니다. 최종 고정 대조에서는 v2가 높았습니다. 두 프로필을 평가 전에 봉인했고 기존 v2를 유지합니다. 이 비교를 다시 ‘보지 않은 정답에서 독립적으로 선택한 모델’로 포장하지 않습니다.')
 page('06 · 추가 고도화와 채택 판단')
 p('최신 날짜·지점 집계에 맞춘 새 결빙 손실함수를 사전 등록하고 지역·이중 지역 제외 총 10회 학습했습니다. 입력은 ASOS 기상과 고정 파생 특성이고 보호 정답이나 다른 도로의 동시 상태를 사용하지 않았습니다.')
 table([['결빙 후보','개발 F1','판단'],['기온 0°C 기준선','0.040882','기존 대조군'],['새 중첩 선택','0.039693','F1·144시점·Recall 조건 실패'],['새 후보 이벤트','272 / 386건 탐지','기준선 대비 60건 손실·2건 추가'],['7일 블록 민감도','차이 95% 범위 -0.004413~+0.002528','독립 지점 신뢰구간 아님; 미채택']],[135,150,210])
 h('풍향·지형 추가: 새 정보를 사용한 통제 비교')
 rows=[['풍속 후보','지역·겨울 제외 MAE','지역 제외 MAE','양쪽 기준 통과']]
 for c in ['direction','terrain','terrain_blend']:
  rows.append([c,f"{wind['reports']['joint'][c]['metrics']['pooled']['mae']:.6f}",f"{wind['reports']['spatial'][c]['metrics']['pooled']['mae']:.6f}",'예' if c in wind['accepted_candidates'] else '아니오'])
 table(rows,[145,125,115,110])
 p('기상청 16방위 코드를 원문 기준으로 해석해 무풍 0과 북풍 360을 구별했습니다. 방향 성분과 출처가 확인된 Copernicus DSM·16방향 지평선 대리변수를 비교했습니다. 24회 고정 학습·기존 69특성 예측 일치·두 겨울/지역/영하 근처/7일 블록 민감도를 확인했습니다. MicroMet의 지형·풍향 원리를 참고했으며 해당 물리모형의 복제나 국내 보정된 물리 계수라고 주장하지 않습니다.')
 p('추가 실험의 채택 후보: '+(', '.join(wind['accepted_candidates']) if wind['accepted_candidates'] else '없음. 현재 69특성 유지.')+' 후보의 실패와 이전 147특성 이력 후보의 악화를 함께 보존합니다. 이미 확인한 정답에 맞춘 추가 후보 탐색은 하지 않습니다.')
 page('07 · 풍속의 실제 구간 적용')
 image(ROOT/'docs/images/wind_network_projection_20261102.png',405)
 p('채택된 69특성 풍속을 500m 843구간·두 겨울 29,134,080개 10분 시점에 적용했습니다. 일별 202,320행, 겨울별 1,686행의 CSV·Parquet·GeoPackage와 오프라인 탐색을 연결했습니다. 풍속 평균은 길이 가중 1.237852·1.288793m/s입니다.')
 p('풍속 입력 범위 이탈은 두 겨울 26.40%·30.39%이며 ASOS 172 출처 50구간은 학습에 없던 조합입니다. 범위 이탈을 오차·확률로 해석하지 않습니다. 수치 집계·GIS와 대표 구간 재추론을 검산했고, 126필터·1,632,048개 화면 값·다운로드·모바일·외부 요청 0을 확인했습니다.')
 page('08 · 새 기상 노출·도로환경 기준')
 image(P/'risk_review_20261106_v14/risk_review_maps.jpg',300)
 p('조건 노출지수는 100 × v2 저온·수분 조건 시점 / 유효 시점입니다. 겨울별 고유 기상 그룹의 75백분위 이상을 상대적으로 높은 노출로 분류해, 같은 기상을 공유하는 많은 구간이 문턱을 중복 가중하지 않게 했습니다.')
 table([['항목','산정·활용','한계'],['교량','중심선 교량 코드가 일부라도 존재','현장 범위·재질·효과 크기 미검증'],['선형 변화','25m 재표본화 방향 변화의 100m당 합','설계 곡률·회전반경·경사 아님'],['가용성','유효 비율 0.95 미만은 입력 보완','자료 부족을 낮은 위험으로 표시하지 않음'],['터널·기후','맥락 표시 / 10년 기후값 미산정','터널 위험 가중치·가짜 기후값 없음']],[70,210,215])
 p('Q&A716이 허용한 근거 명시형 새 기준입니다. NWS·Oregon DOT·FHWA의 교량·그늘·결빙 원리를 참고했지만 국내 구간의 정량 인과효과로 전용하지 않았습니다. 1,686행과 2개 겨울 Shapefile·GeoPackage를 읽어 되검증했습니다.')
 page('09 · 기존 취약구간과 비교')
 image(ROOT/'docs/images/inventory_comparison_20261031_v3.png',270)
 p('문제 표의 기존 목록과 최신 전국 목록을 구분했습니다. 공식 암거 좌표·이정을 사용해 전북 500m 843구간 중 821개를 외삽 없이 보간하고 나머지 22개는 미확정으로 남겼습니다. 보간 위치는 측량된 공식 구간 도형이 아닙니다.')
 table([['목록 관계 · ±250m 민감도','구간 수'],['현재 목록 안','30'],['경계 민감','51'],['목록 범위 밖','740'],['보간 불가','22']],[350,145])
 p('문제 목록 11개와 최신 목록 8개의 전북 경계 안 추정 중첩을 제시합니다. 두 겨울 노출이 높고 목록 밖인 318구간은 방향별 8개 연속 범위로 묶입니다. 넓은 현장 확인 우선 범위이며 신규 위험구간 318곳을 독립적으로 발견했다는 의미가 아닙니다. 동률을 포함하므로 정확한 상위 25%도 아닙니다.')
 p('오프라인 목록 비교 화면은 위치 추정·공식 지정·조건 노출을 따로 보여 줍니다. 지정 해제 이유·사고 감소·제설 효과를 자료 없이 추정하지 않습니다.')
 page('10 · 실행·파일·재현')
 table([['현재 파일','용도'],['reports/analysis_report_v14.pdf','현재 12쪽 분석 보고서'],['code/predict_final.py','기본 v2·온도 v3. 비교 프로필은 명시 선택'],['notebooks/final_submission_review_v14.ipynb','전체 해시·두 프로필 실제 실행·집계·공간 결과·학습 명령'],['exports/final/final_observed_predictions_10min.csv','필수 관측·예측 103,680행; CSV·Parquet'],['exports/risk_review/','새 기준표·1,686행·Shapefile·GPKG·JPG'],['research/latest/weather_explorer_20261106_v13/','현재 69특성 풍속 843구간·240일 탐색'],['demo/index_v14.html · final_review_v14.mp4','실제 CLI 로그·결과를 설명하는 영상'],['manifest.json · validation/ · provenance/','파일별 해시·실행 검증·봉인·근거']],[255,240])
 p('실행: python -m pip install -r requirements-notebook.txt → python code/predict_final.py --input data/weather_example.csv --output local_review/my_final.csv --output-start 2024-12-15 --output-end 2024-12-16. 기존 출력은 덮어쓰지 않습니다.')
 p('모델자료에는 포함 허용 학습 자료·학습된 모형·고정 환경·원 모델 전체 학습 Notebook과 별도 기상 모형 재학습 코드가 있습니다. 기본 추론에 GPU·인증키·외부 예측 API가 필요하지 않습니다. 연구 전용 torch는 최종 추론 의존성이 아닙니다. 현재 결과와 과거 연구 이력을 구별하고 전체 원시 공간 캐시는 로컬 별도 보관합니다.')
 page('11 · 해석의 한계와 제출 안내')
 h('이번 결과가 뒷받침하는 범위')
 p('노면온도·기상 추정의 정량 오차, 관측 공백의 조건 노출, 현장 확인 대상의 근거와 자료 부족을 전달합니다. 결빙의 희소 관측·낮은 정밀도와 지점 간 전이 실패가 남습니다. 실제 안전 운영에는 수분·제설·노면 마찰·추가 센서·교통 및 현장 검증이 필요합니다.')
 p('500m와 1km 결과는 같은 도로를 다르게 나눈 것이고 독립 표본 수가 아닙니다. 두 겨울은 기후 평년이 아니며, 상위 노출 문턱은 자료 내부의 비교 기준입니다. 제공 정규화 DEM과 외부 미터 DSM을 구별합니다. 학습·프로필 선택과 최종 고정 대조의 시점을 보존합니다.')
 h('공통 심사 기준과 연결')
 table([['창의성 20','우수성 50','효과성 30'],['공간 제외·기상 관측망·고유 그룹 문턱','정확한 집계·누출 통제·관측 대조·실행 재현','오프라인 지도·필수 CSV·기준표·실행 설명']],[165,165,165])
 h('참고 원문')
 for label,url in [('공식 과제·693·716 및 제출564','https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004604/detail.do'),('기상청 풍향 코드','https://data.kma.go.kr/community/board/detailBoard.do?bbrdNo=1015&amp;bbrdTypeNo=3&amp;pgmNo=95'),('MicroMet · Liston and Elder 2006','https://research.fs.usda.gov/treesearch/26813'),('NWS · 겨울 결빙','https://www.weather.gov/safety/winter-ice-frost'),('Oregon DOT · 도로 결빙','https://www.oregon.gov/odot/Pages/Winter-Be-Ready-Ice.aspx')]:
  story.append(Paragraph(f'<link href="{url}">{label}</link>',small));md.append(label+' '+url.replace('&amp;','&'))
 p('문서자료 ZIP·모델자료 ZIP을 각각 해당 칸에 제출하고 사이트 이력을 확인합니다. 마감은 오늘 23:59 KST이며 업로드 혼잡 시 간격을 둔 재시도가 안내됐습니다. 실제 업로드·접수는 수행하지 않았습니다. 참가 승인 완료는 사용자 확인이며 로컬 검산을 참가자의 직접 검토로 기록하지 않습니다.')
 def footer(c,doc):
  c.setFont('Malgun',7.5);c.setFillColor(colors.HexColor('#6a818a'));c.drawString(48,27,'전북 고속도로 | 기상·노면온도·결빙 조건 · v14');c.drawRightString(547,27,f'{doc.page} / 12')
 pdf=OUT/'analysis_report_v14.pdf';SimpleDocTemplate(str(pdf),pagesize=(595.28,841.89),leftMargin=50,rightMargin=50,topMargin=43,bottomMargin=47).build(story,onFirstPage=footer,onLaterPages=footer)
 d=fitz.open(pdf);assert len(d)==12,f'Expected 12 pages, got {len(d)}'
 for i in range(len(d)):
  d[i].get_pixmap(matrix=fitz.Matrix(1.35,1.35)).save(OUT/f'page_{i+1:02d}.png')
  assert len(d[i].get_text())>150
 (OUT/'analysis_report_v14.md').write_text('\n\n'.join(md)+'\n',encoding='utf8')
 write(OUT/'build_receipt.json',dict(status='built_pending_visual_review',pages=len(d),pdf_sha256=sha(pdf),renderer='PyMuPDF',
 sources={p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),ASSETS/'metrics_summary.json',P/'wind_direction_terrain_20261106_v1/summary.json',P/'official_curl_review_20261106_v1/summary.json',P/'risk_review_20261106_v14/receipt.json']}))
 print('BUILT report',len(d),'pages',flush=True)
if __name__=='__main__':main()