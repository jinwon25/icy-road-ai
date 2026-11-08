"""노면 정답 없이 23도로·34AWS의 연결, 16예시, 두 겨울 입력 품질을 묶는다."""
from pathlib import Path
import argparse
import json
import shutil
import sys

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,verify_preserved,now
from src.data_source import sha256_file as sha
from src.weather_network import WeatherNetwork,FIELDS
from scripts.evaluate_weather_network_20261101 import network_sources

LABELS={'competition':'대회 학습 지점','honam_baekyang':'호남 백양','seohaean_seocheon':'서해안 서천',
        'tongyeong_geumsan':'통영대전 금산','tongyeong_seosang':'통영대전 서상'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/private/weather_network_viewer_20261101_v1')
    out=parser.parse_args().output.resolve()
    if out.exists():raise FileExistsError('Preserve previous network viewer')
    plan=read(ROOT/'config/weather_network_20261101.json');study=ROOT/plan['output']
    frozen=read(study/'plan.json');receipt=read(study/'network_receipt.json')
    assert sha(study/'network_features.parquet')==receipt['feature_sha256']
    for path,digest in frozen['signatures'].items():assert sha(ROOT/path)==digest,path
    original=verify_preserved()
    f=pd.read_parquet(ROOT/plan['input'],columns=['station','time','group',*['aws_'+k for k in FIELDS]])
    assert not set(f.station)&set(plan['blocked_stations'])
    aws,coordinates,targets=network_sources(plan);builder=WeatherNetwork(aws,coordinates,**plan['network'])
    times=pd.DatetimeIndex([pd.Timestamp(year+(month<3),month,15,hour) for year in [2024,2025]
        for month in [11,12,1,2] for hour in [6,14]]).sort_values()
    snapshots=[];target_rows=[];proof=0
    cached=pd.read_parquet(study/'network_features.parquet');lookup=f.set_index(['station','time'])
    for station,q in f.groupby('station',sort=True):
        lat,lon=targets.loc[station];group=q.group.iloc[0]
        target_rows.append(dict(station=station,lat=float(lat),lon=float(lon),group_label=LABELS[group]))
        current=lookup.loc[[(station,t) for t in times]].reset_index()
        features,mapping=builder.build(times,lat,lon,current)
        idx=pd.MultiIndex.from_frame(f[['station','time']]).get_indexer(pd.MultiIndex.from_frame(current[['station','time']]))
        assert (idx>=0).all()
        np.testing.assert_array_equal(features.to_numpy(),cached.loc[idx].to_numpy());proof+=features.size
        for candidate in mapping['candidates']:
            sid=candidate['station'];source=aws.loc[aws.station.eq(sid),['source_time',*FIELDS]].sort_values('source_time')
            selected=pd.merge_asof(pd.DataFrame({'time':times}),source,left_on='time',right_on='source_time',
                direction='backward',allow_exact_matches=False,tolerance=pd.Timedelta(minutes=15))
            selected['age_minutes']=(selected.time-selected.source_time).dt.total_seconds()/60
            for row in selected.to_dict('records'):
                snapshots.append(dict(target=station,time=row['time'].strftime('%Y-%m-%d %H:%M'),aws=sid,
                    distance_km=candidate['distance_km'],source_time=None if pd.isna(row['source_time']) else row['source_time'].strftime('%Y-%m-%d %H:%M'),
                    age_minutes=None if pd.isna(row['age_minutes']) else float(row['age_minutes']),
                    **{k:None if pd.isna(row[k]) else float(row[k]) for k in FIELDS}))
    source_rows=[dict(station=s,lat=float(r.lat),lon=float(r.lon)) for s,r in coordinates.iterrows()]
    all_locations=target_rows+source_rows
    bounds={k:float(v) for k,v in dict(x0=min(p['lon'] for p in all_locations)-.05,x1=max(p['lon'] for p in all_locations)+.05,
        y0=min(p['lat'] for p in all_locations)-.05,y1=max(p['lat'] for p in all_locations)+.05).items()}
    quality=pd.read_csv(study/'network_quality.csv',dtype={'station':str})
    payload=dict(targets=target_rows,aws=source_rows,times=[t.strftime('%Y-%m-%d %H:%M') for t in times],
        snapshots=snapshots,quality=json.loads(quality.to_json(orient='records',double_precision=15)),bounds=bounds)
    template=ROOT/'src/templates/weather_network_audit.html';html=template.read_text('utf8')
    assert html.count('__PAYLOAD__')==1
    encoded=json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('<','\\u003c')
    out.mkdir();(out/'index.html').write_text(html.replace('__PAYLOAD__',encoded),'utf8')
    pd.DataFrame(snapshots).to_csv(out/'snapshot_sources.csv',index=False,encoding='utf-8-sig')
    shutil.copy2(study/'network_quality.csv',out/'network_quality.csv')
    assert verify_preserved()==original
    write(out/'summary.json',dict(status='network_viewer_created_pending_browser_review',at_utc=now(),
        targets=len(target_rows),aws_stations=len(source_rows),snapshot_times=len(times),snapshot_rows=len(snapshots),
        cached_feature_values_exact=proof,template_sha256=sha(template),source_plan_sha256=sha(study/'plan.json'),
        input_quality_sha256=sha(study/'network_quality.csv'),raw_targets_read=False,protected_outcomes_read=False,
        files={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print('VIEWER',out,'targets',len(target_rows),'sources',len(source_rows),'snapshot rows',len(snapshots),'exact',proof,flush=True)


if __name__=='__main__':main()
