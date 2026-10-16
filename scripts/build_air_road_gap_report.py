"""독립 검산을 통과한 결합·관측 공백 연구를 별도 4쪽 보고서로 만든다."""
from datetime import datetime, timezone
from pathlib import Path
import html
import sys
import fitz
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_method_blending import read, write
from src.data_source import sha256_file as sha

PRIVATE = ROOT / 'outputs/private'
OUT = PRIVATE / 'air_road_gap_report_20261016_v1'
RULES = PRIVATE / 'air_road_blending_20261016_v1'
GAPS = PRIVATE / 'asos_gap_fallback_20261016_v1'
SOURCES = [
    ('KISTI 대회 공지·공식 일정', 'https://aida.kisti.re.kr/competition/main/notice.do'),
    ('KISTI 일별 평가 답변 Q&A633', 'https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=633'),
    ('scikit-learn 1.6: 의사결정 임계값 조정', 'https://scikit-learn.org/1.6/modules/classification_threshold.html'),
    ('Lipton 등 (2014), Thresholding Classifiers to Maximize F1 Score', 'https://arxiv.org/abs/1402.1892'),
    ('Cawley·Talbot (2010), On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation', 'https://jmlr.org/papers/v11/cawley10a.html'),
    ('NWS: Freezing Fog', 'https://www.weather.gov/safety/fog-freezing'),
    ('FHWA: Road Weather Information Systems, Chapter 3', 'https://www.fhwa.dot.gov/publications/research/safety/95202/003.cfm'),
    ('FHWA: Environmental Sensor Station Siting Guidelines', 'https://ops.fhwa.dot.gov/publications/ess05/ess0503.htm'),
    ('기상청 API허브: ASOS 시간자료', 'https://apihub.kma.go.kr/apiList.do'),
    ('기상청 API허브: AWS 매분자료', 'https://apihub.kma.go.kr/apiList.do?seqApi=2&seqApiSub=239'),
]


