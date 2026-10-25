"""XGBoost의 NaN 기본 파라미터를 명시적으로 직렬화해 기존 탐색을 재개한다.

학습·입력·분할·예측 코드는 변경하지 않는다. 기록 실패 직전 산출물은 복사 보존한다.
"""
import json
import math
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import evaluate_extended_search as runner
from src.data_source import sha256_file as sha


def parameter_json(value):
    if isinstance(value,float) and not math.isfinite(value):
        return {'nonfinite_float': 'nan' if math.isnan(value) else ('+inf' if value>0 else '-inf')}
    if isinstance(value,dict):return {k:parameter_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [parameter_json(v) for v in value]
    return value


def write(path,value):
    # 파라미터의 표현만 바꾸며 예측·평가의 NaN은 기존 엄격 JSON 검사로 계속 거부한다.
    def normalize(item):
        if isinstance(item,dict):return {k:parameter_json(v) if k=='parameters' else normalize(v) for k,v in item.items()}
        if isinstance(item,(list,tuple)):return [normalize(v) for v in item]
        return item
    value=normalize(value)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')


if __name__=='__main__':
    out=Path(sys.argv[sys.argv.index('--output')+1])
    recovery=out/'serialization_recovery';recovery.mkdir(exist_ok=True)
    record=recovery/'receipt.json'
    if not record.exists():
        preserved=[]
        for folder in out.iterdir():
            if not folder.is_dir() or folder==recovery:continue
            for path in folder.glob('*.joblib'):
                if path.with_suffix('.json').exists():continue
                for source in [path,path.with_suffix('.parquet')]:
                    if not source.exists():continue
                    dest=recovery/(folder.name+'_'+source.name)
                    if dest.exists():assert sha(dest)==sha(source)
                    else:shutil.copy2(source,dest)
                    preserved.append(dict(source=str(source.relative_to(out)),saved=str(dest.relative_to(out)),sha256=sha(source)))
        write(record,dict(reason='XGBoost default missing=np.nan could not be represented in strict JSON after model save; model outputs were not invalid.',
            correction='Only nonfinite estimator parameter metadata gets an explicit tagged JSON value. Model training and predictions remain unchanged.',
            helper_sha256=sha(Path(__file__)),preserved_orphans=preserved))
    else:assert json.loads(record.read_text('utf-8'))['helper_sha256']==sha(Path(__file__))
    runner.write=write
    runner.main()
