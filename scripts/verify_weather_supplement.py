"""보완 묶음을 별도 위치에 복제하고 CLI·전체 재학습 노트북을 실제 실행한다."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys

import nbformat
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_objective_icing import read,write,verify_preserved


def main():
    source=ROOT/'outputs/private/weather_observation_supplement_20261031_v1'
    out=ROOT/'outputs/private/weather_supplement_validation_20261031_v1'
    if out.exists():raise FileExistsError('Preserve supplement verification')
    receipt=read(source/'receipt.json');frozen=verify_preserved()
    for path,digest in receipt['files'].items():assert sha(source/path)==digest,path
    out.mkdir(parents=True);relocated=out/'relocated';shutil.copytree(source,relocated)
    for path,digest in receipt['files'].items():assert sha(relocated/path)==digest,path
    env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2')
    commands=[
        [sys.executable,'scripts/predict_weather_supplement.py','--model','model','--input','data/inference_example.csv','--output','cli_predictions.csv']
    ];results=[]
    run=subprocess.run(commands[0],cwd=relocated,env=env,text=True,encoding='utf-8',capture_output=True,timeout=180)
    (out/'cli.log').write_text(run.stdout+'\n'+run.stderr,encoding='utf-8');assert run.returncode==0,run.stderr
    expected=pd.read_csv(relocated/'data/expected_predictions.csv',dtype={'station':str})
    actual=pd.read_csv(relocated/'cli_predictions.csv',dtype={'station':str})
    pd.testing.assert_frame_equal(expected,actual,check_exact=True)
    results.append(dict(kind='relocated_cli',rows=len(actual),exit_code=run.returncode))
    nb=nbformat.read(relocated/'notebooks/weather_observation_supplement.ipynb',as_version=4)
    edits=0
    for cell in nb.cells:
        if cell.cell_type=='code' and 'RUN_REFIT=False' in cell.source:
            cell.source=cell.source.replace('RUN_REFIT=False','RUN_REFIT=True');edits+=1
    assert edits==1
    notebook=relocated/'notebooks/full_refit_check.ipynb';nbformat.write(nb,notebook)
    command=[sys.executable,str(ROOT/'scripts/check_notebook.py'),str(notebook),'--timeout','360']
    run=subprocess.run(command,cwd=relocated,env=env,text=True,encoding='utf-8',capture_output=True,timeout=900)
    (out/'notebook_full_refit.log').write_text(run.stdout+'\n'+run.stderr,encoding='utf-8')
    assert run.returncode==0,run.stdout+'\n'+run.stderr
    results.append(dict(kind='relocated_notebook_full_refit',code_cells=sum(c.cell_type=='code' for c in nb.cells),
        refit_targets=receipt['selected_targets'],exit_code=run.returncode))
    for path,digest in receipt['files'].items():assert sha(source/path)==digest,path
    assert verify_preserved()==frozen
    write(out/'receipt.json',dict(status='weather_supplement_verified',source_receipt_sha256=sha(source/'receipt.json'),
        tests=results,original_files_preserved=len(receipt['files']),preservation=frozen,
        logs={p.name:sha(p) for p in out.glob('*.log')},script_sha256=sha(Path(__file__))))
    print('SUPPLEMENT VERIFIED',len(actual),'rows',receipt['selected_targets'],flush=True)


if __name__=='__main__':main()
