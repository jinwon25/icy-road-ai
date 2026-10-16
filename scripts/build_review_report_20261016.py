"""기준선·지점 편중·재현성 정정 4쪽을 기존 분석 보고서 앞에 붙인다."""
from pathlib import Path
from datetime import datetime,timezone
import html
import json
import sys
import fitz
import pandas as pd
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write
from src.data_source import sha256_file as sha
from scripts.benchmark_submission_baselines import counts

PRIVATE=ROOT/'outputs/private';OUT=PRIVATE/'review_report_20261016_v1'
BENCH=PRIVATE/'baseline_benchmark_20261016_v1'
LABELS={'current':'현재 온도·수분 후보','previous_trio':'이전 온도 3종·수분','always_zero':'항상 비결빙','always_one':'항상 결빙',
        'asos_air_temp_le_zero':'ASOS 기온 ≤0°C','estimated_road_temp_le_zero':'추정 노면온도 ≤0°C'}
SOURCES=[
    ('KISTI 공식 문제·자료·참가양식','https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004604/detail.do'),
    ('KISTI 일별 평가 Q&A633','https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=633'),
    ('KISTI 결과물 제출 공지564','https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=564'),
    ('Lipton, Elkan & Narayanaswamy (2014). Thresholding Classifiers to Maximize F1 Score.','https://arxiv.org/abs/1402.1892'),
    ('Reinke et al. (2024). Understanding metric-related pitfalls in image analysis validation. Nature Methods 21, 182-194.','https://www.nature.com/articles/s41592-023-02150-0'),
    ('Saito & Rehmsmeier (2015). The Precision-Recall Plot Is More Informative than the ROC Plot When Evaluating Binary Classifiers on Imbalanced Datasets.','https://doi.org/10.1371/journal.pone.0118432'),
    ('scikit-learn 1.6.1. DummyClassifier.','https://scikit-learn.org/1.6/modules/generated/sklearn.dummy.DummyClassifier.html'),
    ('pandas 2.2.3. read_csv: float_precision=round_trip.','https://pandas.pydata.org/pandas-docs/version/2.2.3/reference/api/pandas.read_csv.html'),
]


