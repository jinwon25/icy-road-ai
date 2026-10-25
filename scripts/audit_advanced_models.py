"""열 이력·태양·지형 후보도 저장 모델 재실행과 공간 제외를 같은 방법으로 검산한다."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import audit_extended_models as runner
from src.thermal_refinement import feature_table as thermal
from src.combined_thermal_history import feature_table as combined
from src.terrain_thermal import feature_table as terrain
from src.solar_memory_search import feature_table as solar
from src.data_source import sha256_file as sha


def features(frame,kind):
    if kind=='combined_thermal_history':return combined(frame,kind)
    if kind in ['thermal_solar','thermal_terrain','history_solar','history_terrain']:return terrain(frame,kind)
    if kind in ['history_asos_solar','combined_asos_solar','combined_target_solar']:return solar(frame,kind)
    return thermal(frame,kind)


if __name__=='__main__':
    output=Path(sys.argv[sys.argv.index('--output')+1])
    runner.feature_table=features
    runner.main()
    paths=[Path(__file__),ROOT/'scripts/audit_extended_models.py',*[ROOT/'src'/name for name in ['thermal_refinement.py','thermal_extended.py','combined_thermal_history.py','terrain_thermal.py','solar_memory_search.py']]]
    (output/'feature_dispatch_receipt.json').write_text(json.dumps(dict(audit_receipt_sha256=sha(output/'receipt.json'),
        signatures={str(p.relative_to(ROOT)):sha(p) for p in paths}),indent=2)+'\n','utf-8')
