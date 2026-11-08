"""별도 위치의 CLI432행·Jupyter·전체습도재학습으로 새실행묶음을 검증한다."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import nbformat
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,verify_preserved
from src.data_source import sha256_file as sha


def main():
    source=ROOT/'outputs/private/weather_history_supplement_20261101_v2'
    receipt=read(source/'receipt.json')
    assert receipt['status']=='weather_history_supplement_built'
    assert receipt['maximum_extra_context_prediction_difference']==0
    for name,digest in receipt['files'].items():assert sha(source/name)==digest,name
    out=ROOT/'outputs/private/weather_history_supplement_validation_20261101_v2'
    if out.exists():raise FileExistsError('Preserve relocated history validation')
    out.mkdir(parents=True);relocated=out/'relocated';shutil.copytree(source,relocated)
    env=os.environ.copy();env.pop('PYTHONPATH',None)
    env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
    command=[sys.executable,'scripts/predict_weather_history.py','--input','data/weather_context_example.csv',
        '--output','cli_predictions.csv','--output-start','2024-12-15','--output-end','2024-12-16']
    cli=subprocess.run(command,cwd=relocated,env=env,capture_output=True,text=True,encoding='utf-8',timeout=240)
    (out/'cli.log').write_text(cli.stdout+'\n'+cli.stderr,'utf-8');assert cli.returncode==0,cli.stderr
    options=dict(dtype={'station':str},parse_dates=['time'],float_precision='round_trip')
    expected=pd.read_csv(relocated/'data/expected_predictions.csv',**options)
    actual=pd.read_csv(relocated/'cli_predictions.csv',**options)
    pd.testing.assert_frame_equal(expected,actual,check_exact=True)
    assert len(actual)==432 and actual.humidity_history_status.eq('complete_24h').all()
    book=nbformat.read(relocated/'notebooks/weather_history_supplement.ipynb',as_version=4);changes=0
    for cell in book.cells:
        if cell.cell_type=='code' and 'RUN_REFIT=False' in cell.source:
            cell.source=cell.source.replace('RUN_REFIT=False','RUN_REFIT=True');changes+=1
    assert changes==1
    path=relocated/'notebooks/full_refit_check.ipynb';nbformat.write(book,path)
    command=[sys.executable,str(ROOT/'scripts/check_notebook.py'),str(path),'--timeout','600']
    notebook=subprocess.run(command,cwd=relocated,env=env,capture_output=True,text=True,encoding='utf-8',timeout=1000)
    (out/'notebook_full_refit.log').write_text(notebook.stdout+'\n'+notebook.stderr,'utf-8')
    assert notebook.returncode==0,notebook.stdout+'\n'+notebook.stderr
    for name,digest in receipt['files'].items():assert sha(source/name)==digest,name
    for name,digest in receipt['files'].items():assert sha(relocated/name)==digest,name
    preservation=verify_preserved()
    write(out/'receipt.json',dict(status='weather_history_supplement_verified',source_receipt_sha256=sha(source/'receipt.json'),
        actual_cli_rows_identical=len(actual),notebook_code_cells=sum(c.cell_type=='code' for c in book.cells),
        complete_refit_targets=['relative_humidity'],extra_context_prediction_difference=0,
        production_road_temperature_changed=False,production_icing_changed=False,
        original_files_preserved=len(receipt['files']),preservation=preservation,
        logs={p.name:sha(p) for p in out.glob('*.log')},verification_source_sha256=sha(Path(__file__))))
    print('HISTORY SUPPLEMENT VERIFIED',len(actual),'rows; full refit exact',flush=True)


if __name__=='__main__':main()
