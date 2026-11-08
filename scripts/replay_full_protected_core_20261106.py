"""정답 열이 없는 전체 검증 기상 입력을 포함하고 제출 CLI의 전 기간 추론을 대조한다."""
from pathlib import Path
import json,sys,subprocess,os,time
import numpy as np,pandas as pd,psutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_objective_icing import verify_preserved
W=ROOT/'outputs/private/final_jury_review_20261106';B=W/'icy_road_model'
SOURCE=ROOT/'outputs/private/submission_candidate_20261024_v3'

def main():
    out=W/'full_core_replay';assert not out.exists();out.mkdir()
    preserved=verify_preserved()
    index=pd.read_csv(SOURCE/'data/point_prediction_index.csv',dtype={'id':str,'prediction_group':str})
    groups=json.loads((SOURCE/'data/prediction_group_manifest.json').read_text('utf8'))
    subset=index.loc[index.kind.eq('protected')].sort_values(['id','winter']);assert len(subset)==6
    frames=[];records=[]
    for r in subset.itertuples():
        p=SOURCE/'data/weather_groups'/(r.prediction_group+'.parquet')
        assert sha(p)==groups[r.prediction_group]['weather_sha256']
        f=pd.read_parquet(p)
        assert not set(f)&{'road_temp','ice','state_raw','state','observed_ice','target','label'}
        assert len(f)==17280 and f.time.min()==pd.Timestamp(f'{r.winter}-11-01')
        assert f.time.max()==pd.Timestamp(f'{r.winter+1}-02-28T23:50:00')
        assert {'asos_solar_altitude_deg','asos_solar_sine_positive'}<=set(f)
        f.station=r.id;frames.append(f)
        record=groups[r.prediction_group]
        records.append(dict(station=r.id,winter=int(r.winter),source_group=r.prediction_group,input_sha256=sha(p),
            asos_station=record['asos_station'],solar_latitude=record['solar_lat'],solar_longitude=record['solar_lon'],
            solar_coordinate_source='ASOS',rows=len(f)))
    f=pd.concat(frames,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    assert len(f)==103680 and not f.duplicated(['station','time']).any()
    target=B/'data/validation_weather.parquet';assert not target.exists()
    f.to_parquet(target,index=False,compression='zstd')
    # 공통 기상 열은 이미 포함한 기상 검증 자료와도 정확히 같아야 한다.
    common=pd.read_parquet(B/'results/evaluation/protected_weather/weather_inputs.parquet').sort_values(['station','time']).reset_index(drop=True)
    columns=[c for c in common if c in f]
    pd.testing.assert_frame_equal(f[columns],common[columns],check_exact=True)
    env=dict(os.environ);env.update(PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
    output=B/'local_review/full_protected_predictions.parquet';output.parent.mkdir(exist_ok=True)
    started=time.perf_counter()
    p=subprocess.Popen([sys.executable,'-X','utf8','code/predict.py','--input','data/validation_weather.parquet','--output','local_review/full_protected_predictions.parquet'],cwd=B,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    peak=0
    while p.poll() is None:
        try:peak=max(peak,psutil.Process(p.pid).memory_info().rss)
        except psutil.NoSuchProcess:pass
        time.sleep(.05)
    stdout,stderr=p.communicate();seconds=time.perf_counter()-started
    assert p.returncode==0,stdout.decode('utf8')+stderr.decode('utf8')
    (out/'cli_stdout.json').write_bytes(stdout)
    pred=pd.read_parquet(output)
    expected=pd.read_csv(B/'results/evaluation/observations_predictions.csv',usecols=['station_id','prediction_time_kst','estimated_road_temperature_c','predicted_ice'],dtype={'station_id':str},parse_dates=['prediction_time_kst'],float_precision='round_trip')
    expected=expected.rename(columns={'station_id':'station','prediction_time_kst':'time','estimated_road_temperature_c':'estimated_road_temp_c'})
    # 대조에는 기존 예측 열만 읽고 관측 열을 선택이나 학습에 사용하지 않는다.
    keys=['station','time'];labels=['estimated_road_temp_c','predicted_ice']
    pair=pred[keys+labels].merge(expected[keys+labels],on=keys,validate='one_to_one',suffixes=['','_expected'])
    assert len(pair)==103680
    for c in labels:np.testing.assert_array_equal(pair[c].to_numpy(float,na_value=np.nan),pair[c+'_expected'].to_numpy(float,na_value=np.nan))
    receipt=dict(status='full_protected_cli_exact',input_rows=len(f),output_rows=len(pred),
        estimated_temperature_rows=int(pred.estimated_road_temp_c.notna().sum()),ice_rows=int(pred.predicted_ice.notna().sum()),
        input_has_observed_targets=False,solar_coordinates='linked ASOS station',
        same_common_input_values=True,input_sha256=sha(target),output_sha256=sha(output),
        observed_values_used_for_training_or_selection=False,model_files_changed=False,
        runtime=dict(wall_seconds=seconds,peak_process_rss_bytes=peak,sampling_interval_seconds=.05,
                     python=sys.version.split()[0],logical_cpus=psutil.cpu_count(),threads=2,
                     note='현재 Windows CPU 환경의 단일 실행. 파일 읽기·기상 이력 계산·출력 저장을 포함하며 다른 장비 성능을 보장하지 않음'),
        sources=records)
    (B/'technical/full_validation_input.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf8')
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf8')
    assert verify_preserved()==preserved
    print(json.dumps({k:v for k,v in receipt.items() if k not in ['sources']},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
