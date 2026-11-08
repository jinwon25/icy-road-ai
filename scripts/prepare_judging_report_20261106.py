"""현재 근거를 중심으로 노면온도·조건 분석·선정 민감도·지형을 연결한 보고서를 구성한다."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'outputs/private/judging_upgrade_20261106';B=W/'icy_road_model'
source=(ROOT/'scripts/build_precision_error_report_20261106.py').read_text('utf8')
target=ROOT/'scripts/build_judging_report_20261106.py';assert not target.exists()

def change(old,new):
    global source
    assert source.count(old)==1,(old[:100],source.count(old))
    source=source.replace(old,new)

change('import sys,html','import sys,html,re')
source=source.replace('precision_submission_update_20261106','judging_upgrade_20261106')
change(" story=[];md=[]"," story=[];md=['# 전북 고속도로의 겨울철 노면온도 추정과 결빙 취약구간 검토'];figure_number=0")
change("  md.extend(['| '+' | '.join(map(str,rows[0]))+' |','| '+' | '.join(['---']*len(rows[0]))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows[1:]])",
       "  md.append('\\n'.join(['| '+' | '.join(map(str,rows[0]))+' |','| '+' | '.join(['---']*len(rows[0]))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows[1:]]))")
change(" def picture(name,height=260,caption=''):\n  path=",
       " def picture(name,height=260,caption=''):\n  nonlocal figure_number\n  figure_number+=1;caption=f'그림 {figure_number}. '+re.sub(r'^그림 [0-9]+\\.\\s*','',caption)\n  path=")
change("Paragraph('0.50m/s',stat),Paragraph('지역을 통째로 제외한<br/>풍속 추정 MAE',body)",
       "Paragraph('14.6%',stat),Paragraph('같은 관측쌍에서 12특성 회귀 대비<br/>노면온도 MAE 감소',body)")
change("Paragraph('두 겨울 기상조건과 도로환경,<br/>공개 목록을 대조한 계측 검토 대상',body)",
       "Paragraph('기준 조합의 계측 검토 대상<br/>선정 기준 민감도 함께 제공',body)")
change("노면온도는 103,659개 관측쌍에서 지점 평균 MAE 0.978°C를 보였다. 결빙 판정 F1은 0.033으로 낮아 경보의 단독 근거로 삼기 어렵다. 결과의 활용 범위는 관측 공백 파악과 현장 확인 대상 선정에 두었다.",
       "노면온도는 103,659개 관측쌍에서 지점 평균 MAE 0.978°C를 보였다. 비교 가능한 103,131쌍에서는 기본 12특성 회귀보다 MAE가 14.6% 낮았다. 구간 선정의 기준 민감도와 지형 차폐도 함께 계산했다. 결빙 F1은 0.033으로 낮아, 활용 범위는 관측 공백 보완과 현장 확인에 두었다.")
change(" md.extend(['# 전북 고속도로의 겨울철 노면온도 추정과 결빙 취약구간 검토','요약: 노면온도 MAE 0.978°C, 공간 제외 풍속 MAE 0.500m/s, 추가 계측 검토 22구간. 결빙 F1 0.033의 한계를 포함한다.'])",
       " md.append('요약: 노면온도 MAE 0.978°C, 12특성 회귀 대비 공통 쌍 MAE 14.6% 감소. 기준 조합 22구간과 75개 기준의 민감도를 제공한다. 결빙 F1 0.033의 한계를 포함한다.')")
change("['도로·시설 정보','전북 경계 안 3노선의 중심선과 교량·터널 코드. 500m 보고 단위 843개']",
       "['도로·시설·지형','전북 3노선의 중심선·교량·터널 코드와 공개 GLO-30 DSM. 500m 보고 단위 843개']")
change("두 결빙 판정법의 출력을 고정한 뒤 관측과 대조했으며, 보고된 결과는 이 고정 대조의 성적이다.",
       "두 결빙 판정법의 출력을 고정한 뒤 관측과 대조했으며, 보고된 결과는 이 고정 대조의 성적이다. 보호 지점의 관측값을 이용해 새 모형을 학습하거나 문턱을 조정하지 않았다.")
benchmark=r"""
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
 p('ASOS 지면온도가 없는 시각 등이 제외되어 이 비교의 분모는 앞쪽 주평가 103,659쌍보다 작다. 원래 제출 예측과 주평가 지표는 바꾸지 않았다.',small)
