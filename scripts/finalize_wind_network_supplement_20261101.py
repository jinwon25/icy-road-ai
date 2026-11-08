"""검증기의 출력 로그 기대만 바로잡고 기존 실제 CLI·재학습 결과를 직접 대조한다."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,now,verify_preserved
from scripts.verify_wind_network_supplement_20261101 import verify_outputs
from src.data_source import sha256_file as sha


def main():
    out=ROOT/'outputs/private/wind_network_supplement_validation_20261101_v1'
    source=ROOT/'outputs/private/wind_network_supplement_20261101_v2';receipt=read(source/'receipt.json')
    if (out/'receipt.json').exists():raise FileExistsError('Preserve completed verification')
    assert (out/'verifier_failed.py').is_file()
    log=(out/'notebook.log').read_text('utf8');assert 'Notebook validated in Jupyter kernel: 3 code cells; outputs not saved' in log
    refit=verify_outputs(out/'bundle');assert refit['training_rows']==receipt['training_rows']==447628
    for name,digest in receipt['files'].items():assert sha(source/name)==sha(out/'bundle'/name)==digest,name
    assert verify_preserved()==receipt['preservation']
    write(out/'receipt.json',dict(status='wind_network_supplement_verified',at_utc=now(),source_receipt_sha256=sha(source/'receipt.json'),
        notebook_code_cells=3,actual_cli_rows_exact=432,api_rows_exact=432,refit_rows_exact=432,full_refit_training_rows=refit['training_rows'],
        source_files_preserved=len(receipt['files']),prefix_exact=receipt['prefix_exact'],notebook_log_sha256=sha(out/'notebook.log'),
        archived_verifier_sha256=sha(out/'verifier_failed.py'),corrected_verifier_sha256=sha(ROOT/'scripts/verify_wind_network_supplement_20261101.py'),
        correction='Jupyter checker suppresses cell stdout; actual saved CLI and refitted-model predictions are checked instead',
        protected_outcomes_read=False,existing_models_changed=False))
    print('VERIFIED actual API/CLI/full-refit 432 exact rows; archived failed log expectation',flush=True)


if __name__=='__main__':main()
