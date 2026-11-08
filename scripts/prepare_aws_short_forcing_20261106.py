"""ASOS와 구분한 AWS의 단기 이력 후보를 같은 사전 검증 절차로 준비한다."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    s=(ROOT/'scripts/evaluate_short_forcing_icing_20261106.py').read_text('utf8')
    s=s.replace('from src.short_forcing_icing_20261106 import features,TAUS','from src.aws_short_forcing_20261106 import features,TAUS')
    s=s.replace("W=P/'short_forcing_icing_20261106';DATA=P/'blind_icing_20261025_v2/training.parquet'","W=P/'aws_short_forcing_icing_20261106';DATA=P/'icing_local_context_inputs_20261106/training.parquet'")
    s=s.replace("ROOT/'src/short_forcing_icing_20261106.py'","ROOT/'src/aws_short_forcing_20261106.py'")
    s=s.replace("['asos_air_temp','asos_ground_temp','asos_dewpoint_obs']","['aws_air_temp','aws_humidity','aws_wind_speed','aws_rain_15m']")
    s=s.replace('ASOS air/ground temperature proxies, not observed road temperature or a replication of the paper. Current 10-min Ice classification, not future onset forecasting.','Nearby AWS cooling/thaw/drying/rain proxies plus current ASOS. No observed pavement state/temperature. Not a replication of the paper or future-onset forecast. ASOS was hourly; use existing more frequent AWS source with strict age>0 and <=60min.')
    s=s.replace('cold/thaw/deposition proxy/crossings','AWS cold/thaw/drying proxy/rain proxy')
    s=s.replace("status='short_forcing_nested_complete'","status='aws_short_forcing_nested_complete'")
    p=ROOT/'scripts/evaluate_aws_short_forcing_20261106.py';assert not p.exists();p.write_text(s,'utf8')
    s=(ROOT/'scripts/audit_short_forcing_20261106.py').read_text('utf8')
    s=s.replace('src.short_forcing_icing_20261106','src.aws_short_forcing_20261106').replace("W=ROOT/'outputs/private/short_forcing_icing_20261106'","W=ROOT/'outputs/private/aws_short_forcing_icing_20261106'")
    s=s.replace("f['asos_air_temp']=-2.;f['asos_ground_temp']=-3.;f['asos_dewpoint_obs']=-1.","f['asos_air_temp']=-2.;f['asos_ground_temp']=-3.;f['asos_dewpoint_obs']=-1.;f['aws_air_temp']=-2.;f['aws_humidity']=80.;f['aws_wind_speed']=1.;f['aws_rain_15m']=0.;f['aws_dewpoint']=-4.;f['aws_age_minutes']=10.")
    s=s.replace("other['asos_air_temp']=40","other['aws_air_temp']=40")
    s=s.replace("ROOT/'outputs/private/blind_icing_20261025_v2/training.parquet'","ROOT/'outputs/private/icing_local_context_inputs_20261106/training.parquet'")
    p=ROOT/'scripts/audit_aws_short_forcing_20261106.py';assert not p.exists();p.write_text(s,'utf8')
if __name__=='__main__':main()
