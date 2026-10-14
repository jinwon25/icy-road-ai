"""공식 후속 확인의 필요한 본문·개발 예측 스키마만 출력한다."""
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'outputs/private'


def main():
    out = PRIVATE / 'official_updates_20261013_v2'; old = PRIVATE / 'official_updates_20261013_v1'
    current = json.loads((out / 'problem_tabs.bin').read_bytes()); previous = json.loads((old / 'problem_tabs.bin').read_bytes())
    for new, prev in zip(current['overviewList'], previous['overviewList']):
        print('tab', new['title'], 'unchanged', new['content'] == prev['content'], 'modified', new.get('modifyDt'))
        body = re.sub(r'data:image/[^;,]+;base64,[A-Za-z0-9+/=]+', '[image]', new['content'])
        text = BeautifulSoup(body, 'html.parser').get_text(' ', strip=True)
        for needle in ['F1', 'Precision', 'Recall', '평가', '제출']:
            at = text.find(needle)
            print(needle, text[max(0, at-130):at+1400] if at >= 0 else 'not found')
    print('pledge byte equal', (out / 'current_application.hwp').read_bytes() == (old / 'current_application.hwp').read_bytes())
    for folder in ['weather_memory_controls_20261013_v1', 'weather_memory_temperature_20261013_v2', 'ice_methodology_20261010_v1']:
        for name in ['outer_predictions.parquet', 'ice_predictions.parquet', 'predictions.parquet']:
            path = PRIVATE / folder / name
            if path.exists(): print(folder, name, pq.read_metadata(path).num_rows, pq.read_schema(path).names)
    for name in ['overview', 'problem_page']:
        soup = BeautifulSoup((out / (name+'.html')).read_bytes(), 'html.parser')
        text = soup.get_text(' ', strip=True)
        for needle in ['문제해결', '평가 기준', '09.15', '11.06', '11-06', '제출']:
            at = text.find(needle)
            print(name, needle, text[max(0, at-120):at+800] if at >= 0 else 'not found')


if __name__ == '__main__': main()
