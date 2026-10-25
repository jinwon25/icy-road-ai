"""추가 시간 이력·손실 대조의 저장 모델을 동결된 독립 재실행 검사에 연결한다."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import audit_extended_models as runner
from src.followup_temperature import feature_table
from src.data_source import sha256_file as sha


if __name__=='__main__':
    search=Path(sys.argv[sys.argv.index('--search')+1]);plan=json.loads((search/'plan.json').read_text('utf-8'))
    for name,expected in plan['settings']['additional_source_sha256'].items():assert sha(ROOT/name)==expected,name
    runner.feature_table=feature_table
    runner.main()
    output=Path(sys.argv[sys.argv.index('--output')+1])
    (output/'dispatch_receipt.json').write_text(json.dumps(dict(feature_module_sha256=sha(ROOT/'src/followup_temperature.py'),
        dispatch_sha256=sha(Path(__file__)),audit_receipt_sha256=sha(output/'receipt.json')),indent=2)+'\n','utf-8')
