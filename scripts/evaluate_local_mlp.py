"""정정 기상 입력에서 고정 학습 길이 MLP를 비교한다. 외부 평가로 조기 종료하지 않는다."""
import json
from pathlib import Path
import sys
from importlib.metadata import version
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import evaluate_extended_search as runner
from src.thermal_refinement import feature_table
from src.local_mlp import LocalMLPRegressor
from src.data_source import sha256_file as sha


def estimator(spec,seed,threads):
    assert spec['family']=='local_mlp'
    return LocalMLPRegressor(epochs=spec['epochs'],width=spec['width'],depth=spec['depth'],loss=spec['loss'],seed=seed,threads=threads)


if __name__=='__main__':
    config=Path(sys.argv[sys.argv.index('--config')+1]);plan=json.loads(config.read_text('utf-8'))
    for name,expected in plan['additional_source_sha256'].items():assert sha(ROOT/name)==expected
    assert version('torch')==plan['torch_version']
    runner.feature_table=feature_table;runner.estimator=estimator;runner.main()
