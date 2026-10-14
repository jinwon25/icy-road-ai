"""접근 실패한 도로 논문의 NOAA 보관 원문과 도로관리 기관 사례를 확인한다."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.research_ice_methodology import OUT, fetch

SOURCES = {
    'road_nowcast2023_noaa': 'https://repository.library.noaa.gov/view/noaa/56154/noaa_56154_DS1.pdf',
    'fhwa_anti_icing': 'https://www.fhwa.dot.gov/reports/mopeap/mop0296a.htm',
    'fhwa_rwis': 'https://ops.fhwa.dot.gov/weather/faq.htm',
    'nssl_hazards': 'https://inside.nssl.noaa.gov/nsslnews/2021/03/researchers-developing-experimental-winter-forecasting-tools/'
}


def main():
    target = OUT / 'practice_fetch_receipts.json'
    if target.exists() or any((OUT / (name+ext)).exists() for name in SOURCES for ext in ['.pdf', '.html', '.bin']):
        raise FileExistsError('Preserve supplement')
    with ThreadPoolExecutor(max_workers=3) as pool:
        receipts = list(pool.map(fetch, SOURCES.items()))
    target.write_text(json.dumps(receipts, ensure_ascii=False, indent=2), encoding='utf-8')
    pdf = OUT / 'road_nowcast2023_noaa.pdf'
    if pdf.exists():
        doc = fitz.open(pdf)
        for page in (0, 4):
            doc[page].get_pixmap(matrix=fitz.Matrix(1.2, 1.2)).save(OUT / f'road_nowcast_page{page+1}.png')


if __name__ == '__main__':
    main()
