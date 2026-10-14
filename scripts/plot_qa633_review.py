"""지표별 날짜 분모와 잘못된 교집합 평균의 F1 부풀림을 시각화한다."""
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import read


def main():
    out = ROOT / 'outputs/private/qa633_development_20261013_v1'; s = read(out / 'summary.json'); a = read(out / 'independent_verification.json')
    assert a['status'] == 'independent_qa633_metrics_audit_passed' and a['summary_sha256'] == sha(out / 'summary.json')
    destination = ROOT / 'docs/images/qa633_review_20261013.png'
    if destination.exists(): raise FileExistsError('Preserve reviewed figure')
    plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False, 'font.size': 11})
    names = ['original', 'equal_distance_mse_mae300', 'equal_nohistory_pair', 'catboost400']
    labels = ['기존 분류', '기존 온도3종 평균', '기상12·2종 평균', 'CatBoost400']
    fig, axes = plt.subplots(1, 2, figsize=(13, 6)); x = np.arange(4)
    for metric, offset, color in [('precision', -.25, '#7c8ea3'), ('recall', 0., '#c59c51'), ('f1', .25, '#4b8f83')]:
        values = [s['reports'][n]['144'][metric+'_days'] for n in names]
        bars = axes[0].bar(x+offset, values, .23, color=color, label=metric)
        axes[0].bar_label(bars, padding=3, fontsize=9)
    axes[0].set_xticks(x, labels, rotation=15); axes[0].set_ylim(0, 720); axes[0].set_ylabel('평균에 포함한 날짜·지점 쌍'); axes[0].set_title('Precision·Recall·F1의 분모는 서로 다르다'); axes[0].legend(); axes[0].grid(axis='y', alpha=.15)
    comparison = pd.read_csv(out / 'wrong_intersection_comparison.csv').set_index('method'); ix = np.arange(3)
    chosen = ['original', 'equal_distance_mse_mae300', 'equal_nohistory_pair']
    for key, offset, color, label in [('correct_f1', -.18, '#4b8f83', '지표별 분모·미탐일F1=0'), ('wrong_joint_defined_f1', .18, '#b86c57', '잘못된P/R 교집합 평균')]:
        values = comparison.loc[chosen, key].to_numpy()
        bars = axes[1].bar(ix+offset, values, .34, color=color, label=label); axes[1].bar_label(bars, fmt='%.4f', padding=3, fontsize=10)
    axes[1].set_xticks(ix, labels[:3], rotation=15); axes[1].set_ylim(0, .135); axes[1].set_ylabel('일별F1의 지점 평균'); axes[1].set_title('미탐일·오경보일을 빼면 점수가 부풀려진다'); axes[1].legend(fontsize=9, loc='upper left'); axes[1].grid(axis='y', alpha=.15)
    fig.suptitle('10월13일 Q&A633 답변을 고정 개발 예측에 반영한 검산', fontsize=15)
    fig.text(.5, .025, '첫 겨울 개발9곳·21개 고정 판정 · 144유효슬롯 조건은 잠정 · 새 독립/공식 점수가 아님', ha='center', fontsize=11)
    fig.tight_layout(rect=(0, .1, 1, .92)); fig.savefig(destination, dpi=160); plt.close(fig); print(destination)


if __name__ == '__main__': main()