def main():
    if OUT.exists():
        raise FileExistsError('Preserve completed followup report')
    evidence = [RULES / 'summary.json', RULES / 'independent_verification.json',
                GAPS / 'summary.json', GAPS / 'independent_verification.json',
                PRIVATE / 'weather_source_gap_audit_20261016_v1/receipt.json',
                PRIVATE / 'remaining_station_metadata_20261016_v1/receipt.json',
                PRIVATE / 'official_updates_20261016_v2/completion_receipt.json']
    rules, rule_audit, gaps, gap_audit, weather, metadata, official = map(read, evidence)
    assert rule_audit['summary_sha256'] == sha(evidence[0]) and gap_audit['summary_sha256'] == sha(evidence[2])
    assert rule_audit['status'] == 'independent_air_road_blending_audit_passed'
    assert gap_audit['status'] == 'independent_asos_gap_fallback_audit_passed'
    assert not official['changed_details'] and not official['changed_tabs'] and official['blank_application_unchanged']
    assert rules['model_promoted'] is False and gaps['all_station_quality_gates_passed'] is False
    assert metadata['eligible_under_previous_screen'] == 0
    OUT.mkdir()
    (OUT / 'preview').mkdir()
    pdfmetrics.registerFont(TTFont('Malgun', 'C:/Windows/Fonts/malgun.ttf'))
    pdfmetrics.registerFont(TTFont('MalgunBold', 'C:/Windows/Fonts/malgunbd.ttf'))
    styles = dict(
        title=ParagraphStyle('title', fontName='MalgunBold', fontSize=19, leading=27, textColor=colors.HexColor('#193b4a'), spaceAfter=14, wordWrap='CJK'),
        heading=ParagraphStyle('heading', fontName='MalgunBold', fontSize=11.3, leading=17, spaceBefore=11, spaceAfter=7, textColor=colors.HexColor('#193b4a')),
        body=ParagraphStyle('body', fontName='Malgun', fontSize=10, leading=16, spaceAfter=10, wordWrap='CJK'),
        small=ParagraphStyle('small', fontName='Malgun', fontSize=8.7, leading=13.5, spaceAfter=8, wordWrap='CJK'),
        cell=ParagraphStyle('cell', fontName='Malgun', fontSize=8.4, leading=12.8, wordWrap='CJK'))
    flow = []

    def text(value, kind='body'):
        flow.append(Paragraph(value, styles[kind]))

    def table(rows, widths):
        data = [[Paragraph(html.escape(str(v)), styles['cell']) for v in row] for row in rows]
        t = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5eff0')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, 0), .6, colors.HexColor('#3f7279')),
            ('LINEBELOW', (0, 1), (-1, -1), .25, colors.HexColor('#d7e1e3')),
            ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        flow.extend([t, Spacer(1, 10)])

    text('기온·노면 결합과 관측 공백\n후속 검증', 'title')
    text('2026년 10월 16일 / 반복 개발 검증 / 실행 후보 유지', 'small')
    text('72개 결합을 비교했지만 단순 ASOS 기온 규칙보다 높은 일별 F1을 얻지 못했습니다. 인접 관측소 대체도 9곳 중 2곳만 품질 조건을 통과했습니다. 개선이 확인되지 않은 판정을 제출 후보에 반영하지 않고, 원 관측의 결측과 새 독립 평가에 필요한 조건을 확인했습니다.')
    text('단순 기준선과 내부 선택 결과', 'heading')
    rows = [['방법', '일별 F1', 'FP', 'FN', '탐지 사건']]
    for name, label in [('current', '현재 온도·수분'), ('always_one', '항상 결빙'), ('road_zero', '추정 노면온도 ≤0°C'),
                        ('air_zero', 'ASOS 기온 ≤0°C'), ('nested_research', '내부 선택: 연구용'), ('nested_strict', '내부 선택: 엄격')]:
        r = rules['reports'][name]
        rows.append([label, f"{r['daily']['144']['f1_available_station_mean']:.6f}", f"{r['fp']:,}", f"{r['fn']:,}", f"{r['event']['detected']}/347"])
    table(rows, [165, 85, 85, 80, 92])
    text('외부 개발 9곳·첫 겨울의 상태 유효 155,118행. F1은 144유효슬롯을 갖춘 1,060개 지점일에서 날짜 평균 후 지점 평균입니다. 실제·예측 양성이 모두 없는 날은 제외돼 F1 날짜 수가 현재 365일, ASOS 786일, 항상 결빙 1,060일로 다릅니다. FP·FN·사건은 부분 날짜를 포함합니다. 144슬롯은 잠정 조건이며 130·72·1슬롯도 별도 확인했습니다.', 'small')
    text('ASOS 규칙은 현재 대비 미탐 4,141행을 줄이지만 오경보가 37,657행 늘어납니다. 온도 MAE 개선과 결빙 탐지의 우수성을 구별하며, F1만으로 실행 후보를 변경하지 않았습니다. Ice 6,611행 중 95.9%가 33408에 집중된 한계도 남습니다.', 'small')
    text('실행 모델 재학습 0건 / 보호·개봉 평가 정답 재열람 0건 / 새 독립 성능 입증 아님', 'small')
    flow.append(PageBreak())

    text('72개 결합의 설계와 독립 검산', 'title')
    table([['요소', '고정한 조건'], ['저온 입력 2종', 'ASOS 기온 / ASOS와 추정 노면온도의 반반 평균'],
           ['임계값 3종', '-2, -1, 0°C'], ['수분 3종', '없음 / AWS 습도 ≥80% / 기온·이슬점 차 ≤2°C 또는 강수·적설'],
           ['지속 2종', '1슬롯 / 과거 포함 연속 3슬롯, 관측 공백 시 초기화'],
           ['현재 판정 2종', '독립 규칙 / 현재 온도·수분 후보와 OR']], [115, 392])
    text('평가 그룹을 온도 학습과 규칙 선택에서 제외', 'heading')
    text('네 외부 그룹 G마다 나머지 세 그룹으로 규칙을 고릅니다. 내부 H의 온도는 G와 H 전체 지점을 학습하지 않은 기존 모델로 계산했습니다. 최종 외부 비교는 G 제외 모델을 사용했습니다. 20개 저장 모델을 재사용했고 새 적합은 하지 않았습니다.')
    table([['선택 기준', '적격 조건 / 실패 시 복귀'],
           ['연구용 F1', '144·1슬롯 F1이 현재·ASOS·항상 결빙을 모두 초과, FP≤ASOS, 기존 탐지 사건 손실 0, 지점별 TP 보존 / ASOS'],
           ['기존 엄격 기준', '위 F1 우위에 현재 대비 FP·FN 비증가, 일별 P·R·F1 비악화, 사건·지점 TP 보존 / 현재 후보']], [115, 392])
    text('네 그룹 모두 두 경로에서 적격 규칙이 없었습니다. 전체 개발 결과를 본 최고 고정 규칙도 수분·지속·OR가 없는 ASOS ≤0°C 자체였습니다. 이 최고값을 새 지점 성능으로 소개하지 않습니다. 자체 습도·거리 임계값은 문헌의 보장값이 아닙니다.', 'small')
    text('별도 구현으로 확인한 범위', 'heading')
    text('규칙 예측 44,714,016값 · 저장 온도 1,242,056값 · 지표 보고서 788개 · 사건 보고서 387개 · 외부 선택 4개 · 일별 30,240행과 지점 252행. 시간창은 시간 인덱스 기반 구현으로, 지표는 기존 일별 집계로, 사건은 별도 그룹 집계로 대조했습니다.', 'small')
    text('근거: air_road_blending_20261016_v1의 실험 계획·요약·independent_verification.json. 모두 outputs/private 아래 보존합니다. 이번 72개 안에서의 실패를 모든 결합 방법의 실패로 확대하지 않습니다.', 'small')
    flow.append(PageBreak())

    text('관측 공백: 채우기와 정확도는 별개', 'title')
    text('최근접 ASOS를 제외하는 합성 공백 648행을 사전에 고정했습니다. 50km 이내·추가 거리 30km 이내·엄격히 과거 60분 이내 관측을 사용했습니다. 지점별 대체율 ≥50%, 온도 비교 ≥36행, MAE 악화 ≤10%, 평균 온도 변화 ≤0.75°C를 모두 요구했습니다.', 'small')
    rows = [['지점', '대체 가능/72', '원 입력 MAE', '대체 MAE', '품질 통과']]
    for r in gaps['masked_station_results']:
        fmt = lambda v: '-' if v is None else f'{v:.4f}'
        rows.append([r['station'], r['available_fallback_rows'], fmt(r['original_mae']), fmt(r['fallback_mae']), '예' if r['quality_passed'] else '아니요'])
    table(rows, [75, 112, 112, 112, 96])
    text('보호 공백 18행 중 12행에 참고 온도·결빙 판정을 만들 수 있었으나 전체 지점 품질 기준은 실패했습니다. 정식 출력은 18행 null을 유지합니다. 행별 ASOS 선택 666건·온도 1,296값·참고 출력 18행을 별도 검산했습니다.', 'small')
    text('공식 원 관측 7회 조회로 확인', 'heading')
    table([['대상', '확인한 결과'], ['부안 2026-02-11 13:00', 'HTTP 200이지만 관측 행 없음. 직전 정상 시각은 기존 캐시와 일치.'],
           ['장수 2025-12-19 14:00', 'TA=-99.0 결측. 같은 시각 캐시도 결측이며 원 기온 복구 불가.'],
           ['겨울 시작 직전 6건', '원 ASOS 기온 확보. AWS·적설 입력 근거는 없어 완전 복구로 채택하지 않음.'],
           ['AWS 매분자료', '기존 키로 다시 HTTP 403. 원문·인증 제외 요청 정보만 보존.']], [155, 352])
    text('음수 적설 결측은 0으로 바꾸지 않습니다. 실제 -9°C는 유효 기온입니다. ASOS 단독으로 AWS 없는 입력의 정확도가 확인된 것은 아닙니다. 보호 도로 정답·외부 예측 서비스는 사용하지 않았습니다.', 'small')
    flow.append(PageBreak())

    text('공식 현황과 다음 검증 조건', 'title')
    text('10월 16일 오전 10시 38분, 공개 응답 39개와 빈 참가양식을 같은 날 오전 기록과 다시 대조했습니다. 새 글·답변·문제 탭·양식 변경은 없었습니다. 공지 4건, 문제 Q&A 6건, 올해 일반 Q&A 17건을 확인했습니다. 결과물 제출 날짜와 문제별 최종 CSV 규격은 추가 공지를 발견하지 못했습니다. 11월 6일은 참가신청 종료일입니다.', 'small')
    text('다음 성능 개선은 새 근거를 먼저 확보', 'heading')
    text('기존 위치 선별표의 미조회 후보 30곳 중 현재 캐시 거리 조건 안에는 12208만 남습니다. 기존 센서와 약 11m 떨어져 5km 분리 기준에 미달합니다. 현재 캐시와 기존 선별 기준에서 새 적격 독립 지점은 0곳이며, 전국 관측소 전체의 부재를 뜻하지 않습니다.', 'small')
    text('① AWS 접근과 새 지역 기상 가용성을 정답 없이 확인 → ② 후보·예측을 봉인한 뒤 새 지점 한 번 개봉 → ③ 33408 센서·제설·염분·유지보수 이력 대조 → ④ 공식 CSV·결측·일정 공지 반영. 이미 개봉한 지점을 새 독립 평가로 재사용하지 않습니다.', 'small')
    text('참고 자료와 적용 범위', 'heading')
    text('임계값·F1·선택 편향 문헌은 기준선과 내부 선택 분리에 적용했습니다. NWS·FHWA 자료는 수분·노면온도·관측소 대표성의 물리적 동기로 사용했습니다. 논문이 자체 임계값이나 새 지점 성능을 보장한다고 해석하지 않았습니다. 기상청 명세는 KST·ID·기온·적설 단위 대조에 적용했습니다.', 'small')
    for number, (label, url) in enumerate(SOURCES, 1):
        text(f'[{number}] <a href="{html.escape(url, quote=True)}" color="#245f79">{html.escape(label)}</a>', 'small')
    text('기존 실행 ZIP·모델·정식 예측과 47개·예약 549개 고정 파일 및 세 평가 봉인을 유지했습니다. 이 문서는 현재 16쪽 제출 기술 보고서와 구별하는 후속 연구 기록입니다. 공식 점수·수상 가능성·제출 완료를 입증하지 않습니다.', 'small')

    def footer(canvas, doc):
        canvas.setFillColor(colors.HexColor('#5d727a'))
        canvas.setFont('Malgun', 8)
        canvas.drawString(42, 25, '2026-10-16 후속 검증 / 반복 개발 결과 / 공식 점수 아님')
        canvas.drawRightString(A4[0]-42, 25, f'{doc.page}/4')

    path = OUT / 'followup_report.pdf'
    SimpleDocTemplate(str(path), pagesize=A4, rightMargin=42, leftMargin=42, topMargin=38, bottomMargin=44).build(flow, onFirstPage=footer, onLaterPages=footer)
    with fitz.open(path) as doc:
        assert len(doc) == 4, len(doc)
        content = '\n'.join(p.get_text() for p in doc)
        assert '\ufffd' not in content
        for value in ['0.030633', '0.071122', '44,714,016', '1,242,056', '403', '648']:
            assert value in content, value
        for i, page in enumerate(doc):
            page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4)).save(OUT / 'preview' / f'page_{i+1:02d}.png')
        links = sum(len(p.get_links()) for p in doc)
    write(OUT / 'report_receipt.json', dict(status='rendered_pending_visual_review', created_at_utc=datetime.now(timezone.utc).isoformat(),
          pages=4, pdf_sha256=sha(path), link_annotations=links,
          evidence_signatures={str(p.relative_to(ROOT)): sha(p) for p in evidence},
          source_sha256=sha(Path(__file__)), execution_candidate_changed=False))
    print(dict(status='four_page_report_rendered', path=str(path), visual_review_required=True), flush=True)


if __name__ == '__main__':
    main()
