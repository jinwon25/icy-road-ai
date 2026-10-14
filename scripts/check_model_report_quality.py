"""추가 모델·문서 변경의 단위 검사와 보고서 수치·레이아웃 기초 검사를 기록."""
from pathlib import Path
from datetime import datetime, timezone
import subprocess
import sys
import fitz

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write,preservation
from src.data_source import sha256_file as sha

OUT=ROOT/'outputs/private/model_report_quality_20261014_v1'
REPORT=ROOT/'outputs/private/report_upgrade_20261014_v2'


def main():
    OUT.mkdir(exist_ok=False)
    frozen=preservation()
    records=[]
    for name,args in [('unit_tests',['-m','unittest','discover','-s','tests','-v']),
                      ('repository',['scripts/check_repository.py']),('markdown',['scripts/check_markdown.py'])]:
        result=subprocess.run([sys.executable,'-X','utf8',*args],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (OUT/(name+'.log')).write_bytes(result.stdout)
        records.append(dict(name=name,exit_code=result.returncode,log_sha256=sha(OUT/(name+'.log'))))
        print(name,result.returncode,result.stdout.decode('utf-8',errors='replace')[-500:],flush=True)
        if result.returncode:raise RuntimeError('Required quality check failed: '+name)
    pdf=next(REPORT.glob('*.pdf'))
    with fitz.open(pdf) as doc:
        assert len(doc)==12
        text='\n'.join(p.get_text() for p in doc)
        for expected in ['1.200440','1.200531','0.030633','16.96','19,174','2,672','1,242,056','6,340','95.9%']:
            assert expected in text,expected
        assert '\ufffd' not in text
        links=sum(len(p.get_links()) for p in doc)
        assert links>=13
        for p in doc:
            assert len(p.get_text())>200
            for block in p.get_text('dict')['blocks']:
                if block['type']!=0:continue
                x0,y0,x1,y1=block['bbox']
                assert x0>=35 and x1<=p.rect.width-35 and y0>=20 and y1<=p.rect.height-15,block['bbox']
    assert preservation()==frozen
    write(OUT/'quality_receipt.json',dict(status='model_report_quality_checks_passed',
        completed_at_utc=datetime.now(timezone.utc).isoformat(),checks=records,pdf_pages=12,pdf_links=links,
        pdf_sha256=sha(pdf),visual_review_is_separate=True,old_frozen_files=frozen[0],reserved_frozen_files=frozen[1]))


if __name__=='__main__':main()
