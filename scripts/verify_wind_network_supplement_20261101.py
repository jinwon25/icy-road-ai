"""독립 위치에서 실제 Jupyter3셀로 API·CLI·전체재학습432행의 정확한 일치를 확인한다."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,now,verify_preserved
from src.data_source import sha256_file as sha
from src.wind_network_runtime import predict_wind_network


def verify_outputs(bundle):
    runs=list((bundle/'local_review').glob('*/refit/receipt.json'));assert len(runs)==1
    refit=read(runs[0]);local=runs[0].parents[1]
    load=lambda p:pd.read_csv(p,dtype={'station':str},float_precision='round_trip')
    query=load(bundle/'data/weather_example.csv');points=load(bundle/'data/points_example.csv')
    coordinates=load(bundle/'data/aws_coordinates.csv');aws=pd.read_parquet(bundle/'data/aws_example.parquet')
    expected=load(bundle/'data/reference_predictions.csv');expected.time=pd.to_datetime(expected.time)
    actual=load(local/'cli.csv');actual.time=pd.to_datetime(actual.time)
    pd.testing.assert_frame_equal(actual,expected,check_exact=True)
    for model in [bundle/'model',local/'refit']:
        result=predict_wind_network(query,points,aws,coordinates,model)
        pd.testing.assert_frame_equal(result,expected,check_exact=True)
    assert len(expected)==432
    return refit


def main():
    source=ROOT/'outputs/private/wind_network_supplement_20261101_v2'
    out=ROOT/'outputs/private/wind_network_supplement_validation_20261101_v1'
    if out.exists():raise FileExistsError('Preserve relocated verification')
    receipt=read(source/'receipt.json');frozen=verify_preserved()
    for name,digest in receipt['files'].items():assert sha(source/name)==digest,name
    out.mkdir();bundle=out/'bundle';bundle.mkdir()
    for name in [*receipt['files'],'receipt.json']:
        dest=bundle/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/name,dest)
    env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2')
    command=[sys.executable,'scripts/check_notebook.py','notebooks/wind_network_review.ipynb','--timeout','600']
    result=subprocess.run(command,cwd=bundle,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1200)
    (out/'notebook.log').write_bytes(result.stdout);assert result.returncode==0,'Relocated notebook failed: '+str(out/'notebook.log')
    refit=verify_outputs(bundle);assert refit['training_rows']==receipt['training_rows'] and refit['status']=='wind_network_refit_complete'
    for name,digest in receipt['files'].items():assert sha(source/name)==sha(bundle/name)==digest,name
    assert verify_preserved()==frozen
    proof=dict(status='wind_network_supplement_verified',at_utc=now(),source_receipt_sha256=sha(source/'receipt.json'),
        notebook_code_cells=3,actual_cli_rows_exact=432,api_rows_exact=432,refit_rows_exact=432,full_refit_training_rows=refit['training_rows'],
        source_files_preserved=len(receipt['files']),prefix_exact=receipt['prefix_exact'],notebook_log_sha256=sha(out/'notebook.log'),
        protected_outcomes_read=False,existing_models_changed=False)
    write(out/'receipt.json',proof);print(proof,flush=True)


if __name__=='__main__':main()
