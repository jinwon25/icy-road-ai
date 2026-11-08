"""직접 확인한 최종 화면·영상·PDF의 시각 검수와 메타데이터를 정리한다."""
from pathlib import Path
import json,shutil,sys
import fitz
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
W=ROOT/'outputs/private/evening_refinement_20261106';B=W/'icy_road_model';D=W/'icy_road_documents'
def update(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf8')
def main():
    pdf=B/'results/field/field_measurement_plan.pdf'
    doc=fitz.open(pdf);metadata=doc.metadata
    metadata.update(author='로드투인사이트',title='서해안 고속도로 두 범위의 현장 확인 계획',subject='같은 기상 입력을 공유하는 인접 구간의 비교 계측 계획')
    doc.set_metadata(metadata);doc.saveIncr();doc.close()
    doc=fitz.open(pdf);assert len(doc)==2 and doc.metadata['author']=='로드투인사이트'
    for i,page in enumerate(doc):
        pix=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5))
        reviewed=W/'field_browser_final'/f'plan_{i+1:02d}.png'
        im=Image.open(reviewed).convert('RGB');assert im.size==(pix.width,pix.height) and im.tobytes()==pix.samples
    doc.close();shutil.copyfile(pdf,D/'report/field_measurement_plan.pdf')
    for folder in ['field_browser_final','media_review_final','browser_review_final']:
        path=W/folder/'receipt.json';v=json.loads(path.read_text('utf8'))
        assert v['status'] in ['passed','passed_pending_visual_review']
        v['status']='passed';v['visual_review']='passed'
        if folder=='field_browser_final':
            v['source_sha256']['results/field/field_measurement_plan.pdf']=sha(pdf)
            v['visual_notes']=['데스크톱·태블릿·모바일의 지도와 원표를 확인',
                               '모바일의 빈 측정 양식과 입력 라벨을 확인','두 PDF 페이지의 지도·표·이용조건을 확인',
                               '메타데이터 정리 전후의 두 페이지 픽셀 일치']
        elif folder=='media_review_final':
            v['visual_notes']=['12개 실제 녹화 장면에서 기상·평가·75기준·계측 계획·빈 기록 양식·실제 추론을 확인']
        else:v['visual_notes']=['원표와 일치하는 75기준의 데스크톱·모바일 화면 및 현재 탐색 경로를 확인']
        update(path,v)
    print('계측 계획 2쪽과 실제 영상 12장면의 최종 검수를 기록했습니다.',flush=True)
if __name__=='__main__':main()
