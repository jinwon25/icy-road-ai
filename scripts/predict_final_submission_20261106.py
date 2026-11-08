"""최종 제출용 기본 프로필: AI 노면온도 v3 + 명시적 F1 우선 기온 기준선.

기존 v2는 --icing-profile preserved_v2로 재현한다. 선택 목적과 한계는 최종 보고서에 기재한다.
"""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.predict_competition_profile import main
if __name__=='__main__':
    if not any(a=='--icing-profile' or a.startswith('--icing-profile=') for a in sys.argv[1:]):
        sys.argv.extend(['--icing-profile','score_priority_asos_zero'])
    main()