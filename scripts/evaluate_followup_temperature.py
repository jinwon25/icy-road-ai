"""v3 이후 고정 대조를 기존 지역 제외 실행기에 연결한다. 동결 소스는 바꾸지 않는다."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import evaluate_extended_search as runner
from src.followup_temperature import feature_table, training_weights
from src.data_source import sha256_file as sha


if __name__ == '__main__':
    config = Path(sys.argv[sys.argv.index('--config') + 1])
    plan = json.loads(config.read_text('utf-8'))
    for name, expected in plan['additional_source_sha256'].items():
        assert sha(ROOT / name) == expected, name
    for name, expected in plan['reference_sha256'].items():
        assert sha(ROOT / name) == expected, name
    runner.feature_table = feature_table
    runner.weights = training_weights
    runner.main()
