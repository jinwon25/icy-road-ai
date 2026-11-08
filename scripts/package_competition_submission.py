"""분석 문서와 실행 자료를 두 제출 채널로 묶고 압축 내부를 대조한다."""
from pathlib import Path
import sys,json,re
import pandas as pd
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,copy,sha
from scripts.package_review_v8 import archive
from scripts.review_submission_bundle import verify_directory
from scripts.check_markdown import inspect_documents
P=ROOT/'outputs/private';OUT=P/'competition_submission';B=OUT/'icy_road_model';D=OUT/'icy_road_documents';W=P/'editorial_review_20261106'
def put(p,t):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(t,encoding='utf8')
def manifest(folder,channel):
 files={p.relative_to(folder).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in folder.rglob('*') if p.is_file() and p!=folder/'manifest.json' and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.relative_to(folder).parts[0]!='local_review'}
 value=dict(package_label='competition_submission',channel=channel,status='verified_local_submission',current_report='report/analysis_report.pdf',files=files,competition_submitted=False)
 if channel=='model':value.update(current_notebook='notebooks/analysis.ipynb',current_explorer='index.html',current_demo='demo/index.html')
 write(folder/'manifest.json',value);verify_directory(folder)
def main():
 assert read(W/'delivery_checks.json')['status']=='passed';assert not (B/'manifest.json').exists()
 for src,dst in [('report/analysis_report.pdf','report/analysis_report.pdf'),('AI_USAGE.md','AI_USAGE.md'),('results/evaluation/road_temperature_metrics.csv','data/road_temperature_metrics.csv'),('results/evaluation/icing_station_metrics.csv','data/icing_station_metrics.csv'),('results/evaluation/icing_day_counts.csv','data/icing_day_counts.csv'),('results/sections/criteria.csv','data/criteria.csv'),('results/sections/inspection_areas.csv','data/inspection_areas.csv'),('results/sections/route_summary.csv','data/route_summary.csv')]:
  copy(B/src,D/dst)
 for name in ['road_temperature','wind_distribution','condition_exposure','icing_calendar','inspection_locations']:
  copy(B/'report/figures'/(name+'.png'),D/'figures'/(name+'.png'))
 for name,new in [('condition_exposure','winter_exposure'),('inspection_locations','inspection_review')]:
  target=D/'maps'/(new+'.jpg');target.parent.mkdir(exist_ok=True)
  Image.open(B/'report/figures'/(name+'.png')).convert('RGB').save(target,quality=95,subsampling=0)
 put(D/'README.md','''# 전북 고속도로 겨울철 분석\n\n[분석 보고서](report/analysis_report.pdf)는 두 겨울의 자료·방법·평가와 공간 결과를 설명한다. [노면온도 관측 대조](figures/road_temperature.png), [풍속 분포](figures/wind_distribution.png), [조건 노출 지도](maps/winter_exposure.jpg), [이정별 계측 검토](maps/inspection_review.jpg)를 함께 제공한다.\n\n학습 제외 3지점의 노면온도 MAE 평균은 0.978°C, 기상 지역 전체 제외 풍속 MAE는 0.500m/s다. 결빙 정밀도는 0.0195, F1은 0.0326으로 오경보 문제가 남는다. 실제 Ice가 있는 1지점만 분류 평균에 포함했다.\n\n두 겨울의 조건과 교량·선형 정보, 공개 취약구간 목록을 대조해 500m 22구간을 방향별 11개 연속 범위로 묶었다. [선정 기준](data/criteria.csv)과 [전체 범위](data/inspection_areas.csv)는 추가 계측·시설 확인의 근거이며 새 공식 위험구간 지정이 아니다.\n\n실행 코드·학습 자료·모형·Notebook·기상 지도·실행 영상·필수 관측·예측 CSV·GIS는 모델자료 ZIP에 포함했다. [AI 활용 내역](AI_USAGE.md)을 함께 제공한다.\n''')
 put(B/'technical/competition_requirements.md','''# 과제 요구와 자료 위치\n\n공통 문제해결 평가 기준은 창의성 20·우수성 50·효과성 30이다. 과제의 회귀·분류·공간 결과별 별도 수치 배점을 임의로 합산하지 않았다.\n\n| 요구 | 자료 |\n| --- | --- |\n| 고속도로·지점·10분 시각과 관측·추정 | results/evaluation/observations_predictions.csv |\n| BIAS·MAE·RMSE와 날짜→지점 P/R/F1 | results/evaluation/ 및 분석 보고서 |\n| 500m 지도·기준표·공간 파일 | results/weather/, results/sections/, maps/sections.html |\n| 학습·추론 코드·자료·모형·Notebook·환경 | code/, data/, model/, notebooks/, weather/, requirements.txt |\n| 모델 테스트와 설명 데모 | demo/index.html |\n| AI 활용 및 이용조건 | AI_USAGE.md, licenses/ |\n\n과제 질의응답의 실제 Ice 없는 지점 제외, 무양성일 지표 처리, 정확한 10분 시각 대조, 다른 지점의 동시 노면상태 입력 금지, 정규화 DEM 단위, 자체 기준의 근거 명시를 적용했다. 두 겨울을 최근 10년 기후값으로 대체하지 않았다.\n\n[공식 과제](https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004604/detail.do) · [결과물 안내](https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=564)\n''')
 errors=[]
 for folder in [B,D]:errors+=inspect_documents(folder,[p.relative_to(folder).as_posix() for p in folder.rglob('*.md')])
 assert not errors,errors
 values=[]
 for line in (ROOT/'secret.env').read_text(encoding='utf-8-sig').splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   v=line.split('=',1)[1].strip().strip('"'+chr(39))
   if len(v)>=12:values.append(v.encode())
 for folder in [B,D]:
  for p in folder.rglob('*'):
   if not p.is_file() or 'local_review' in p.relative_to(folder).parts:continue
   assert p.suffix.lower() not in ['.env','.key','.pem','.hwp'],p
   if p.suffix.lower() in ['.py','.md','.json','.ipynb','.html','.csv','.txt','.js','.css','.log']:
    data=p.read_bytes();assert not any(v in data for v in values),p
    assert not re.search(rb'(?:github_pat_[A-Za-z0-9_]{40,}|RGAPI-[A-Za-z0-9-]{30,}|sk-[A-Za-z0-9_-]{30,})',data),p
 manifest(B,'model');manifest(D,'documents')
 archives={name:archive(folder,OUT/('icy_road_'+name+'.zip'),'icy_road_'+name) for name,folder in [('documents',D),('model',B)]}
 write(OUT/'submission_receipt.json',dict(status='two_channel_archives_verified',archives=archives,checks=read(W/'delivery_checks.json'),report_pages=8,demo_seconds=read(W/'video_review_checked/receipt.json')['seconds'],competition_submitted=False))
 put(OUT/'README.md','''# 제출 자료\n\n- 문서자료: icy_road_documents.zip\n- 모델자료: icy_road_model.zip\n\n[분석 화면](icy_road_model/index.html) · [분석 보고서](icy_road_model/report/analysis_report.pdf) · [실제 탐색·추론 영상](icy_road_model/demo/index.html)\n\n결과물 마감은 2026년 11월 6일 23:59 KST다. 두 ZIP을 각각 해당 제출 칸에 올리고 사이트의 접수 이력 반영을 확인한다. 실제 업로드는 수행하지 않았다. 파일별 검증 근거는 submission_receipt.json에 있다.\n''')
 print(json.dumps(archives,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
