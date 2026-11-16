"""Recover cached wheels without network or writes to Day 06. Run in WSL."""
import argparse
import email
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--day6-root', type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true', help='Recover/verify wheels without installing')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    wheelhouse = root / 'data/local/wheelhouse'
    wheelhouse.mkdir(parents=True, exist_ok=True)
    records = []
    lock = (args.day6_root / 'starter/requirements-stage4-linux-py312.lock').read_text()
    approved_hashes = set(re.findall(r'--hash=sha256:([0-9a-f]{64})', lock))
    caches = [args.day6_root / 'data/local/stage4/pip-cache', Path.home() / '.cache/pip']
    for body in (p for cache in caches for p in cache.rglob('*.body')):
        if not zipfile.is_zipfile(body):
            continue
        with zipfile.ZipFile(body) as archive:
            metadata = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
            if len(metadata) != 1:
                continue
            prefix = metadata[0].rsplit('/', 1)[0]
            info = email.message_from_bytes(archive.read(metadata[0]))
            wheel = email.message_from_bytes(archive.read(prefix + '/WHEEL'))
            tag = wheel.get_all('Tag')[0]
            name = info['Name'].replace('-', '_')
            target = wheelhouse / f"{name}-{info['Version']}-{tag}.whl"
        with body.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest not in approved_hashes:
            continue
        if not target.exists():
            shutil.copyfile(body, target)
        with target.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                raise ValueError('Wheelhouse checksum mismatch: ' + target.name)
        records.append(dict(file=target.name, sha256=digest))
    (wheelhouse.parent / 'wheel_inventory.json').write_text(json.dumps(records, indent=2) + '\n')
    for target in wheelhouse.glob('*.whl'):
        with target.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() not in approved_hashes:
                raise ValueError('Unapproved wheel: ' + target.name)
    if args.verify_only:
        print(json.dumps(dict(verified_wheels=len(records))))
        return
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-compile', '--no-index',
                    '--require-hashes', '--find-links', str(wheelhouse),
                    '-r', str(root / 'requirements-dense.lock')], check=True)


if __name__ == '__main__':
    main()
