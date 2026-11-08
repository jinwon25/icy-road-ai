"""공식 암거 원문 CSV·DBF·SHP 좌표를 교차검산하고 이정 연결 후보를 보존한다."""
import csv
from decimal import Decimal
from hashlib import sha256
import io
import json
from pathlib import Path
import struct
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]


def points(raw):
    assert struct.unpack('>i',raw[:4])[0]==9994
    assert struct.unpack('<ii',raw[28:36])==(1000,1)
    assert struct.unpack('>i',raw[24:28])[0]*2==len(raw)
    offset=100;result=[]
    while offset<len(raw):
        number,words=struct.unpack('>ii',raw[offset:offset+8]);assert number==len(result)+1
        content=raw[offset+8:offset+8+2*words];kind=struct.unpack('<i',content[:4])[0]
        assert kind in [0,1]
        result.append(None if kind==0 else struct.unpack('<dd',content[4:20]))
        offset+=8+2*words
    assert offset==len(raw)
    return result


def dbf_rows(raw):
    size,header,record=struct.unpack('<IHH',raw[4:12]);names=[];lengths=[];offset=32
    while raw[offset]!=13:
        field=raw[offset:offset+32];names.append(field[:11].split(b'\0')[0].decode('cp949'))
        lengths.append(field[16]);offset+=32
    result=[]
    for i in range(size):
        block=raw[header+i*record:header+(i+1)*record];assert block[:1]==b' '
        offset=1;row={}
        for name,length in zip(names,lengths):
            row[name]=block[offset:offset+length].decode('cp949').strip();offset+=length
        result.append(row)
    return result


def equivalent_value(csv_value,dbf_value,numeric=False):
    """CSV에 표시된 소수 자리의 반올림 한계만 허용하며 결측은 0으로 바꾸지 않는다."""
    if not numeric:return csv_value.strip()==dbf_value.strip()
    if not csv_value.strip():return not dbf_value.strip() or set(dbf_value.strip())=={'*'}
    if not dbf_value.strip() or '*' in dbf_value:return False
    a,b=Decimal(csv_value),Decimal(dbf_value)
    return a.is_finite() and b.is_finite() and abs(a-b)<=Decimal(10)**a.as_tuple().exponent/2


def main():
    folder=ROOT/'outputs/private/public_road_context_20261031_v1';source=folder/'culvert_coordinates_20260514.zip'
    out=ROOT/'outputs/private/official_culvert_anchors_20261031_v2';out.mkdir(parents=True,exist_ok=False)
    receipt=json.loads((folder/'receipt.json').read_text(encoding='utf-8'))
    assert receipt['status']=='download_complete'
    expected=next(r['sha256'] for r in receipt['requests'] if r['file']==source.name)
    assert sha256(source.read_bytes()).hexdigest()==expected
    files={}
    with ZipFile(source) as archive:
        assert archive.testzip() is None
        for suffix in ['csv','shp','shx','dbf','prj','cpg']:
            matches=[n for n in archive.namelist() if n.endswith('.'+suffix)];assert len(matches)==1
            files[suffix]=archive.read(matches[0])
            (out/('culverts.'+suffix)).write_bytes(files[suffix])
    assert files['cpg'].decode().strip()=='EUC-KR'
    assert 'GCS_WGS_1984' in files['prj'].decode() and 'Degree' in files['prj'].decode()
    rows=list(csv.DictReader(io.StringIO(files['csv'].decode('cp949'))))
    geometry=points(files['shp']);attributes=dbf_rows(files['dbf'])
    assert len(rows)==len(geometry)==len(attributes)==10601
    aliases={'서해안선':'서해안고속국도','통영대전선,중부선':'통영-대전고속국도','논산천안선,호남선':'호남고속국도'}
    normalized=[];coordinate_checks=0;coordinate_mismatches=[];attribute_mismatches=[]
    for index,(row,point,attribute) in enumerate(zip(rows,geometry,attributes),1):
        assert set(attribute)==set(row)
        for key in row:
            if not equivalent_value(row[key],attribute[key],key in ['이정','폭(m)','높이(m)','연장','Y좌표','X좌표']):
                attribute_mismatches.append([index,key])
        has_xy=bool(row['X좌표'] and row['Y좌표'])
        lon=float(row['X좌표']) if row['X좌표'] else None;lat=float(row['Y좌표']) if row['Y좌표'] else None
        if has_xy and point is not None:
            if max(abs(point[0]-lon),abs(point[1]-lat))>5.01e-10:coordinate_mismatches.append(index)
            coordinate_checks+=1
        elif has_xy or point is not None:coordinate_mismatches.append(index)
        valid=has_xy and point is not None and 124<=lon<=132 and 33<=lat<=39
        route=aliases.get(row['노선'])
        normalized.append(dict(source_row=index,name=row['암거명'],headquarters=row['본부'],office=row['지사'],
            original_route=row['노선'],route=route,chainage_km=float(row['이정']) if row['이정'] else None,
            longitude=lon,latitude=lat,use=row['암거용도'],structure_length_m=row['연장'],
            source_coordinate_valid=valid,in_three_route_scope=bool(route),
            source_date='2026-05-14',historical_2024_2025_position_verified=False))
    with (out/'anchors.csv').open('x',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(normalized[0]));writer.writeheader();writer.writerows(normalized)
    summary=dict(status='source_verified' if not coordinate_mismatches and not attribute_mismatches else 'source_mismatch_review_required',
        records=len(rows),source_crs='WGS84 geographic degrees from included PRJ',
        coordinate_comparisons=coordinate_checks,coordinate_mismatches=coordinate_mismatches,
        attribute_comparisons=len(rows)*len(rows[0]),numeric_tolerance='Half of the last displayed CSV decimal place; missing equals DBF blank/asterisks only',
        dbf_columns=list(attributes[0]),attribute_mismatches=attribute_mismatches,
        three_route_records=sum(r['in_three_route_scope'] for r in normalized),
        three_route_valid_coordinates=sum(r['in_three_route_scope'] and r['source_coordinate_valid'] for r in normalized),
        original_zip_sha256=expected,source_date='2026-05-14',download_receipt_sha256=sha256((folder/'receipt.json').read_bytes()).hexdigest(),
        geometry_alignment_verified=False,not_a_road_surface_observation=True,
        previous_attempt='v1 used literal comparison for floating-point DBF numbers and CSV text. v1 remains unchanged; v2 checks numeric rounding and surrounding spaces, not changed observations.',
        files={p.name:sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()},
        audit_script_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['files','attribute_mismatches','coordinate_mismatches']},ensure_ascii=False))
    print('coordinate mismatches',len(coordinate_mismatches),'attribute mismatches',len(attribute_mismatches),flush=True)


if __name__=='__main__':main()
