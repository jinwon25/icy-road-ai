"""Generate a full column dictionary from observed headers and quality counts."""
from pathlib import Path
import re
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_data import FIELDS, NONNUMERIC

IN = ROOT / "outputs" / "private" / "full"
inventory = pd.read_csv(IN / "file_inventory.csv")
quality = pd.read_csv(IN / "variable_quality.csv").set_index(["kind", "column"])
lines = ["# 변수 사전 및 품질 요약", "",
         "원본 CSV 첫 파일의 실제 열 이름을 기준으로 작성했다. 결측토큰과 숫자 오류는 개발용 RWIS 14개소, ASOS·AWS 전체 행에서 집계했다. 정적 메타데이터 열에는 동적 품질 통계를 적용하지 않았다.",
         "", "| 자료 | 원본 열 | 원본형 | 처리형 | 역할 | 표기 단위 | 분모 | 결측토큰 | 숫자 오류 |",
         "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |"]
for kind in ("RWIS", "ASOS", "AWS"):
    header = inventory.loc[inventory.kind == kind, "header"].iloc[0].split(" | ")
    time_col, id_col, name_col, lat_col, lon_col, route_col, _ = FIELDS[kind]
    for col in header:
        if col == time_col:
            role = "시각"
        elif col == id_col:
            role = "관측소 ID"
        elif col == name_col:
            role = "관측소명"
        elif col in (lat_col, lon_col):
            role = "좌표"
        elif col == route_col:
            role = "노선"
        elif col.startswith("Unnamed:") or not col:
            role = "원본 행 인덱스"
        elif col == "노면상태":
            role = "분류 정답"
        elif col in NONNUMERIC:
            role = "범주 입력"
        else:
            role = "수치 입력/추정 후보"
        found = re.search(r"\(([^)]*)\)\s*$", col)
        unit = found.group(1) if found else "미표기"
        if col == "노면온도 (광학)":
            unit = "미표기(광학 센서)"
        if col in (lat_col, lon_col):
            unit = "위경도(도)"
        if col == "노면상태":
            unit = "코드"
        if (kind, col) in quality.index:
            q = quality.loc[(kind, col)]
            n = str(int(q["total"]))
            missing = str(int(q["missing_tokens"]))
            invalid = "" if pd.isna(q.get("malformed_numeric")) else str(int(q["malformed_numeric"]))
        else:
            n = missing = invalid = ""
        parsed = ("datetime (KST provisional)" if col == time_col else "float64" if col in (lat_col, lon_col) else "string" if col in (id_col, name_col, route_col) or col in NONNUMERIC or col.startswith("Unnamed:") or not col else "float64 candidate")
        lines.append(f"| {kind} | {col or '(빈 열명)'} | string | {parsed} | {role} | {unit} | {n} | {missing} | {invalid} |")
    lines.append("")
lines += [
    "노면상태 코드의 원본 정의: 01 Dry, 02 Wet, 03 Snow, 04 Ice, 10 저시정, 11 노면 위 물 고임, 12 제빙제 사용으로 결빙 안 됨, 13 제빙제 사용으로 결빙 시작, 14 Damp, 15 물·얼음 판별 불가. 공식 설명에 따라 04만 Ice 양성으로 둔다. 13·15는 현재 잠정 음성이고, 빈 값·미정의 코드는 평가에서 제외한다.",
    "",
    "RWIS 시정은 m, ASOS 시정은 10m 표기다. ASOS 풍향은 16방위 표기와 수치 값의 관계가 미확인이다. RWIS 노면온도의 광학 표기는 센서 방식이며 온도 단위는 원본 헤더에 명시되지 않았다. 누적 강수량은 자정 초기화를 고려해야 한다.",
    "",
    "세부 오류 문자열과 건수는 Git에서 제외된 `outputs/private/full/variable_quality.csv`에 보존했다. 이 사전은 원본 값을 변경하지 않는다.",
]
(ROOT / "docs" / "VARIABLE_DICTIONARY.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
print("columns",sum(len(inventory.loc[inventory.kind == kind, "header"].iloc[0].split(" | ")) for kind in FIELDS))
