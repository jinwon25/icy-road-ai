"""실제 추론 명령의 출력을 기록하고 결과 설명과 함께 MP4로 재생한다."""
import json
import subprocess
import sys
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / 'outputs/private/demo'; out.mkdir(exist_ok=True)
    started = time.perf_counter(); events = []
    command = [sys.executable, '-X', 'utf8', str(ROOT / 'scripts/demo_inference.py')]
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
    for line in process.stdout:
        events.append({'elapsed_seconds': time.perf_counter()-started, 'text': line.rstrip()})
        print(line.rstrip(), flush=True)
    if process.wait() != 0: raise RuntimeError('Actual inference command failed; no demonstration video generated')
    (out / 'actual_execution.json').write_text(json.dumps({'command': command, 'exit_code': 0, 'events': events}, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'actual_execution.txt').write_text('\n'.join(e['text'] for e in events)+'\n', encoding='utf-8')
    regular = 'C:/Windows/Fonts/malgun.ttf'; bold = 'C:/Windows/Fonts/malgunbd.ttf'
    font = ImageFont.truetype(regular, 24); small = ImageFont.truetype(regular, 21); title = ImageFont.truetype(bold, 37)
    width, height, fps = 1280, 720, 10
    path = out / 'inference_demo.mp4'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
    if not writer.isOpened(): raise RuntimeError('MP4 encoder unavailable')
    def canvas(heading, subtitle):
        im = Image.new('RGB', (width, height), '#0f172a'); draw = ImageDraw.Draw(im)
        draw.text((48, 35), heading, font=title, fill='#f8fafc')
        draw.text((50, 92), subtitle, font=small, fill='#94a3b8')
        return im, draw
    def write(im, seconds):
        frame = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
        for _ in range(round(seconds*fps)): writer.write(frame)
    im, draw = canvas('전북 고속도로 온도·결빙 분석', '수정본 20261007 · 비공개 제출 검토용 · 실제 실행 로그와 결과 설명')
    for i, line in enumerate(['개발 14개 관측소 / 보호 3개 관측소 분리', '과거 AWS·ASOS와 같은 노선 RWIS를 결합', '467개 구간 × 34,560시각 = 16,139,520행', '고정 평가: 온도 MAE 0.930°C', '결빙 분류: TP 0 / FP 3 / FN 64 → 탐지 실패', '이 영상은 실패 결과와 적용 한계도 함께 보여줍니다.']):
        draw.text((60, 175+i*66), line, font=font, fill='#f8fafc' if i != 4 else '#fda4af')
    write(im, 6); im.save(out / 'demo_frame_intro.png')
    for count in range(1, len(events)+1):
        im, draw = canvas('저장 모델로 하루 144행 추론', '실제 명령 출력 · 가독성을 위해 느리게 재생 · 원본 시간 기록은 actual_execution.json')
        visible = events[max(0,count-12):count]
        for i, event in enumerate(visible): draw.text((42, 156+i*39), event['text'], font=small, fill='#d1fae5')
        write(im, 1.)
    im.save(out / 'demo_frame_inference.png'); write(im, 3)
    plot = Image.open(ROOT / 'outputs/private/segment_condition_proposal/condition_exposure_sensitivity.png').convert('RGB')
    plot.thumbnail((1200, 510))
    im, draw = canvas('온도 오차에 따른 조건 노출 변화', '추정온도 ≤0°C + 과거 강수/이슬점 조건 · 실제 결빙 지속시간이나 사고 위험등급이 아님')
    im.paste(plot, ((width-plot.width)//2, 145)); write(im, 7); im.save(out / 'demo_frame_map.png')
    im, draw = canvas('해석과 제출 전 확인', '모델·임계값을 고정한 뒤 보호 지점 평가 · 평가 결과에 맞춘 재조정 없음')
    for i, line in enumerate(['온도 추정과 결빙 탐지 성능은 구분해야 합니다.', 'DSM 고도는 도로면 고도와 다르며 구간 분류는 탐색적입니다.', '공식 이정·상하행·기존 취약구간 대응은 미확정입니다.', '지도는 시설·기상 조건의 현장 확인을 돕는 분석 자료입니다.', '운영 경보 적용·수상 가능성·사고 감소 효과는 입증하지 못했습니다.']):
        draw.text((60, 180+i*72), line, font=font, fill='#f8fafc')
    write(im, 7); writer.release()
    capture = cv2.VideoCapture(str(path)); frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)); duration = frames/capture.get(cv2.CAP_PROP_FPS)
    assert capture.isOpened() and frames > 0
    for index in (0, frames//2, frames-1):
        capture.set(cv2.CAP_PROP_POS_FRAMES, index); success, decoded = capture.read()
        if not success or decoded.shape[:2] != (height, width): raise AssertionError('Video decode verification failed')
    capture.release()
    (out / 'video_manifest.json').write_text(json.dumps({'status': 'actual_command_log_replay_and_results', 'width': width, 'height': height, 'fps': fps, 'frames': frames, 'duration_seconds': duration, 'codec': 'mp4v', 'verified_decoded_frames': 3, 'not_a_screen_capture': True}, indent=2), encoding='utf-8')
    print(f'Video verified: {frames} frames / {duration:.1f}s', flush=True)


if __name__ == '__main__': main()
