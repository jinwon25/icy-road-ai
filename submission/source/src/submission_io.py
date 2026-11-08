"""트리 경계의 입력 부동소수점 값을 보존하는 CSV/Parquet 읽기."""
from pathlib import Path
import pandas as pd


def read_weather(path):
    path=Path(path)
    if path.suffix.lower()=='.parquet':return pd.read_parquet(path)
    # 기본 C파서의 마지막 비트 차이가 트리 경계에서 다른 분기로 이어질 수 있다.
    return pd.read_csv(path,dtype={'station':str},float_precision='round_trip')
