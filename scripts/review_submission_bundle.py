"""압축 해제된 제출 검토 묶음의 전체 파일 해시와 선택적 예측·노트북 실행을 확인한다."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
from datetime import datetime,timezone


def verify_directory(root):
    root=Path(root).resolve();manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'));records=manifest['files']
    for name,record in records.items():
        posix=PurePosixPath(name)
        if not posix.parts or posix.is_absolute() or '..' in posix.parts or ':' in name or '\\' in name or name!=posix.as_posix():raise ValueError('Unsafe member: '+name)
        path=root/name
        if not path.resolve().is_relative_to(root) or path.is_symlink() or any(p.is_symlink() for p in path.parents if p!=root and p.is_relative_to(root)):raise ValueError('Linked or escaping file: '+name)
        if not path.is_file() or path.stat().st_size!=record['bytes']:raise ValueError('Missing or wrong-size file: '+name)
        with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        if digest!=record['sha256']:raise ValueError('Changed file: '+name)
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and not p.relative_to(root).parts[0]=='local_review'}
    unexpected=actual-set(records)-{'manifest.json'}
    if unexpected:raise ValueError('Unexpected files: '+', '.join(sorted(unexpected)))
    return dict(status='all_manifest_files_verified',files=len(records),bytes=sum(r['bytes'] for r in records.values()),package_label=manifest.get('package_label'))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=Path('.'));parser.add_argument('--smoke',action='store_true');parser.add_argument('--output',type=Path,default=Path('local_review/verification.json'));args=parser.parse_args()
    root=args.root.resolve();output=(root/args.output).resolve()
    if not output.is_relative_to(root/'local_review') or output.exists():raise ValueError('New output inside local_review is required')
    result=verify_directory(root);output.parent.mkdir(parents=True,exist_ok=True)
    result.update(at_utc=datetime.now(timezone.utc).isoformat(),checks=[],model_or_prediction_changed=False)
    if args.smoke:
        prediction=output.with_name(output.stem+'_predictions.csv')
        if prediction.exists():raise FileExistsError(prediction)
        commands=[('prediction',[sys.executable,'-X','utf8','code/predict.py','--input','data/weather_example.csv','--output',str(prediction),'--output-start','2024-12-15','--output-end','2024-12-16']),
                  ('notebook',[sys.executable,'-X','utf8','scripts/check_notebook.py','notebooks/extended_submission_review.ipynb'])]
        environment=os.environ.copy();environment.update(OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
        for name,command in commands:
            log=output.with_name(output.stem+'_'+name+'.log')
            if log.exists():raise FileExistsError(log)
            run=subprocess.run(command,cwd=root,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600)
            log.write_bytes(run.stdout)
            if run.returncode:raise RuntimeError(name+' failed; inspect '+str(log))
            result['checks'].append(dict(name=name,returncode=0,log=log.relative_to(root).as_posix()))
        import pandas as pd
        options=dict(dtype={'station':str,'predicted_ice':'Int64'},parse_dates=['time'],float_precision='round_trip')
        predicted=pd.read_csv(prediction,**options);expected=pd.read_csv(root/'data/example_predictions.csv',**options)
        pd.testing.assert_frame_equal(predicted,expected,check_exact=True);result['prediction_rows_identical']=len(predicted)
        verify_directory(root);result['status']='manifest_and_execution_verified'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
