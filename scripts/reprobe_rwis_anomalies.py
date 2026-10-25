"""이미 평가한 두 지점의 정해진 작은 구간만 재조회해 API 이상을 재현한다. 평가에는 반영하지 않는다."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sys
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.kma_rwis_download import load_auth_key
from src.rwis_forensics import response_profile
from scripts.blind_icing_validation import DEFAULT, verify


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True)
    out = p.parse_args().output.resolve()
    if out.exists() or not out.is_relative_to((ROOT/'outputs/private').resolve()):
        raise ValueError('New private output required')
    verify(DEFAULT)
    digest = hashlib.sha256((DEFAULT/'summary.json').read_bytes()).hexdigest()
    key = load_auth_key(ROOT/'secret.env')
    out.mkdir(parents=True)
    # 모두 이미 개봉한 평가 기간이다. 보호 지점이나 새 지점·기간을 요청하지 않는다.
    samples = [('12213','202411010010','202411010010',1), ('12213','202602282350','202602282350',1),
        ('33406','202511301200','202511301200',1), ('33406','202512151200','202512151200',1),
        ('33406','202602130010','202602130010',1), ('33406','202602130010','202602130010',0),
        ('33406','202602240855','202602240905',1), ('33406','202602241200','202602241200',1)]
    (out/'plan.json').write_text(json.dumps(dict(at_utc=datetime.now(timezone.utc).isoformat(), samples=samples,
        purpose='Source diagnosis only; frozen observations, labels, predictions, metrics remain untouched',
        endpoint='https://apihub.kma.go.kr/api/typ01/url/road_stn_obs.php', original_summary_sha256=digest), indent=2), encoding='utf-8')
    records = []
    for station, start, end, disp in samples:
        assert station in {'12213','33406'}
        params=dict(mode=1,var=station,tm1=start,tm2=end,help=1,disp=disp)
        record=dict(parameters=params,at_utc=datetime.now(timezone.utc).isoformat())
        try:
            response=requests.get('https://apihub.kma.go.kr/api/typ01/url/road_stn_obs.php',params=params|{'authKey':key},timeout=(10,45))
            body=response.text
            if key in body:raise ValueError('Credential echo suppressed')
            name=f'{station}_{start}_{end}_disp{disp}.txt';(out/name).write_text(body,encoding='utf-8')
            record.update(status=response.status_code,file=name,sha256=hashlib.sha256((out/name).read_bytes()).hexdigest())
            if response.status_code==200:
                record['profile']=response_profile(body,station,start,end)
        except (requests.RequestException,ValueError) as exc:
            record['error_type']=type(exc).__name__
        records.append(record)
        (out/'receipt.json').write_text(json.dumps(dict(records=records,original_summary_sha256=digest,used_for_scoring=False),ensure_ascii=False,indent=2),encoding='utf-8')
        print(station,start,'disp',disp,record.get('status'),record.get('profile',{}).get('conflicting_state_pairs'),record.get('error_type'),flush=True)
        time.sleep(1.3)
    assert hashlib.sha256((DEFAULT/'summary.json').read_bytes()).hexdigest()==digest
    verify(DEFAULT)


if __name__=='__main__':main()
