"""검산된 후보 결과와 실행매뉴얼을 한글PDF로 만들고 페이지PNG를 저장한다."""
from pathlib import Path
import html
import json
import sys
import fitz
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak
from reportlab.lib.pagesizes import A4

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write
from src.data_source import sha256_file as sha

OUT=ROOT/'outputs/private/submission_candidate_20261013_v1'


def main():
    target=OUT/'reports/결빙_분석_제출후보_보고서.pdf'
    if target.exists():raise FileExistsError('Preserve rendered report')
    audit=read(OUT/'validation/independent_verification.json');assert audit['status']=='submission_candidate_independent_audit_passed'
    spatial=read(OUT/'spatial_receipt.json');policy=read(ROOT/'outputs/private/thermal_consensus_20261013_v1/summary.json')
    pdfmetrics.registerFont(TTFont('Malgun','C:/Windows/Fonts/malgun.ttf'));pdfmetrics.registerFont(TTFont('MalgunBold','C:/Windows/Fonts/malgunbd.ttf'))
    base=dict(fontName='Malgun',fontSize=10.1,leading=16,textColor=colors.HexColor('#253342'),wordWrap='CJK')
    styles={'body':ParagraphStyle('body',**base,spaceAfter=9),
        'small':ParagraphStyle('small',**(base|{'fontSize':8.3,'leading':12}),spaceAfter=7),
        'title':ParagraphStyle('title',fontName='MalgunBold',fontSize=24,leading=33,textColor=colors.HexColor('#183b59'),spaceAfter=20,wordWrap='CJK'),
        'h1':ParagraphStyle('h1',fontName='MalgunBold',fontSize=18,leading=25,textColor=colors.HexColor('#183b59'),spaceAfter=16,wordWrap='CJK'),
        'h2':ParagraphStyle('h2',fontName='MalgunBold',fontSize=12,leading=18,textColor=colors.HexColor('#183b59'),spaceBefore=7,spaceAfter=7,wordWrap='CJK')}
    story=[]
    def p(text,style='body'):return Paragraph(text,styles[style])
    def text(t,style='body'):story.append(p(t,style))
    def table(rows,widths):
        wrapped=[[p(html.escape(str(c)),'small') for c in row] for row in rows]
        t=Table(wrapped,colWidths=widths,repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7eef4')),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#91a8ba')),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#d9e1e7')),
            ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.extend([t,Spacer(1,10)])
    def page():story.append(PageBreak())
    text('전북 고속도로 결빙 분석<br/>제출 후보 결과와 실행매뉴얼','title')
    text('2026 DATA·AI 분석 경진대회<br/>검토 기준일 2026년 10월 13일','small')
    text('도로 관측이 없는 위치의 노면온도를 공공 기상으로 추정하고, 저온과 수분 조건이 함께 나타나는 시점을 구간별로 제시한다. 개발 자료의 온도 오차와 결빙 탐지 개선, 성분 불일치, 입력 공백을 함께 기록해 현장 확인에 필요한 근거를 제공한다.')
    text('주요 결과','h2')
    table([['항목','결과와 범위'],['온도 개발 검증','첫 겨울 공간 제외9곳. 지점 평균MAE1.200531°C. 기존1.232271°C 대비2.58% 감소'],
        ['결빙 개발 검증','일평균F1 0.030633, Precision0.052803, Recall0.774688. Recall은 양성 관측8곳의 평균'],
        ['실행용 대표 후보','허용23곳의 첫 겨울397,126행으로 MSE/MAE300 모델2개를 고정 적합. 새 독립 성능평가 없음'],
        ['두 겨울 위치 추정','보호3곳103,680행. 유효추정103,662행, 입력부족18행. 정답 재평가 없음'],
        ['전북 공간 결과','500m843개·1km423개. 두 겨울10분 추정 색인·요약·GPKG·Shapefile·JPG']],[110,405])
    text('핵심 판단','h2')
    text('온도와 일부 결빙 지표는 개발 자료에서 개선됐다. 일별 평균Precision 하락과 반복 개발의 선택 편향이 남아 최종 모델 승격은 보류한다. 지도는 기상 기반 저온·수분 조건의 추정 노출이며 실제Ice 또는 사고확률의 검증값이 아니다.')
    text('공식CSV 규격·결과물 제출 날짜·일부 일별 결측 정책은 추가 공지 확인이 필요하다. 이 보고서의 개발 지표를 보호3곳의 공식 점수로 사용하지 않는다.','small')
    page()
    text('평가 설계와 공식 지표','h1')
    text('첫 겨울23개 허용 지점만 학습에 사용한다. 외부 개발9개 지점을4개 공간 그룹으로 나누고, 후보 선택에 사용할 예측은 선택 그룹과 적용 그룹을 모두 제외한 모델로 만든다. 이미 개봉한 평가·보호 정답·둘째 겨울 정답은 이번 개발·선택·검산에 사용하지 않는다.')
    text('날짜별 혼동행렬을 구한 뒤 각 지점의 일평균, 지점별 값의 단순 평균을 계산한다. 전체시점 혼동행렬의 지표는 진단으로 구분한다. 관측이 없는 날짜와 전 기간 미정의인 지점을 비결빙 또는0점으로 채우지 않는다.')
    table([['날짜 조건','Precision','Recall','F1'],['실제·예측 결빙 모두0','평균 제외','평균 제외','평균 제외'],['실제 결빙>0·예측0','미정의·제외','0 포함','0 포함'],['실제0·예측 결빙>0','0 포함','분모0·잠정null','0 포함']],[230,95,95,95])
    text('633번의10월13일 답변으로 미탐일의 처리를 확인했다. 오경보만 있는 날의Recall 평균 정책과 부분 날짜의 최소 관측량은 명시 답변이 없어 잠정값을 구분한다.144·130·72·1유효슬롯 조건을 모두 저장한다.')
    table([['고정 판정','P 평균','R 평균','F1 평균','FP / FN'],['기존 온도3종 평균','0.055359','0.753175','0.030231','20,889 /4,982'],
        ['기상12·2종 평균','0.052803','0.774688','0.030633','20,255 /4,952']],[155,75,75,75,135])
    text('완전일 조건에서Precision/F1은9곳, Recall은8곳이 정의된다. 평균을 낸 날짜·지점쌍은 후보P307/R124/F1 365개다. Recall9곳 전체 평균은null이다. 전체FP/FN 감소가 일평균Precision 증가를 보장하지 않는다.','small')
    text('실제 Ice일 1개가 144슬롯 조건에서 제외된다. 1슬롯 조건의 후보 F1은 0.030115다. 더 유리한 관측량 기준을 공식 점수로 고르지 않았다.','small')
    text('근거: 공식문제·Q&A633. 보호 분리와 반복 선택의 한계는Roberts et al.(2017), Cawley and Talbot(2010)을 참고했다.','small')
    page()
    text('추가 열·수분 가설과 채택 판단','h1')
    text('MSE/MAE 두 온도 추정의 평균·최솟값·최댓값, 저온 경계 -0.5/0/0.5°C, 이슬점 여유0/1°C의 고정18개 가설을 비교했다. 강수·눈 관측은 수분조건으로 유지했다. 해당 경계는 개발 가설이며 문헌의 보편적 임계값으로 제시하지 않는다.')
    text('선택에는 다른 3개 공간 그룹의 이중 제외 예측만 사용했다. 144 및 1슬롯 조건의 P/R/F1 비악화, FP/FN 비증가, 양성 지점의 TP 유지, 기존 탐지 사건 손실 0을 모두 요구했다. 4개 외부 그룹 모두 적격 후보가 없어 기존 판정을 유지했다.')
    names=['original_trio','mean_cold-0.5_dew+1.0','warmest_cold+0.0_dew+1.0','current_pair','nested_selected']
    rows=[['판정','F1','P','FN','기존사건 손실']]
    labels=['기존3종 평균','평균 -0.5°C·여유1°C','최댓값0°C·여유1°C','현재2종 평균','공간 내부 선택 정책']
    for name,label in zip(names,labels):
        item=policy['reports'][name];r=item['report'];rows.append([label,f"{r['daily']['144']['f1_available_station_mean']:.6f}",f"{r['daily']['144']['precision_available_station_mean']:.6f}",str(r['fn']),str(item['retention']['lost_events'])])
    table(rows,[220,80,80,65,70])
    text('평균 -0.5°C·여유 1°C는 F1과 Precision이 높아졌지만 FN이 4,982에서 5,052로 늘고 기존 탐지 사건 3개를 놓쳤다. 일부 지표의 최고값만 골라 채택하지 않았다.')
    text('사건은 같은 지점에서 10분 간격으로 연속된 실제 Ice의 덩어리로 정의한다. 총 탐지 사건의 순증가와 기존 사건 손실을 따로 비교한다. 단일 시각 Ice도 제거하지 않는다. 18가설에 현재 후보의 중복 대조를 더한 19비교와 기준·선택 판정의 일별 90,720행을 별도 검산했다.')
    text('Bouilloud et al.(2009)의 노면 열·수분·눈 모형을 물리적 맥락으로 참고했다. 이번 규칙에는 도로 염분·제설·열수지 모사가 없다. scikit-learn의 임계값 지침에 따라 선택용 자료와 적용 그룹을 분리했다.','small')
    page()
    text('두 겨울의 구간 조건 노출','h1')
    image=Image(str(OUT/'figures/candidate_condition_map_500m.jpg'),width=515,height=352)
    story.append(image);story.append(Spacer(1,12))
    text('노출 비율은 해당 구간 중점의 유효 추정 시점 중 평균 노면온도 <=0°C와 수분 조건을 동시에 만족하는 시점의 비율이다. 10분 슬롯 6개를 1시간 상당량으로 표현한다. 연속 결빙 사건 수나 실제 빙판 지속시간으로 해석하지 않는다.')
    text('동일한 AWS 후보 순서와 ASOS를 쓰는 위치의 거리 없는 기상 12입력은 같다. 이를 138개 공통 기상 그룹으로 저장하고 위치 색인으로 43,752,960개 구간 시점을 표현한다. 위치별 전체 CSV는 내보내기 명령으로 펼칠 수 있다.')
    text('교량·터널 코드 비율과 정적 도로 속성은 함께 저장한다. 공식 이정·실제 시설 범위·일사 차폐·도로 염분은 추가 확인이 필요하다. 1km 후보도 중점 추정이며 기존 500m 길이 가중 1km 통계와 집계가 다르다.','small')
    page()
    text('조건 기준표와 입력 품질','h1')
    table([['조건 코드','판정 기준','해석'],['insufficient_input','유효 ASOS 없음 또는 수분 3열 모두 결측','판정 null. 입력 보완과 현장 확인'],['cold_wet_consensus','평균 <=0°C·수분 조건·두 성분 모두 <=0°C','저온·수분 조건에 모델 합의'],['cold_wet_disagreement','평균 <=0°C·수분 조건·한 성분 >0°C','경계 조건. 성분 불일치 표시'],['criterion_not_met','유효 입력에서 결합 기준 미충족','판정 0. 안전 보장 없음']],[155,205,155])
    text('이 기준표는 입력 근거와 모델 조건을 정리한다. 보정된 Ice 확률·사고확률·공식 A/B/C 위험등급을 부여하지 않는다. 성분 차이도 전체 예측오차나 90% 보장 범위와 다르다.')
    text('추론 입력계약','h2')
    text('station,time,asos_air_temp,aws_air_temp,aws_humidity,aws_wind_speed,aws_rain_15m,aws_dewpoint,aws_age_minutes,asos_age_minutes,hour_sin,hour_cos,season_sin,season_cos,rain15_max_3h,asos_snow_cm','small')
    text('시각은 Asia/Seoul의 정확한 10분 격자다. 공공 기상은 목표 시각보다 엄격히 이전인 60분 이내 관측만 결합한다. 숫자 결측 -999/-99.9/-99.2/-99.7은 NaN으로 정리한다. 미래 관측·중복·잘못된 시각·정답 열을 거부한다. 오래된 AWS를 제거하며 유효 ASOS와 수분 입력이 없으면 판정을 null로 둔다.')
    text('보호 3곳 두 겨울 103,680행 중 18행이 입력 부족이다. 현재 후보는 이 경우 예측을 거부한다. 개발 판정의 기존 분류 fallback 21행과 처리가 다르므로, 입력 부족 운영 성능까지 기존 F1 검증으로 입증했다고 표현하지 않는다.')
    text('검산 범위','h2')
    text(f"기상 특징 {audit['weather_feature_values_verified']:,}값을 NumPy의 별도 시간 탐색으로 확인했다. 추론값 {audit['prediction_values_verified']:,}개와 보호 예측 103,680행이 일치했다. 고정 2모델을 다시 적합하고 대표 재추론 103,680값이 일치했다. 검산 접속 시도는 0건이다.")
    page()
    text('재현 실행과 제출 준비','h1')
    text('Python 3.11·CPU 환경이며 GPU/CUDA를 요구하지 않는다. 라이브러리 버전을 requirements.txt에 고정했다. 의존성 설치 이후의 학습·추론은 포함된 로컬 자료만 사용한다.')
    for command in ['python -m pip install -r requirements.txt','python -X utf8 code/predict.py --input data/weather_example.csv --output validation/new_example.csv','python -X utf8 code/train.py --output validation/new_models','python -X utf8 code/export_predictions.py --kind protected --output validation/target_csv','python -X utf8 code/export_predictions.py --kind segment --scale 500 --id 8eabed369e9c40e7 --output validation/segment_csv']:
        text(html.escape(command),'small')
    text('기존 출력이 있으면 중단한다. 모든 구간을 펼치려면 --id를 생략한다. 공통 기상 그룹 저장으로 중복을 줄였지만 전체 구간 CSV로 펼치면 파일 크기와 생성시간이 증가한다.')
    table([['항목','상태'],['모델·학습표·일반 추론·매뉴얼','준비 완료. 전체 적합은 실행용이며 독립 성능평가와 구별'],['10분 보호 예측·구간 색인·공간파일','준비 완료. 정답 재평가 없음, 결측 18행'],['공식 최종 CSV·제출일·일부 일별 정책','주최 측 추가 공지 확인 필요'],['새 지점 성능·최종 모델 승격','보류. 반복 개발 개선만으로 채택하지 않음'],['공식 이정·시설 범위·검증 위험등급','미확정. 현재 조건 노출을 사고 위험등급으로 전용하지 않음']],[240,275])
    text('원본 ZIP·신청서·서명·개인정보·인증키·Git 이력·보호 정답·개봉 평가 정답을 묶음에서 제외했다. 제공 자료와 파생물은 참가 권한 내 비공개로 관리한다. 과거 모델·봉인·평가 파일은 원본 프로젝트에서 보존한다.')
    text('참고 자료','h2')
    for item in read(OUT/'reports/reference_applications.json'):
        url=html.escape(item['url'],quote=True);text(f'<link href="{url}" color="#21577c">{html.escape(item["title"])}</link>: {html.escape(item["application"])}','small')
    def footer(canvas,doc):
        canvas.setFont('Malgun',8);canvas.setFillColor(colors.HexColor('#667787'));canvas.drawString(40,27,'icy-road-ai / 비공개 제출 후보 / 개발 검증과 공식 평가 구별');canvas.drawRightString(A4[0]-40,27,str(doc.page))
    doc=SimpleDocTemplate(str(target),pagesize=A4,rightMargin=40,leftMargin=40,topMargin=43,bottomMargin=45,title='전북 고속도로 결빙 분석 제출 후보 결과와 실행매뉴얼',author='icy-road-ai')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    pdf=fitz.open(target);preview=OUT/'validation/pdf_preview_v4';preview.mkdir()
    for i,page in enumerate(pdf):page.get_pixmap(matrix=fitz.Matrix(1.4,1.4)).save(preview/f'page_{i+1}.png')
    assert len(pdf)==6,'Unexpected report overflow'
    for page in pdf:assert len(page.get_text())>120
    write(OUT/'validation/pdf_render_receipt_v4.json',dict(pdf_sha256=sha(target),pages=len(pdf),rendered_pngs=len(pdf),visual_review_pending=True))
    print('PDF 페이지',len(pdf))


if __name__=='__main__':main()
