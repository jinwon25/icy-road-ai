"""최종 release plan의 기본 프로필을 명시해 기존 검증된 추론기를 실행한다."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.predict_competition_profile import main
if __name__=='__main__':
    plan=json.loads((ROOT/'final_release_plan.json').read_text(encoding='utf8'))
    if not any(a=='--icing-profile' or a.startswith('--icing-profile=') for a in sys.argv):
        sys.argv.extend(['--icing-profile',plan['default_icing_profile']])
    if not any(a=='--bundle' or a.startswith('--bundle=') for a in sys.argv):sys.argv.extend(['--bundle',str(ROOT)])
    main()