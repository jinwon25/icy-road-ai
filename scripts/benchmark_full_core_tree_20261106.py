"""전체 추론의 실행시간과 Windows Python 실행기 자식을 포함한 작업집합을 확인한다."""
from pathlib import Path
import os,sys,json,time,subprocess
import pandas as pd,psutil
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/private/final_jury_review_20261106';B=W/'icy_road_model'
def main():
    path=W/'full_core_benchmark.json';assert not path.exists()
    env=dict(os.environ);env.update(PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
    target=B/'local_review/full_core_benchmark.parquet';assert not target.exists()
    started=time.perf_counter();p=subprocess.Popen([sys.executable,'-X','utf8','code/predict.py','--input','data/validation_weather.parquet','--output','local_review/full_core_benchmark.parquet'],cwd=B,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    peak=0;maximum_processes=0
    while p.poll() is None:
        try:
            main=psutil.Process(p.pid);processes=[main,*main.children(recursive=True)];total=0
            for process in processes:
                try:total+=process.memory_info().rss
                except (psutil.NoSuchProcess,psutil.AccessDenied):pass
            peak=max(peak,total);maximum_processes=max(maximum_processes,len(processes))
        except psutil.NoSuchProcess:pass
        time.sleep(.05)
    stdout,stderr=p.communicate();seconds=time.perf_counter()-started
    assert p.returncode==0,stdout.decode('utf8')+stderr.decode('utf8')
    pd.testing.assert_frame_equal(pd.read_parquet(target),pd.read_parquet(B/'local_review/full_protected_predictions.parquet'),check_exact=True)
    assert peak>100*1024*1024 and maximum_processes>=2
    value=dict(wall_seconds=seconds,peak_process_tree_rss_bytes=peak,maximum_processes=maximum_processes,
        sampling_interval_seconds=.05,python=sys.version.split()[0],logical_cpus=psutil.cpu_count(),threads=2,
        note='현재 Windows CPU 환경의 단일 측정. 파일 읽기·이력 계산·출력 저장 포함. 프로세스 트리 RSS 합계는 공유 페이지를 중복 포함할 수 있으며 물리 메모리 사용량과 다름.')
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf8')
    receipt=json.loads((B/'technical/full_validation_input.json').read_text('utf8'));receipt['runtime']=value
    (B/'technical/full_validation_input.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(value,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
