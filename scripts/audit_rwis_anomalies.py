"""별도 원문 집계로 결측·충돌·좌표 진단과 실제 CCTV 목록을 검산한다."""
from collections import Counter, defaultdict
from pathlib import Path
import csv
import re
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.blind_icing_validation import DEFAULT, read, write, verify, old_freezes, now


def main():
    out = ROOT / 'outputs/private/rwis_anomaly_diagnosis_20261025_v1'
    if (out / 'audit.json').exists():
        raise FileExistsError('Preserve completed audit')
    verify(DEFAULT)
    report = read(out / 'summary.json')
    per_day = defaultdict(Counter)
    states, fields, coordinates, invalid = Counter(), Counter(), Counter(), Counter()
    conflicts = []
    for name, digest in read(out / 'input_signatures.json').items():
        path = ROOT / name
        assert sha(path) == digest
        cols, rows = {}, []
        for line in path.read_text(encoding='utf-8').splitlines():
            match = re.match(r'#\s*(\d+)\.\s*(\w+)\s*:', line.strip())
            if match:
                cols[match[2]] = int(match[1])-1
            elif line.strip() and not line.lstrip().startswith('#'):
                rows.append(tuple(v.strip() for v in next(csv.reader([line]))))
        grouped = defaultdict(set)
        for row in rows:
            station, token = row[cols['STN_ID']], row[cols['TM']]
            assert station in {'12213', '33406'}
            if station == '12213':
                if token not in {'0', '-999', ''}:
                    coordinates[(row[cols['LAT']], row[cols['LON']])]+=1
            elif token in {'0', '-999', ''}:
                invalid[token]+=1
            else:
                grouped[token].add(row)
        for token, unique in grouped.items():
            if len(unique)>1:
                conflicts.append(token)
                states['|'.join(sorted({r[cols['SFS']] for r in unique}))]+=1
                fields.update(k for k,j in cols.items() if len({r[j] for r in unique})>1)
                category='conflict_quarantine'
            else:
                # 공식 코드표의 01–15와 결측을 별도로 대조한다. 상태를 복구하지 않는다.
                state=next(iter(unique))[cols['SFS']]
                category='valid_label' if state in {str(i) for i in range(1,16)} else 'invalid_state'
            if int(token[-2:])%10==0:
                per_day[token[:8]][category]+=1
    dates=pd.read_csv(out/'daily_quality.csv')
    for row in dates.itertuples():
        observed=per_day[row.date.replace('-','')]
        for key in ['valid_label','invalid_state','conflict_quarantine']:
            assert observed[key]==getattr(row,key), (row.date,key)
        assert 144-sum(observed.values())==row.timestamp_absent
    assert dict(states)==report['conflicting_minute_state_pairs']
    assert dict(fields)==report['differing_fields']
    assert dict(invalid)==report['invalid_timestamp_tokens']
    assert len(conflicts)==len(set(conflicts))==report['conflicting_minutes']
    assert min(conflicts)==report['first_conflict'] and max(conflicts)==report['last_conflict']
    assert [dict(lat=a,lon=b,minute_rows=n) for (a,b),n in coordinates.items()]==report['station_12213_response_coordinate_counts']
    context=ROOT/'outputs/private/rwis_anomaly_additional_sources_20261025_v1'
    cctv=pd.read_csv(context/'cctv_20260423.csv',encoding='cp949')
    assert sha(context/'cctv_20260423.csv')==read(context/'cctv_file_receipt.json')['sha256']
    assert len(cctv)==2999 and list(cctv)==['노선번호','노선명','CCTV명','이정','방향','설치목적','운영상태']
    matches=cctv.loc[cctv.CCTV명.str.contains('성암교|진천터널외부')]
    assert len(matches)==4
    assert sha(DEFAULT/'summary.json')==report['original_summary_sha256']
    verify(DEFAULT)
    assert old_freezes()==(47,549)
    write(out/'audit.json',dict(status='passed',at_utc=now(),source_files=report['source_files'],
        independently_counted_days=len(dates),conflicting_minutes=len(conflicts),
        cctv_rows=len(cctv),cctv_matches=matches.to_dict('records'),
        cctv_contains_coordinates=False,cctv_used_for_training=False,
        source_artifacts={p.relative_to(ROOT).as_posix():sha(p) for directory in [context,ROOT/'outputs/private/rwis_anomaly_sources_20261025_v1'] for p in directory.iterdir() if p.is_file()},
        summary_sha256=sha(out/'summary.json'),code_sha256=sha(Path(__file__)),
        original_blind_summary_sha256=sha(DEFAULT/'summary.json'),labels_or_scores_changed=False))
    print('AUDIT PASSED',report['source_files'],len(dates),len(conflicts),len(cctv),flush=True)


if __name__=='__main__':
    main()
