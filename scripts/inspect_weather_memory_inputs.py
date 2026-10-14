"""승인된 첫 겨울 개발 입력과 신규 문헌의 필요한 부분만 읽는다."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    d = pd.read_parquet(ROOT / 'outputs/private/weather_distance_20261010_v1/development_inputs.parquet')
    print('development:', len(d), sorted(d.station.unique()), d.time.min(), d.time.max())
    print('columns:', list(d.columns))
    print('history availability:', d[['asos_air_temp', 'aws_air_temp', 'aws_humidity', 'aws_dewpoint', 'aws_rain_15m', 'aws_wind_speed']].notna().mean().to_dict())
    refs = ROOT / 'outputs/private/weather_memory_references_20261013_v1'
    for name, needles in {
        'road_lstm_stacking2026': ['input configuration', 'lagged', 'Data availability', '2026', 'Received'],
        'spatial_local_quantile2026': ['Algorithm 1', 'exchangeab', 'mixing'],
        'interval_scoring2007': ['interval score', 'central prediction'],
        'official_submission_notice': ['제출 기간', '23:59'],
    }.items():
        path = refs / (name+'.txt')
        if path.exists():
            text = path.read_text('utf-8')
            for needle in needles:
                at = text.lower().find(needle.lower())
                print(name, needle, text[max(0, at-120):at+1800] if at >= 0 else 'not found')


if __name__ == '__main__':
    main()
