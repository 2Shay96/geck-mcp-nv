"""Build a reproducible source-only download from a committed Git revision."""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tomllib
import zipfile

PREFIX = 'GECK-MCP-for-New-Vegas/'
ROOT_FILES = {'README.md', 'CHANGELOG.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md'}
SOURCE_SUFFIXES = {'.py', '.cs', '.c', '.h', '.json', '.toml', '.txt', '.md', '.swift'}
# These regression modules require the game-derived fixtures omitted from downloads.
FIXTURE_TESTS = {f'bridge/tests/test_{name}.py' for name in
                 ('authoring', 'build', 'codec', 'records', 'validate')}


def included(name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
        raise ValueError('unsafe archive path')
    if name in ROOT_FILES:
        return True
    if not p.parts or p.parts[0] not in {'bridge', 'windows', 'docs', 'tools'}:
        return False
    if any(part in {'state', 'build', 'evidence', 'photos', 'fixtures', '.venv',
                    '__pycache__', 'backups', 'screenshots'} for part in p.parts):
        return False
    if name in FIXTURE_TESTS:
        return False
    if p.parts[:2] == ('bridge', 'projects') and not p.name.startswith('example-'):
        return False
    return p.suffix in SOURCE_SUFFIXES


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def package(repo, revision, output):
    repo, output = Path(repo), Path(output)
    if output.suffix.lower() != '.zip':
        raise ValueError('output must be a .zip path')
    manifest_path = output.with_suffix('.json')
    if output.exists() or manifest_path.exists():
        raise FileExistsError('archive or manifest already exists; choose a new output')
    commit = git(repo, 'rev-parse', '--verify', revision + '^{commit}').decode().strip()
    source = zipfile.ZipFile(io.BytesIO(git(repo, 'archive', '--format=zip', commit)))
    files, excluded = {}, []
    for item in source.infolist():
        if item.is_dir():
            continue
        if not included(item.filename):
            excluded.append(item.filename)
            continue
        if (item.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError('source symlinks are not supported')
        files[item.filename] = source.read(item)
    version = tomllib.loads(files['bridge/pyproject.toml'].decode())['project']['version']
    module = ast.parse(files['bridge/geck_mcp/__init__.py'].decode())
    declared = [ast.literal_eval(n.value) for n in module.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == '__version__' for t in n.targets)]
    if declared != [version] or f'(v{version})' not in files['README.md'].decode():
        raise ValueError('release version markers disagree')
    with output.open('xb') as target, zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(PREFIX + name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    manifest = {'version': version, 'sourceCommit': commit, 'archive': output.name,
                'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                'size': output.stat().st_size, 'files': len(files),
                'excluded': sorted(excluded), 'publication': 'local-only'}
    with manifest_path.open('x', encoding='utf-8') as target:
        json.dump(manifest, target, indent=2)
        target.write('\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--revision', required=True, help='committed source revision')
    parser.add_argument('--output', type=Path, required=True, help='new .zip path; never overwritten')
    args = parser.parse_args()
    print(json.dumps(package(args.repo, args.revision, args.output), indent=2))
