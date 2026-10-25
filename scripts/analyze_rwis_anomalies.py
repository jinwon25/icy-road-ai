"""완료 평가를 바꾸지 않고 33406 원문 공백 원인과 12213 위치 출처를 대조한다."""
from pathlib import Path
from collections import Counter
import sys
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.rwis_forensics import response_profile,tokens
from src.data_source import sha256_file as sha
from scripts.blind_icing_validation import DEFAULT,read,write,verify,now


def main():
    out=ROOT/'outputs/private/rwis_anomaly_diagnosis_20261025_v1'
    if out.exists():raise FileExistsError('Preserve diagnosis')
    verify(DEFAULT);manifest=read(DEFAULT/'download_manifest.json');summary_sha=sha(DEFAULT/'summary.json')
    dates=[];pairs=Counter();fields=Counter();invalid_tokens=Counter();conflicts=[];coordinates=Counter();inputs={}
    for identifier,record in sorted(manifest['records'].items()):
        if record['station'] not in {'12213','33406'}:continue
        station=record['station'];all_ten={};raw_invalid=0;raw_count=0
        for transport in record['transport']:
            original=DEFAULT/'transport'/transport['transport_cache_path']
            assert sha(original)==transport['transport_response_sha256']
            if 'quality_receipt' in transport:
                side=DEFAULT/transport['quality_receipt'];assert sha(side)==transport['quality_receipt_sha256']
                receipt=read(side);original=DEFAULT/receipt['raw_path'];assert sha(original)==receipt['raw_sha256']
            inputs[original.relative_to(ROOT).as_posix()]=sha(original)
            body=original.read_text(encoding='utf-8');cols,rows=tokens(body,station)
            profile=response_profile(body,station,transport['start_kst'],transport['end_kst'])
            if station=='12213':
                for row in rows:
                    if row[cols.index('TM')] not in {'0','-999',''}:
                        coordinates[(row[cols.index('LAT')],row[cols.index('LON')])]+=1
                continue
            assert not set(all_ten)&set(profile['ten_minute_categories'])
            all_ten.update(profile['ten_minute_categories']);pairs.update(profile['conflicting_state_pairs']);fields.update(profile['differing_fields'])
            invalid_tokens.update(profile['invalid_timestamp_tokens']);raw_invalid+=sum(profile['invalid_timestamp_tokens'].values());raw_count+=profile['raw_rows']
            conflicts.extend(profile['conflict_tokens'])
        if station!='33406':continue
        index=pd.date_range(record['start_kst'],record['end_kst'],freq='10min')
        counts=Counter(all_ten.get(t.strftime('%Y%m%d%H%M'),'timestamp_absent') for t in index)
        stored=pd.read_parquet(DEFAULT/'observations'/(identifier+'.parquet'))
        assert counts['valid_label']==int(stored.ice.isin([0,1]).sum())
        assert counts['invalid_state']==int((~stored.ice.isin([0,1])).sum())
        assert sum(counts.values())==144
        dates.append(dict(date=record['start_kst'][:10],**{k:counts[k] for k in ['valid_label','invalid_state','conflict_quarantine','timestamp_absent']},
            raw_invalid_timestamps=raw_invalid,raw_rows=raw_count))
    d=pd.DataFrame(dates);assert len(d)==240 and len(conflicts)==len(set(conflicts))
    # 각 날짜의 원문 분류 합계와 이미 봉인된 평가 결측 수를 별도로 대조한다.
    f=pd.read_parquet(DEFAULT/'evaluation.parquet');f=f.loc[f.station.eq('33406')]
    totals={k:int(d[k].sum()) for k in ['valid_label','invalid_state','conflict_quarantine','timestamp_absent']}
    assert totals['valid_label']==int(f.ice.isin([0,1]).sum())
    assert totals['conflict_quarantine']+totals['timestamp_absent']==int(f._merge.eq('left_only').sum())
    out.mkdir(parents=True);d.to_csv(out/'daily_quality.csv',index=False)
    write(out/'input_signatures.json',inputs)
    reprobe=ROOT/'outputs/private/rwis_anomaly_reprobe_20261025_v1/receipt.json'
    write(out/'summary.json',dict(status='raw_anomalies_diagnosed_without_score_changes',at_utc=now(),source_files=len(inputs),
        station_33406_totals=totals,invalid_timestamp_tokens=dict(invalid_tokens),conflicting_minute_state_pairs=dict(pairs),
        differing_fields=dict(fields),conflicting_minutes=len(conflicts),first_conflict=min(conflicts),last_conflict=max(conflicts),
        station_12213_response_coordinate_counts=[dict(lat=a,lon=b,minute_rows=n) for (a,b),n in coordinates.items()],
        timestamp_missing_dates=d.loc[d.timestamp_absent.gt(0),['date','timestamp_absent','raw_invalid_timestamps']].to_dict('records'),
        original_summary_sha256=summary_sha,reprobe_sha256=sha(reprobe),source_sha256=sha(Path(__file__)),
        module_sha256=sha(ROOT/'src/rwis_forensics.py'),labels_or_scores_changed=False,
        cause_attribution='Upstream response anomalies reproduced. Sensor hardware, logger, aggregation and server root cause remain unconfirmed.'))
    assert sha(DEFAULT/'summary.json')==summary_sha;verify(DEFAULT)
    print((out/'summary.json').read_text(encoding='utf-8'),flush=True)


if __name__=='__main__':main()
