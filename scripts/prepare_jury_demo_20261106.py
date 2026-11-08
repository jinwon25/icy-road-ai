"""현재 종합 지도와 전 기간 실제 모형 실행을 보여주는 녹화 스크립트를 준비한다."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def swap(s,a,b):assert s.count(a)==1,(a,s.count(a));return s.replace(a,b)
def main():
    s=(ROOT/'scripts/record_evening_demo_20261106.py').read_text('utf8')
    s=s.replace("W=P/'evening_refinement_20261106'","W=P/'final_jury_review_20261106'")
    s=s.replace('demo_inference_team.csv','demo_full_jury.parquet')
    s=swap(s,"'--input','data/weather_example.csv','--output',str(output),'--output-start','2024-12-15','--output-end','2024-12-16'", "'--input','data/validation_weather.parquet','--output',str(output)")
    s=swap(s,"predicted=pd.read_csv(output,dtype={'station':str},float_precision='round_trip')",'predicted=pd.read_parquet(output)')
    s=swap(s,"expected=pd.read_csv(B/'data/example_predictions.csv',dtype={'station':str},float_precision='round_trip')", "expected=pd.read_parquet(B/'local_review/full_protected_predictions.parquet')")
    a="inputf=pd.read_csv(B/'data/weather_example.csv');shownin=inputf.loc[inputf.time.str.startswith('2024-12-15'),['station','time','asos_air_temp','aws_air_temp','aws_humidity']].head(4)"
    b="inputf=pd.read_parquet(B/'data/validation_weather.parquet');shownin=inputf[['station','time','asos_air_temp','aws_air_temp','aws_humidity']].head(4)"
    s=swap(s,a,b)
    s=s.replace('python code/predict.py --input data/weather_example.csv\n--output local_review/road_predictions.csv\n--output-start 2024-12-15 --output-end 2024-12-16',
                'python code/predict.py --input data/validation_weather.parquet\n--output local_review/full_predictions.parquet')
    s=s.replace('예제는 추론 재현용입니다. 보고서의 미관측 지점 검증 성적과는 구분합니다.',
                '학습에서 제외한 세 지점의 두 겨울 전체를 다시 추론한 결과입니다. 관측 정답은 입력하지 않았으며 표에는 예측값 일부를 표시합니다.')
    s=s.replace('결빙 조건 입력의 전체 시계열이 같은 조합은 한 번씩 집계했습니다. 두 겨울의 서로 다른 입력은 22개·24개입니다.',
                '공개 목록과 중첩 가능한 81구간과 추가 계측 후보 3구간을 함께 봅니다. 지도 색은 위험등급이 아니라 검토할 정보의 종류입니다.')
    s=s.replace("5,'실제 입력 정보 단위'","5,'목록과 추가 확인 종합'")
    a="  page.locator('#matrix').scroll_into_view_if_needed()"
    b="""  page.locator('#inventoryAgreement').scroll_into_view_if_needed()
  caption('목록과 명목상 겹치는 64구간 중 두 겨울 모두 기상 상위 25%에 든 곳은 0개였습니다. 이 기상 조건으로 기존 지정을 해제하지 않습니다.',7,'목록과 기상 조건의 불일치')
  page.locator('#matrix').scroll_into_view_if_needed()"""
    s=swap(s,a,b)
    s=s.replace('기상 상위 10%를 두 겨울 모두 요구하면 0구간입니다. 이를 도로가 안전하다는 판정으로 바꾸지 않습니다.',
                '기상 상위 10%를 두 겨울 모두 요구하면 추가 후보는 0구간입니다. 공개 목록과의 대조는 그대로 유지됩니다.')
    s=s.replace('포함된 기상 입력으로 로컬 Python 모형을 실제 실행했습니다. 예제 144행 전체가 포함된 기대 결과와 일치합니다.',
                '전체 검증 기상 103,680행을 로컬 모형으로 다시 추론했습니다. 온도와 결빙 예측 모두 제출 표의 값과 정확히 일치합니다.')
    s=s.replace('cli_rows=144','cli_rows=103680')
    s=s.replace('두 겨울 기상, 같은 관측쌍의 회귀 비교, 결빙 판정의 한계, 75개 기준 조합의 선택 민감도,',
                '두 겨울 기상, 같은 관측쌍의 회귀 비교, 결빙 판정의 한계, 공개 목록 대조와 75개 기준 조합의 민감도,')
    target=ROOT/'scripts/record_jury_demo_20261106.py';assert not target.exists();target.write_text(s,'utf8')
if __name__=='__main__':main()
