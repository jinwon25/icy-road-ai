"""공식 숨김 본문·Q&A 답변 상태와 접근 실패 문헌의 검토 범위를 기록한다."""
import json
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/private/ice_methodology_references_20261010_v1'


def main():
    target = OUT / 'official_inspection.json'
    if target.exists():
        raise FileExistsError('Preserve inspection receipt')
    board = BeautifulSoup((OUT / 'official_board.html').read_bytes(), 'html.parser')
    rows = []
    for row in board.select('tr'):
        anchors = row.select('a[href]')
        if any('fn_select_detail(' in a.get('href', '') for a in anchors):
            rows.append({'links': [a['href'] for a in anchors], 'cells': [td.get_text(' ', strip=True) for td in row.select('td')]})
    qa = [r for r in rows if any('fn_select_detail(633)' in a for a in r['links'])]
    assert len(qa) == 1 and qa[0]['cells'][4] == '-'
    bodies = {}
    for name in ['official_notice', 'official_qa633']:
        soup = BeautifulSoup((OUT / (name+'.html')).read_bytes(), 'html.parser')
        body = soup.find(id='nttCn'); assert body is not None
        text = str(body.get('value', body.get_text())); bodies[name] = {'characters': len(text), 'file': name+'_body.md'}
        (OUT / (name+'_body.md')).write_text(text, encoding='utf-8')
    receipts = json.loads((OUT / 'fetch_receipts.json').read_text('utf-8'))
    pledge = next(r for r in receipts if r['name'] == 'official_pledge')
    assert pledge['sha256'] == '3d85f7ac144266b67145cf69442542d9f57cfcc487340bfe558f6c21f3d03395'
    receipt = {'official_board_questions': len(rows), 'qa633': qa[0], 'qa633_answer_published': False,
               'official_bodies': bodies, 'pledge_identical_to_previously_reviewed_hwp': True,
               'successful_http': sum(r.get('status') == 200 for r in receipts), 'http_requests': len(receipts),
               'failed_sources': [{'name': r['name'], 'status': r.get('status'), 'error_type': r.get('error_type')} for r in receipts if r.get('status') != 200],
               'source_limit': 'AMS·MDPI 원문403. 검색 초록만으로 구현 세부·성능을 인용하지 않음. CatBoost Plain과 논문의 Ordered 모드를 구별함.',
               'decisions': ['공식04 정답 유지', '공식 일별 미정의 규격은 미확정으로 표기', '실행 버전·대안·실패·AI 검토를 보존', '코드 제출 의무를 대회 중 공개 허용으로 해석하지 않음']}
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
