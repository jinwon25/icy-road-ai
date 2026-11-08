"""팀명이 반영된 최종 화면·영상의 자동 검사를 실행한다."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import audit_information_media_20261106 as audit
audit.O=audit.W/'media_review_team'
if __name__=='__main__':audit.main()
