"""검산된 기상 요약의 두 겨울 지도·시계열·CSV를 단일 오프라인 HTML로 묶는다."""
import argparse
import base64
import gzip
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'outputs/private/weather_history_segment_projection_20261101_v1')
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/private/weather_explorer_20261101_v1')
    args=parser.parse_args();source=args.source.resolve();out=args.output.resolve()
    if out.exists():raise FileExistsError('Preserve weather explorer')
    assert out.is_relative_to((ROOT/'outputs/private').resolve()) and out.parent==source.parent
    read=lambda p:json.loads(p.read_text(encoding='utf8'))
    summary=read(source/'summary.json');audit=read(source/'independent_verification.json')
    assert audit['status']=='passed' and audit['summary_sha256']==sha(source/'summary.json')
    for name in ['weather_segments_500m.csv','weather_segment_daily.csv.gz']:
        assert sha(source/name)==summary['files'][name]
    geometry=ROOT/'outputs/private/official_inventory_viewer_20261031_v1/viewer_data.json';shape=read(geometry)
    old={r['seg_id']:r for r in shape['rows']}
    winter=pd.read_csv(source/'weather_segments_500m.csv',float_precision='round_trip')
    daily=pd.read_csv(source/'weather_segment_daily.csv.gz',float_precision='round_trip',parse_dates=['date'])
    assert len(winter)==1686 and len(daily)==202320 and winter.seg_id.nunique()==843
    daily=daily.sort_values(['seg_id','date']);assert not daily.duplicated(['seg_id','date']).any()
    assert set(old)==set(winter.seg_id)
    expected=pd.date_range('2024-11-01','2025-02-28').append(pd.date_range('2025-11-01','2026-02-28'))
    fields=['air_temperature_mean','relative_humidity_mean','wind_speed_mean']
    counts=['air_temperature_valid_slots','relative_humidity_valid_slots','wind_speed_valid_slots']
    daily_fields=[*fields,*counts,'humidity_history_outside_slots','humidity_history_partial_slots']
    rows=[]
    for identifier,days in daily.groupby('seg_id',sort=True):
        np.testing.assert_array_equal(days.date.to_numpy(),expected.to_numpy())
        geometry_row=old[identifier];w=winter.loc[winter.seg_id.eq(identifier)].sort_values('winter')
        assert len(w)==2 and list(w.winter)==[2024,2025]
        assert list(w.route_nm)==[geometry_row['route_nm']]*2 and list(w.flow_lbl)==[geometry_row['flow_lbl']]*2
        records=[]
        for _,record in w.iterrows():
            assert record.planned_slots==17280
            records.append(dict(mean=[None if pd.isna(record[c]) else float(record[c]) for c in fields],
                coverage=[float(record[c]/17280) for c in counts],outside=float(record.humidity_history_outside_fraction),partial=float(record.humidity_history_partial_fraction)))
        values=days[daily_fields].round(6).astype(object).where(pd.notna(days[daily_fields]),None).values.tolist()
        rows.append(dict(id=identifier,route=geometry_row['route_nm'],flow=geometry_row['flow_lbl'],
            path=geometry_row['path'],cx=geometry_row['cx'],cy=geometry_row['cy'],
            unknown=bool(w.new_asos_source_domain.any()),w=records,days=values))
    ranges=[]
    for index in range(5):
        v=[(r['w'][w]['mean'][index] if index<3 else 100*r['w'][w]['outside' if index==3 else 'partial']) for r in rows for w in [0,1]]
        v=[x for x in v if x is not None];ranges.append([min(v),max(v)])
    wind_network=summary.get('status')=='wind_network_segment_projection_complete'
    note=('풍속은 69특성 주변 AWS 관측망 모형의 11월 2일 구간 추정입니다. '
          '기온·v10 습도·노면온도·결빙은 기존 결과를 보존합니다. '
          '풍속 입력 범위 이탈 등 추가 진단은 전체 CSV·GIS에 포함됩니다. '
          '구간별 실측 오차를 새로 평가한 자료는 아닙니다.' if wind_network else
          '현재 습도는 v10 과거 기상 이력 모형, 기온·풍속은 기존 채택 모형입니다. 구간별 관측 정확도를 새로 측정한 자료는 아닙니다.')
    payload=dict(rows=rows,box=shape['box'],boundary=shape['boundary'],ranges=ranges,model_note=note)
    encoded=json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')
    compressed=gzip.compress(encoded,compresslevel=9,mtime=0)
    template=ROOT/'src/templates/weather_explorer.html'
    html=template.read_text(encoding='utf8').replace('__PAYLOAD__',base64.b64encode(compressed).decode('ascii')).replace('__SOURCE__',source.name)
    assert '__PAYLOAD__' not in html and '__SOURCE__' not in html
    out.mkdir();(out/'viewer_data.json.gz').write_bytes(compressed);(out/'index.html').write_text(html,encoding='utf8')
    receipt=dict(status='weather_explorer_built_pending_browser_review',segments=len(rows),winter_rows=len(winter),daily_rows=len(daily),
        source=source.relative_to(ROOT).as_posix(),source_summary_sha256=sha(source/'summary.json'),
        source_audit_sha256=sha(source/'independent_verification.json'),geometry_sha256=sha(geometry),
        source_data_sha256={name:summary['files'][name] for name in ['weather_segments_500m.csv','weather_segment_daily.csv.gz','weather_segments.gpkg']},
        template_sha256=sha(template),builder_sha256=sha(Path(__file__)),display_daily_decimal_places=6,
        files={p.name:sha(p) for p in out.iterdir() if p.is_file()},external_dependencies=False,
        production_model_changed=False,wind_network_projection=wind_network,
        applied_wind_model_sha256=summary.get('applied_wind_model_sha256'))
    (out/'summary.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('WEATHER EXPLORER BUILT',len(encoded),len(compressed),len(rows),flush=True)


if __name__=='__main__':main()
