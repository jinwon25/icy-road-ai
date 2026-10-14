"""공식 숨김 본문·서약 동일성·대체 논문 원문·실패 이력을 별도 보존한다."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from bs4 import BeautifulSoup
import fitz
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha


def main():
    folder = ROOT / 'outputs/private/method_blending_references_20261010_v1'
    result = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'official_bodies': {}}
    for name in ['official_problem', 'official_notice', 'official_qa633']:
        soup = BeautifulSoup((folder / (name+'.html')).read_bytes(), 'html.parser')
        node = soup.find('input', id='nttCn')
        if node is not None:
            body = node.get('value', '')
            target = folder / (name+'_body.txt')
            with target.open('x', encoding='utf-8') as f:
                f.write(body)
            result['official_bodies'][name] = {'sha256': sha(target), 'characters': len(body)}
    previous = ROOT / 'outputs/private/weather_network_review_20261010_v1/public_sources/pledge.hwp'
    result['official_pledge'] = {'file_format': 'HWP binary; previously read pledge retained', 'current_sha256': sha(folder / 'official_pledge.bin'),
                                'previous_sha256': sha(previous), 'identical_to_previously_reviewed_pledge': sha(previous) == sha(folder / 'official_pledge.bin')}
    soup = BeautifulSoup((folder / 'official_board.html').read_bytes(), 'html.parser')
    rows = [[c.get_text(' ', strip=True) for c in row.find_all('td')] for row in soup.find_all('tr')]
    matching = [r for r in rows if any('결빙 F1 평가 시' in v for v in r)]
    result['qa633'] = {'matched_board_rows': len(matching), 'answer_status': matching[0][-2] if len(matching) == 1 else None}
    url = 'https://www.wsl.ch/lud/biodiversity_events/papers/Roberts_et_al-2017-Ecography.pdf'
    response = requests.get(url, timeout=(10, 30))
    target = folder / 'spatial_cv2017_author_copy.pdf'; target.write_bytes(response.content)
    result['spatial_cv_author_copy'] = {'requested_url': url, 'status': response.status_code, 'bytes': len(response.content), 'sha256': sha(target)}
    if response.status_code == 200 and response.content.startswith(b'%PDF-'):
        pdf = fitz.open(target); result['spatial_cv_author_copy']['pages'] = len(pdf)
        (folder / 'spatial_cv2017_author_copy.txt').write_text('\n'.join(p.get_text() for p in pdf), encoding='utf-8')
        pdf[0].get_pixmap(matrix=fitz.Matrix(1.2, 1.2)).save(folder / 'spatial_cv2017_page1.png')
    receipt = folder / 'official_and_alternative_receipt.json'
    with receipt.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    # 실패한 계산을 삭제하거나 성공 기록으로 바꾸지 않는다.
    failures = [('method_blending_20261010_v1', '원본 소스 서명 검사 중단: 계산 중 shared module에 ice_guard 함수가 추가됨. v1은 미완료·미채택; 전체 v2 재실행.', 36),
                ('score_blending_20261010_v1', '기존 threshold_prediction은 fallback 행 점수도 유한 값이어야 함. NaN 점수 계약 오류로 결과 계산 전에 중단. 원본 유한 fallback 점수 유지 후 v2 재실행.', 0)]
    for name, reason, count in failures:
        target = ROOT / 'outputs/private' / name / 'run_failure_receipt.json'
        with target.open('x', encoding='utf-8') as f:
            json.dump({'status': 'failed_run_preserved', 'reason': reason, 'base_fit_calls_before_failure': count,
                       'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'not_validated_for_promotion': True}, f, indent=2, ensure_ascii=False)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