"""
change(" page('도로 기상 추정')",benchmark+"\n page('도로 기상 추정')")
change("picture('wind_distribution',320,","picture('wind_distribution',240,")
change(" p('노면 에너지 교환에는 기온·수분·바람·복사 조건이 함께 작용한다[2].",
       " p('지정 검증 3지점의 기온·습도·1분 풍속은 제공 원본에서 모두 결측코드였다. 예측 103,680행을 먼저 고정한 뒤 가용성을 확인했으며, 세 기상 요소의 유효 관측쌍은 각각 0개다. 해당 성능은 NA로 두고 다른 관측소 값을 도로 실측 정답으로 대체하지 않았다. 위 표는 이 세 지점의 점수가 아니라 별도 지역 제외 평가다.',small)\n p('노면 에너지 교환에는 기온·수분·바람·복사 조건이 함께 작용한다[2].")
conditions=r"""
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
"""
change(" page('겨울별 조건 노출과 도로환경')",conditions+"\n page('겨울별 조건 노출과 도로환경')")
sensitivity=r"""
 page('선정 기준을 바꾸면 남는 구간')
 p('상위 기상 빈도와 중심선 방향 변화의 기준을 각각 상위 40·30·25·20·10%로, 공개 목록의 경계 여유를 ±100·250·500m로 바꾼 75개 조합을 비교했다. 원래 기준 조합은 상위 25%·상위 25%·±250m이며, 결과가 좋아 보이는 조합으로 바꾸지 않았다.')
 picture('selection_sensitivity',185,'75개 자체 기준 조합의 선택 구간 수. 갈색 테두리가 기준 조합 22구간이다. 모든 그림의 색 범위는 0~86개로 같다.')
 rows=[['기준 범위','500m 구간 수','75개 조합의 선택 유지율']]
 stability=pd.read_csv(B/'results/sections/sensitivity/area_stability.csv')
 for r in stability.itertuples():
  a=100*r.minimum_selection_fraction;b=100*r.maximum_selection_fraction
  rows.append([r.inspection_area_id,int(r.segments),f'{a:.0f}%' if a==b else f'{a:.0f}~{b:.0f}%'])
 table(rows,[100,145,262])
 p('기준 조합에서는 843개 중 기상 조건을 두 겨울 모두 충족한 곳이 95개, 교량·선형 조건까지 충족한 곳이 27개, 공개 목록 밖 조건까지 충족한 곳이 22개였다. 가용성 문턱을 90~99%로 바꿔도 기준 조합의 22개는 같았다.',small)
 p('75개 조합의 선택 개수는 0~86개이고, 모두에서 유지되는 구간은 없다. 기상 상위 10%를 두 겨울 모두 요구하면 0개다. F06의 두 구간은 60개 조합(80%)에서 유지돼 현장 확인의 우선 근거로 삼을 수 있다. 유지율은 결빙확률이나 통계적 신뢰도가 아니며, 선정되지 않은 구간의 안전을 입증하지 않는다.',small)
 page('지형에서 확인할 낮의 일사 환경')
 p('같은 기상을 공유하는 도로에도 주변 지형은 다르다. 공개 GLO-30 DSM의 네 타일에서 기존 지도와 같은 843중점을 조회하고, 16방향·3km 지평선과 10분 태양위치 근사식을 대조했다[9,10]. 제공된 정규화 DEM을 미터로 해석하지 않고 별도 공개 원본의 미터 표고를 사용했다.')
 picture('terrain_solar_context',330,'2024/25 겨울의 지형 차폐 가능 낮 시간 비율과 F06·F08의 대표 중점. 오른쪽은 같은 고도각 축의 DSM 지평선과 동지 태양 경로다.')
 p('F06의 대표 중점에서는 태양 고도가 양수인 시점의 15.2%가 근사 지평선 아래에 있었다. F08 대표 중점은 4.6%였다. 탐색을 1km로 줄이면 각각 15.2%·1.8%가 되어 먼 지형의 반영 범위에 따라 결과가 달라졌다. 각 범위에서 추정 이정이 가장 앞선 중점을 예시로 사용했으며, 전체 구간의 결과와 1km 비교를 CSV로 제공한다.')
 h('지형 지표를 위험 배점으로 곧바로 더하지 않은 이유')
 p('차폐는 낮의 직달 일사와 관련되고 하늘 개방도는 야간 복사 교환에도 관련된다[2]. 구름·제설·수분과 함께 작용하므로 한 방향의 위험 가중치로 합산할 근거가 부족하다. 이 지형 정보는 현장에서 그늘·수분·시설을 확인할 맥락으로 제시하고, 추정 모형이나 기준 조합의 선정에는 새 가중치를 넣지 않았다.')
 p('DSM은 수목·건물·시설물을 포함하며 취득 시기 이후의 공사를 반영하지 못할 수 있다. 교량 상판 높이·도로 경사·터널 내부를 측량한 값이 아니고, 계산된 낮 시간 비율은 실제 일조·일사량 관측도 아니다.',small)
 p('produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.',small)
"""
change(" page('활용 범위와 결론')",sensitivity+"\n page('활용 범위와 결론')")
change("공간 결과의 저온·수분 문턱과 도로환경 기준은 분석용 비교 기준이다.",
       "공간 결과의 저온·수분 문턱과 도로환경 기준은 분석용 비교 기준이다. 기준 조합 22구간의 선택 유지율은 36~80%였고, 이를 확정된 신규 위험구간으로 제안하지 않는다.")
old=" ('[8] 한국도로공사. 암거 현황. 공공데이터포털.','https://www.data.go.kr/data/15159523/fileData.do')]"
new=""" ('[8] 한국도로공사. 암거 현황. 공공데이터포털.','https://www.data.go.kr/data/15159523/fileData.do'),
 ('[9] Copernicus DEM GLO-30. 자료 설명·DSM와 이용조건.','https://doi.org/10.5270/ESA-c5d3d65'),
 ('[10] NOAA GML. Solar Calculation Details. 태양위치 근사식의 범위.','https://gml.noaa.gov/grad/solcalc/calcdetails.html')]"""
change(old,new)
change("assert len(doc)==9","assert len(doc)==13")
change("B/'technical/development_error_analysis.json']", "B/'technical/development_error_analysis.json',B/'technical/judging_evidence.json',B/'results/evaluation/temperature_benchmarks/metrics.csv',B/'results/sections/sensitivity/scenario_summary.csv',B/'results/conditions/association_ranges.csv',B/'results/sections/terrain/segment_solar_context.csv']")
target.write_text(source,'utf8')
original=B/'report/analysis_report.pdf';saved=W/'original_analysis_report.pdf'
assert original.resolve().is_relative_to(W.resolve()) and saved.resolve().is_relative_to(W.resolve()) and not saved.exists()
original.replace(saved)
print('현재 결과 기준의 13쪽 보고서 조판 준비 완료')
