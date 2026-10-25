"""같은 회귀 비교 실행기에 해시 고정한 열·수분 특징만 추가한다."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import evaluate_extended_search as runner
from src.thermal_extended import feature_table
from src.data_source import sha256_file as sha

if __name__=='__main__':
    config=Path(sys.argv[sys.argv.index('--config')+1]);plan=json.loads(config.read_text('utf-8'))
    assert plan['thermal_library_sha256']==sha(ROOT/'src/thermal_extended.py')
    runner.feature_table=feature_table
    runner.main()
