"""Git 추적 파일의 원본 자료·모델 혼입과 노트북 출력을 검사한다."""
from pathlib import Path
import ast
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {'.zip', '.csv', '.xlsx', '.xls', '.pdf', '.hwp', '.docx', '.tif', '.tiff',
             '.shp', '.shx', '.dbf', '.prj', '.cpg', '.gpkg', '.geojson', '.parquet',
             '.feather', '.pkl', '.pickle', '.joblib', '.pt', '.pth', '.onnx', '.npy',
             '.npz', '.db', '.sqlite', '.sqlite3', '.pem', '.key'}


def main():
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0')
    errors = []
    checked = 0
    for name in filter(None, paths):
        path = ROOT / name
        if not path.exists():
            errors.append(f'누락된 추적 파일: {name}')
            continue
        if path.suffix.lower() in FORBIDDEN or name.startswith('outputs/') or (path.name.startswith('.env') and path.name != '.env.example'):
            errors.append(f'공유 제외 파일: {name}')
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=name)
        if path.suffix == '.ipynb':
            notebook = json.loads(path.read_text(encoding='utf-8'))
            if any(cell.get('outputs') or cell.get('execution_count') is not None for cell in notebook['cells'] if cell['cell_type'] == 'code'):
                errors.append(f'노트북 출력/실행 번호: {name}')
        if path.suffix in {'.md', '.py', '.json', '.yml', '.ipynb'}:
            text = path.read_text(encoding='utf-8-sig')
            if re.search(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|RGAPI-[A-Za-z0-9-]{30,}|sk-[A-Za-z0-9_-]{30,})', text):
                errors.append(f'인증정보 형식 발견: {name}')
            if path.suffix == '.md':
                for target in re.findall(r'\]\(([^)]+)\)', text):
                    target = target.split('#', 1)[0]
                    if target and not re.match(r'^[a-z]+:', target) and not (path.parent / target).exists():
                        errors.append(f'문서 링크 누락: {name} -> {target}')
        checked += 1
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'추적 파일 {checked}개 검사 통과: 제외 자료·인증정보 형식·노트북 출력 없음')


if __name__ == '__main__':
    main()
