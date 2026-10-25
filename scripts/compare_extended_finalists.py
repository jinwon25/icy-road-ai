"""후속 고정 평균을 추가하고 실제 사용 설정·코드 해시를 함께 보존한다."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import compare_extended_candidates as runner
from src.data_source import sha256_file as sha

if __name__=='__main__':
    config=ROOT/'config/extended_fixed_blends_20261024.json';settings=json.loads(config.read_text('utf-8'))
    output=Path(sys.argv[sys.argv.index('--output')+1])
    signatures={str(p.relative_to(ROOT)):sha(p) for p in [config,Path(__file__),ROOT/'scripts/compare_extended_candidates.py',ROOT/'src/extended_comparison.py']}
    runner.PAIRS=runner.PAIRS|settings['pairs']
    runner.main()
    receipt=dict(settings=settings,source_signatures=signatures,summary_sha256=sha(output/'summary.json'))
    (output/'comparison_plan.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf-8')
