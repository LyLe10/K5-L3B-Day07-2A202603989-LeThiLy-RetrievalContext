"""Hash source/data/model files before/after. Excludes runtime caches and Git internals."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def inventory(root):
    records = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in
                   ['.venv','venv','pip-cache','.git','.pytest_cache','__pycache__']]
        for name in files:
            path = Path(base) / name
            if path.is_symlink():
                continue
            with path.open('rb') as stream:
                records[str(path.relative_to(root))] = hashlib.file_digest(stream,'sha256').hexdigest()
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--day6-root', required=True, type=Path)
    parser.add_argument('--before', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    after = inventory(args.day6_root)
    before = json.loads(args.before.read_text())
    changes = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    report = dict(status='PASS' if not changes else 'FAIL',files_checked=len(before),
                  files_after=len(after),changed_paths=changes,
                  exclusions=['.venv','venv','pip-cache','.git','.pytest_cache','__pycache__'])
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    if changes:raise SystemExit(1)


if __name__=='__main__':main()
