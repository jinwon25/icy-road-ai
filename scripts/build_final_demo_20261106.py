"""실제 기본 CLI를 실행하고 로그·결과·지도를 설명하는 80초 영상."""
from pathlib import Path
import sys,subprocess,os,json,textwrap
import cv2,numpy as np,pandas as pd
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,sha
B=ROOT/'outputs/private/submission_candidate_20261106_v14';O=B/'demo/final_v14';O.mkdir()
env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
cmd=[sys.executable,'-X','utf8','code/predict_final.py','--input','data/weather_example.csv','--output','local_review/v14_demo_default.csv','--output-start','2024-12-15','--output-end','2024-12-16']
r=subprocess.run(cmd,cwd=B,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180);(O/'execution_log.txt').write_bytes(r.stdout)
assert r.returncode==0
f=pd.read_csv(B/'local_review/v14_demo_default.csv',float_precision='round_trip',dtype={'station':str});e=pd.read_csv(B/'data/final_example_predictions.csv',float_precision='round_trip',dtype={'station':str});pd.testing.assert_frame_equal(f,e,check_exact=True);assert len(f)==144
font=lambda size,bold=False:ImageFont.truetype('C:/Windows/Fonts/malgunbd.ttf' if bold else 'C:/Windows/Fonts/malgun.ttf',size)
slides=[]
def slide(title,lines=None,figure=None):
 im=Image.new('RGB',(1440,900),'#f2f6f8');d=ImageDraw.Draw(im);d.rectangle((0,0,1440,112),fill='#123c4b');d.text((55,32),title,font=font(39,True),fill='white')
 d.text((55,850),'v14 | 실제 CLI 로그와 결과를 재구성한 설명 영상 · 공식 서버 성적 아님',font=font(23),fill='#56727b')
 if figure:
  img=Image.open(figure).convert('RGB');img.thumbnail((1310,620));im.paste(img,((1440-img.width)//2,135))
  d.text((55,780),lines[0],font=font(25),fill='#203f4b')
 else:
  y=150
  for line in (lines or []):
   for part in textwrap.wrap(line,width=49,replace_whitespace=False) or ['']:
    d.text((65,y),part,font=font(30),fill='#203f4b');y+=49
   y+=12
 assert y<830 if not figure else True
 slides.append(im)
slide('01 · 완성물에서 확인할 내용',['기상 관측이 없는 전북 고속도로의 노면온도·기상 추정','두 겨울 · 500m 843구간 · 현재 69특성 풍속','최신 Q&A 반영: 필수 관측 대조와 날짜→지점 평균','기본 결빙 v2 유지 · 기온 0°C 기준선은 비교 열','지도는 조건 노출과 현장 검토 자료입니다.'])
slide('02 · 실제 기본 추론 실행',['python code/predict_final.py','--input data/weather_example.csv','--output local_review/v14_demo_default.csv','--output-start 2024-12-15 --output-end 2024-12-16','실제 종료 코드 0 · preserved_v2 · 144행','network_attempts=0 · 예제 144행 전체 정확 일치'])
rows=f[['time','predicted_road_temp','predicted_ice']].head(4) if 'predicted_road_temp' in f else f.head(4)
slide('03 · 입력·출력과 보호 원칙',['입력: 기상·시각·지점. 노면 관측 정답 열은 제외','출력: 추정 노면온도·결빙 0/1/NA·판정 상태','최종 제출 표는 고속도로명·지점명·10분 시각과','관측 노면상태·관측 노면온도·두 예측을 포함','103,680행 / 원 관측 누락 3행 / 추론 NA 18행','모델·프로필 봉인 후 관측 대조. 이후 재조정 없음'])
slide('04 · 제외 3지점 노면온도',['지점 평균 MAE 0.977562°C / 103,659 유효쌍','부곡교 MAE 1.112718°C','해전 MAE 1.044087°C / 삼봉 MAE 0.775881°C','BIAS 평균 -0.549055°C · 낮은 쪽 편향이 남음','보고서와 final_temperature_metrics.csv에 분모 명시'])
slide('05 · 결빙은 낮은 정밀도가 남습니다',['최신 방식 F1 0.032627 / P 0.019495 / R 0.593588','실제 Ice가 있는 부곡교 1지점만 분류 평균 대상','해전·삼봉은 산출불가. 0점으로 넣지 않음','기온 기준선 최종 F1 0.008698 · 개발 순위 역전','추가 10회 학습은 채택 조건 실패. 기존 v2 유지','자동 제설·안전 경보용으로 검증된 결과가 아님'])
slide('06 · 새 도로환경 검토', ['노출 비율·교량·선형 변화·입력 충분성. 실제 Ice 확률이 아닙니다.'],ROOT/'outputs/private/risk_review_20261106_v14/risk_review_maps.jpg')
slide('07 · 실제 풍속 구간 적용', ['69특성 모형 적용. 일별 202,320행과 오프라인 화면·CSV·GIS 연결.'],ROOT/'docs/images/wind_network_projection_20261102.png')
slide('08 · 확인 순서와 제출',['현재 12쪽 보고서 → 실제 실행·설명 영상','843구간 HTML 지도 → 관측·예측 CSV → 새 기준표','문서자료 ZIP / 모델자료 ZIP을 각각 제출','마감: 오늘 11월 6일 23:59 KST','업로드 혼잡 재시도 안내. 실제 접수 이력 확인 필요','이 영상 제작 과정에서는 대회 업로드를 수행하지 않음'])
video=B/'demo/final_review_v14.mp4';assert not video.exists();w=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),8,(1440,900));assert w.isOpened()
for i,im in enumerate(slides):
 im.save(O/f'slide_{i+1:02d}.png');frame=cv2.cvtColor(np.asarray(im),cv2.COLOR_RGB2BGR)
 for _ in range(80):w.write(frame)
