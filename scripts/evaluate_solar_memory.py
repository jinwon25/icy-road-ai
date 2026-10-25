"""사전 고정한 태양 위치·열 이력 결합 후보를 같은 공간 제외 조건에서 비교한다."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import evaluate_extended_search as runner
from src.solar_memory_search import feature_table
from src.data_source import sha256_file as sha

if __name__=='__main__':
    config=Path(sys.argv[sys.argv.index('--config')+1]);plan=json.loads(config.read_text('utf-8'))
    for name,expected in plan['additional_source_sha256'].items():assert sha(ROOT/name)==expected,name
    runner.feature_table=feature_table
    runner.main()
