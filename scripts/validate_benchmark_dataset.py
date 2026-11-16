"""Offline schema/gold/absence audit of the Day 07 dataset, never evaluation."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.benchmark_data import load_offline_snapshot,validate_dataset,validate_absence_approval,sha


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--day6-root',type=Path,required=True)
    parser.add_argument('--benchmark-dir',type=Path,default=Path('data/benchmark'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Audit output exists; preserve evidence')
    chunks,pages,identity=load_offline_snapshot(args.day6_root)
    manifest_raw=(args.benchmark_dir/'manifest.json').read_bytes()
    manifest=json.loads(manifest_raw)
    if manifest.get('review_status')=='ACCEPTED':
        pin=(args.benchmark_dir/'manifest.sha256').read_text(encoding='utf-8').split()
        if pin!=[sha(manifest_raw),'manifest.json']:raise ValueError('FROZEN_MANIFEST_PIN_MISMATCH')
    if manifest['identity']!=identity:raise ValueError('BENCHMARK_MANIFEST_IDENTITY_MISMATCH')
    splits={}
    for split in ('dev','test'):
        raw=(args.benchmark_dir/f'{split}.json').read_bytes()
        if sha(raw)!=manifest['files_sha256'][f'{split}.json']:raise ValueError('DATASET_FILE_HASH_MISMATCH')
        splits[split]=json.loads(raw)
    report=validate_dataset(splits['dev'],splits['test'],chunks,pages,identity)
    report['errors'].extend(validate_absence_approval(splits['dev'],splits['test'],manifest,identity))
    if report['errors']:
        report.update(status='FAIL',schema_and_integrity='FAIL',ready_for_milestone5b=False)
    report['manifest_sha256']=sha((args.benchmark_dir/'manifest.json').read_bytes())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:report[k] for k in ('status','schema_and_integrity','counts','ready_for_milestone5b')}))
    return 1 if report['errors'] else 0


if __name__=='__main__':sys.exit(main())