w.release();capture=cv2.VideoCapture(str(video));assert capture.isOpened();total=int(capture.get(cv2.CAP_PROP_FRAME_COUNT));assert total==640
for i in range(8):
 capture.set(cv2.CAP_PROP_POS_FRAMES,i*80+40);ok,frame=capture.read();assert ok and frame.shape==(900,1440,3);encoded_ok,encoded=cv2.imencode('.png',frame);assert encoded_ok;(O/f'decoded_{i+1:02d}.png').write_bytes(encoded.tobytes())
capture.release()
(B/'demo/index_v14.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>최종 v14 실행·결과</title><style>body{font:17px/1.7 system-ui;max-width:1000px;margin:25px auto;padding:0 16px;color:#183e4b}video{width:100%}a{color:#12677c}</style><h1>최종 v14 실행·결과 설명</h1><p>80초 · 실제 기본 CLI 로그와 결과를 재구성한 설명 영상입니다. 화면 녹화·공식 서버 성적·참가자 직접 검토를 뜻하지 않습니다.</p><video controls preload="metadata" src="final_review_v14.mp4"></video><p><a href="final_v14/execution_log.txt">실제 실행 로그</a> · <a href="../reports/analysis_report_v14.pdf">현재 보고서</a> · <a href="../research/latest/weather_explorer_20261106_v13/index.html">현재 기상 지도</a></p></html>',encoding='utf8')
write(O/'receipt.json',dict(status='built_pending_visual_review',video_sha256=sha(video),frames=total,fps=8,seconds=80,width=1440,height=900,
 cli_returncode=r.returncode,cli_output_rows=144,exact_fixture_match=True,external_prediction_api=False,kind='actual CLI log reconstruction and explanatory figures; not screen recording',
 decoded_slide_centres=8,files={p.name:sha(p) for p in O.iterdir() if p.is_file()}))
print('BUILT demo 80 seconds, 640 frames, 144 CLI rows identical',flush=True)
