"""작업 폴더 안의 임시 커널로 제출 Notebook의 12개 셀을 실제 실행한다."""
from pathlib import Path
import sys,os,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.check_notebook import check_notebook
W=ROOT/'outputs/private/final_jury_review_20261106';B=W/'icy_road_model'
if __name__=='__main__':
    runtime=W/'notebook_runtime';runtime.mkdir()
    assert runtime.resolve().is_relative_to(W.resolve())
    tempfile.tempdir=str(runtime.resolve())
    os.environ.update(TEMP=str(runtime.resolve()),TMP=str(runtime.resolve()),PYTHONDONTWRITEBYTECODE='1',
        OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
    check_notebook(B/'notebooks/analysis.ipynb',timeout=600)