def main():
    if OUT.exists():raise FileExistsError('Preserve prior report')
    summary=read(BENCH/'summary.json');prepared=read(PRIVATE/'submission_candidate_20261016_v1/validation/review_20261016_prepare.json')
    official=read(PRIVATE/'official_updates_20261016_v1/completion_receipt.json')
    assert prepared['csv_parquet_temperature_different_rows']==0
    OUT.mkdir();(OUT/'preview').mkdir()
    pdfmetrics.registerFont(TTFont('Malgun','C:/Windows/Fonts/malgun.ttf'))
    pdfmetrics.registerFont(TTFont('MalgunBold','C:/Windows/Fonts/malgunbd.ttf'))
    styles={
        'title':ParagraphStyle('title',fontName='MalgunBold',fontSize=19,leading=27,textColor=colors.HexColor('#142d42'),spaceAfter=16),
        'h2':ParagraphStyle('h2',fontName='MalgunBold',fontSize=12,leading=18,spaceBefore=12,spaceAfter=7),
        'body':ParagraphStyle('body',fontName='Malgun',fontSize=10,leading=16,spaceAfter=9,wordWrap='CJK'),
        'small':ParagraphStyle('small',fontName='Malgun',fontSize=8.8,leading=13,spaceAfter=7,wordWrap='CJK'),
        'cell':ParagraphStyle('cell',fontName='Malgun',fontSize=8.2,leading=12,wordWrap='CJK'),
    }
    flow=[];markdown=[]
    def text(value,kind='body'):
        flow.append(Paragraph(value,styles[kind]));markdown.append(value.replace('<b>','').replace('</b>',''))
    def title(value):text(value,'title')
    def table(rows,widths):
        cells=[[Paragraph(html.escape(str(v)),styles['cell']) for v in row] for row in rows]
        t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eff4')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#567080')),
            ('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#d4dce1')),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        flow.extend([t,Spacer(1,10)])
        markdown.append('\n'.join('| '+' | '.join(map(str,row))+' |' for row in [rows[0],['---']*len(rows[0]),*rows[1:]]))
    def fmt(value):return '-' if value is None else f'{value:.6f}'
    title('결빙 기준선 비교와 재현성 정정')
    text('2026년 10월 16일 추가 검증 · 개발 첫 겨울 9개 지점','small')
    text('현재 후보는 단순 기준선보다 일별 F1이 낮습니다. 온도 MAE 개선을 결빙 탐지의 우수성으로 확대하지 않고, 성능 적합 판단과 새 지점 독립 검증을 보류합니다. 실행 모델을 바꾸는 대신 누락된 기준선과 재현 경로의 오류를 보완했습니다.')
    text('단순 기준선과 같은 규약으로 비교','h2')
    rows=[['방법','일별 F1','P 평균','R 평균*','FP','FN','F1 날짜/지점']]
    for name,item in summary['reports'].items():
        d=item['coverage']['144'];c=item['counts']
        rows.append([LABELS[name],fmt(d['f1_available_station_mean']),fmt(d['precision_available_station_mean']),fmt(d['recall_available_station_mean']),f"{c['fp']:,}",f"{c['fn']:,}",f"{d['f1_days']}/{d['f1_stations']}"])
    table(rows,[119,64,59,59,62,57,87])
    text('일별 지표는 144개 유효 관측이 있는 1,060개 지점일에서 날짜 평균 후 지점 평균을 계산했습니다. 예정 지점일은 1,080개입니다. FP/FN은 부분 날짜를 포함한 유효 상태 155,118행의 합계로, 일별 F1과 집계 단위가 다릅니다. 최소 관측량 144는 잠정 조건입니다.','small')
    text('* R은 양성이 존재하는 8개 지점의 평균입니다. 9개 전체 지점 평균은 미정의입니다. 항상 비결빙의 F1도 유효 8개 지점 평균이며 9개 지점 전체 평균으로 표시하지 않습니다.','small')
    text('실제·예측 결빙이 모두 없는 날은 F1 평균에서 제외되므로 방법마다 날짜 분모가 달라집니다. 144·130·72·1 관측 조건의 24개 보고서, 일별 25,920행과 지점 216행을 별도 NumPy 구현으로 검산했습니다.','small')
    text('입력 부족 21행에서 단순 온도 규칙은 기존 고정 개발 판정과 같은 0 관례를 사용했습니다. 제출 추론에서는 부족 입력을 null로 유지합니다. 임계값 탐색이나 새 모델 학습은 수행하지 않았습니다.','small')
    flow.append(PageBreak())
    title('지점 구성에 따른 성능 변화')
    frame=pd.read_parquet(BENCH/'fixed_comparator_predictions.parquet')
    rows=[['지점','실제 Ice','TP','FP','FN','시점 Recall']]
    for station in summary['population']:
        f=frame.loc[frame.station.eq(station)];c=counts(f,f.current)
        rows.append([station,f"{c['tp']+c['fn']:,}",f"{c['tp']:,}",f"{c['fp']:,}",f"{c['fn']:,}",fmt(c['recall'])])
    table(rows,[85,78,78,85,78,103])
    text('실제 Ice 6,611행 중 6,340행(95.9%)이 33408에 있습니다. 현재 후보의 전체 시점 Recall은 25.1%이며 이 지점을 제외한 271개 양성에서는 97.8%입니다. 그러나 제외 후 Precision은 1.39%에 불과해 오경보 문제는 남습니다.')
    text('지점을 제외해 결과를 개선하거나 라벨을 삭제하는 근거로 쓰지 않습니다. 원인 규명에는 센서 범위·상태 코드·제설·염분·시각 이력이 필요합니다. 현재 비교는 이미 여러 차례 사용한 개발 자료이므로 새 지점의 독립 성능으로 읽을 수 없습니다.')
    text('F1과 운영 부담을 함께 판단','h2')
    ratio=summary['fp_fn_cost_break_even_miss_to_false_alarm']
    text(f'현재 후보는 항상 결빙보다 FP 128,252행이 적고 FN 4,952행이 많습니다. 시점별 선형 비용을 가정한 단순 계산에서 미탐/오경보 비용 비율의 손익분기는 {ratio:.2f}입니다. 실제 경보 묶음·제설 운영비용을 추정한 값이 아니므로 이 비율로 모델을 선택하지 않습니다.')
    text('다음 후보는 단순 기준선의 일별 F1과 FP/FN, 지점별 손실, 기존 사건 보존을 함께 비교해야 합니다. 보호·이미 개봉한 평가 정답으로 선택 기준을 맞추지 않고, 후보를 고정한 후 미사용 적격 지점에서 평가해야 합니다.','small')
    flow.append(PageBreak())
    title('추론과 제출물 재현 경로의 수정')
    table([
        ['확인된 문제','반영한 수정과 검증'],
        ['저장소 CSV 기본 파서','read_weather를 공통 사용해 float_precision=round_trip 적용. 저장소 CLI·ZIP CLI·Parquet의 같은 144행과 기존 기대값이 정확히 일치. 온도·결빙 차이 0행.'],
        ['모델 카드 집계 이름','전체 행 MAE 1.2005309458과 지점 균등 MAE 1.2004399739를 실제 포함 예측에서 계산. 생성 코드와 새 ZIP 카드에 같은 필드 적용.'],
        ['구형 데모를 현재 후보로 안내','현재 2모델 평균은 python -m src.submission_runtime으로 안내. demo_inference.py는 과거 Ridge·HGB 기준선으로 표시.'],
        ['삭제된 임시 해제 폴더 의존','보존된 원본 ZIP의 해시 목록과 외부 SHA-256을 확인해 새 폴더로 복원. 기존 폴더 덮어쓰기·경로 탈출·중복 멤버·해시 변조를 차단.'],
        ['입력 계약의 빈틈','동일 지점의 12207/12207.0을 정규화 후 중복 확인. 기상 관측 나이 0 이하를 거부하고 10분 격자의 나노초 편차도 거부.'],
    ],[117,390])
    text('모델과 예측의 보존','h2')
    text(f"원본 10월 14일 ZIP의 925개 해시를 먼저 확인했습니다. 새 후보에서도 실행 모델·전체 data/·가중 연구 자료 {prepared['immutable_candidate_files']:,}개 파일의 SHA-256이 같습니다. 기존 온도·결빙 예측을 바꾸는 재학습·임계값 변경 없이 설명과 재현 코드를 수정했습니다.")
    text('패키지 내부 실행','h2')
    for value in ['python code/predict.py --input data/weather_example.csv --output validation/new.csv',
                  'python -m src.submission_runtime --input data/weather_example.csv --models model --output validation/new_repo.csv',
                  'python code/reproduce_baselines.py --output validation/new_baselines.json']:
        text(html.escape(value),'small')
    text('원본 ZIP·신청서·인증정보·보호 및 개봉 평가 정답은 새 묶음에 포함하지 않습니다. 원본 작업 공간에서의 재생성은 repair_submission_candidate_20261016.py의 prepare/finalize 단계로 수행합니다.','small')
    flow.append(PageBreak())
    title('공식 정보와 적용한 참고 자료')
    text('10월 16일 공식 공개 응답 39개와 빈 참가양식 1개를 다시 확인했습니다. 공지 4건·문제 Q&A 6건·올해 일반 Q&A 17건의 본문, 문제·평가 설명과 참가양식 해시는 10월 14일 기록과 같았습니다. 새 결과물 제출 날짜·최종 CSV 규격 공지는 발견되지 않았습니다.')
    text('11월 6일은 참가신청 종료일입니다. 로그인한 참가 계정의 승인·제출 양식은 이번 공개 검토 범위에 포함하지 않았습니다. 코드 제출 의무와 대회 중 공개 허용은 구별하며, 제공 데이터의 제3자 제공 제한·종료 후 폐기 의무를 유지합니다.','small')
    text('문헌을 적용한 범위','h2')
    text('Lipton 등의 결과는 정보가 없는 분류기에서도 F1 최적화가 전부 양성을 택할 수 있음을 보여 줍니다. 이번 날짜·지점 집계에서 관측한 순위의 직접 증명으로 쓰지는 않았습니다. Reinke 등의 집계 함정 논의와 Saito·Rehmsmeier의 불균형 평가 논의에 따라 분모·지점별 혼동행렬·Precision/Recall을 함께 보였습니다.','small')
    for index,(label,url) in enumerate(SOURCES,1):
        flow.append(Paragraph(f'[{index}] <a href="{html.escape(url,quote=True)}" color="#225e85">{html.escape(label)}</a>',styles['small']))
        markdown.append(f'[{index}] [{label}]({url})')
    text('뒤의 12쪽은 10월 14일 분석 원문입니다. 수치·실험 당시 조건을 보존하며, 현재 성능과 재현 경로에 대한 판단은 앞의 추가 검증 및 최신 모델 카드를 따릅니다.','small')
    def footer(canvas,doc):
        canvas.setFont('Malgun',8);canvas.setFillColor(colors.HexColor('#5b6b76'))
        canvas.drawString(42,25,'2026-10-16 추가 검증 · 개발 성능 / 공식 점수 아님')
        canvas.drawRightString(A4[0]-42,25,f'{doc.page}/4')
    supplement=OUT/'supplement.pdf'
    SimpleDocTemplate(str(supplement),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=40,bottomMargin=42).build(flow,onFirstPage=footer,onLaterPages=footer)
    with fitz.open(supplement) as doc:assert len(doc)==4,len(doc)
    old=next((PRIVATE/'report_upgrade_20261014_v2').glob('*.pdf'))
    with fitz.open(supplement) as doc,fitz.open(old) as previous:
        assert len(previous)==12;doc.insert_pdf(previous,links=True);doc.save(OUT/'current_report.pdf')
    with fitz.open(OUT/'current_report.pdf') as doc:
        assert len(doc)==16
        for i,page in enumerate(doc):page.get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(OUT/'preview'/f'page_{i+1:02d}.png')
        content='\n'.join(p.get_text() for p in doc)
        assert '\ufffd' not in content
        for expected in ['0.071122','0.055216','0.030633','1.2004399739','1.2005309458']:
            assert expected in content,expected
    (OUT/'supplement.md').write_text('\n\n'.join(markdown)+'\n','utf-8')
    write(OUT/'report_receipt.json',dict(status='report_rendered_pending_visual_review',created_at_utc=datetime.now(timezone.utc).isoformat(),
        pdf_sha256=sha(OUT/'current_report.pdf'),pages=16,supplement_pages=4,preserved_analysis_pages=12,
        benchmark_summary_sha256=sha(BENCH/'summary.json'),prepare_receipt_sha256=sha(PRIVATE/'submission_candidate_20261016_v1/validation/review_20261016_prepare.json'),
        source_pdf_sha256=sha(old),official_receipt_sha256=sha(PRIVATE/'official_updates_20261016_v1/completion_receipt.json')))
    print('16-page current report rendered; visual inspection required.')


if __name__=='__main__':main()
