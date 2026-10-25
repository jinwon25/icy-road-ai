"""소스 서명과 사전 후보를 고정한 후 열·수분 후보 주변을 대조한다."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import evaluate_extended_search as runner
from src.thermal_refinement import feature_table, estimator
from src.data_source import sha256_file as sha

if __name__=='__main__':
    config=Path(sys.argv[sys.argv.index('--config')+1]);plan=json.loads(config.read_text('utf-8'))
    for name, expected in plan['additional_source_sha256'].items():
        assert sha(ROOT/name)==expected, name
    runner.feature_table=feature_table
    runner.estimator=estimator
    runner.main()
