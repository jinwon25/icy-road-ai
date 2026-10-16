"""모델 카드에 전체 행과 지점 균등 온도 지표를 실제 예측에서 계산한다."""
from src.method_blending import domain
from src.temperature_transfer import regression_report


def temperature_evidence(frame, column='equal_nohistory_pair'):
    domain(frame)
    report = regression_report(frame, frame[column])
    if report['pooled']['n'] == 0 or any(v['n'] == 0 for v in report['stations'].values()):
        raise ValueError('Temperature evidence must cover every declared station')
    return {
        'temperature_valid_rows': report['pooled']['n'],
        'temperature_stations': len(report['stations']),
        'temperature_mae_pooled': report['pooled']['mae'],
        'temperature_mae_station_mean': report['station_macro']['mae'],
        'temperature_aggregation': 'pooled=mean absolute error over valid rows; station_mean=unweighted mean of within-station MAEs',
    }
