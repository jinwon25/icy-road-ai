"""배포본의 열 추가·파일명 대소문자·목표안개 자료를 구별하는 원본 로더."""
from __future__ import annotations

import re

import pandas as pd


MISSING_NUMBERS = frozenset((-999.0, -99.9, -99.2, -99.7))


def daily_kind(name: str) -> str | None:
    match = re.search(r"Jeonbuk_(RWIS|ASOS|AWS)_daily_", name, re.IGNORECASE)
    if not match:
        return None
    kind = match.group(1).upper()
    # 목표안개와 결빙 관측 파일의 basename이 같으므로 디렉터리도 구별한다.
    if kind == "RWIS" and any(p.startswith("1-1.") for p in name.replace("\\", "/").split("/")):
        return "FOG"
    return kind


def daily_members(archive, kind: str) -> list[str]:
    names = sorted(n for n in archive.namelist() if daily_kind(n) == kind)
    if not names:
        raise ValueError(f"No daily files for {kind}")
    return names


def read_columns(archive, name: str, columns: list[str], names: list[str]) -> pd.DataFrame:
    if len(columns) != len(names):
        raise ValueError("Source and destination column counts differ")
    with archive.open(name) as stream:
        frame = pd.read_csv(stream, usecols=columns, dtype=str, encoding="utf-8-sig",
                            keep_default_na=False)
    # pandas usecols는 요청 순서가 아닌 파일의 열 순서를 반환한다.
    frame = frame.loc[:, columns].copy()
    frame.columns = names
    return frame


def numeric_observations(values: pd.Series) -> pd.Series:
    """10월 7일 공식 결측 코드를 NaN으로 바꾼다. 실제 음의 기온은 보존한다."""
    numbers = pd.to_numeric(values, errors="coerce")
    return numbers.mask(numbers.isin(MISSING_NUMBERS) | numbers.isin([float("inf"), -float("inf")]))
