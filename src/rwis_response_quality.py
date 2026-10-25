"""동일 원문 중복만 합치고 충돌 관측은 값·예측과 무관하게 전부 격리한다."""
from collections import defaultdict
import csv
import re
from src.validation import canonical_station_id,PROTECTED_STATIONS


def quarantine_duplicates(body,station):
    station=canonical_station_id(station)
    if station in PROTECTED_STATIONS:raise ValueError('Protected response is forbidden')
    lines=body.splitlines();schema=[];rows=[]
    for i,line in enumerate(lines):
        if line.lstrip().startswith('#'):
            m=re.match(r'#\s*(\d+)\.\s*(\w+)\s*:',line.strip())
            if m:schema.append((int(m[1]),m[2]))
        elif line.strip():rows.append((i,tuple(x.strip() for x in (next(csv.reader([line])) if ',' in line else line.split()))))
    schema.sort();cols=[name for _,name in schema]
    if not {'TM','STN_ID','LAT','LON','HT','SFS','TR1'}<=set(cols) or len(cols)!=len(set(cols)) or [i for i,_ in schema]!=list(range(1,len(schema)+1)):
        raise ValueError('Invalid observation schema')
    if any(len(r)!=len(cols) for _,r in rows):raise ValueError('Unexpected observation field count')
    si,ti=cols.index('STN_ID'),cols.index('TM');groups=defaultdict(list)
    for i,row in rows:
        if canonical_station_id(row[si])!=station:raise ValueError('Unrequested station')
        # 시각 미정의 행은 기존 파서의 별도 격리 규칙에 맡겨 그 개수도 보존한다.
        if row[ti] not in ['', '0','-999']:groups[row[ti]].append((i,row))
    removed=set();identical=0;conflicts=[]
    for moment,group in groups.items():
        if len(group)==1:continue
        distinct={r for _,r in group}
        if len(distinct)==1:
            removed.update(i for i,_ in group[1:]);identical+=len(group)-1
        else:
            removed.update(i for i,_ in group)
            conflicts.append(dict(station=station,time=moment,rows=len(group),differing_fields=[cols[j] for j in range(len(cols)) if len({r[j] for _,r in group})>1]))
    report=dict(raw_rows=len(rows),identical_duplicate_rows_removed=identical,conflicting_keys=len(conflicts),
                conflicting_rows_removed=sum(x['rows'] for x in conflicts),remaining_rows=len(rows)-len(removed),conflicts=conflicts)
    cleaned='\n'.join(line for i,line in enumerate(lines) if i not in removed)+'\n' if removed else body
    return cleaned,report
