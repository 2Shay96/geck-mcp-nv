"""Build a plugin from a spec, offline. Never touches the game's Data folder.

    python3 build_plugin.py projects/coolworld.spec.json [--adopt existing.esp] [--compare other.esp]

Outputs build/<Plugin>.esp and build/<Plugin>.receipt.json, and saves the
project's FormID map in state/formids/<project_id>.json. --adopt seeds FormIDs
from a hand-built plugin (first build only). --compare prints a record-level diff.
Standard library only.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from geck_mcp.esp import build as builder, diff  # noqa: E402
from geck_mcp.esp.formids import FormIdMap, MasterIndex  # noqa: E402
from geck_mcp.esp.records import SpecError  # noqa: E402
from geck_mcp.esp.validate import validate  # noqa: E402
from geck_mcp.esp.assets import AssetIndex  # noqa: E402
from geck_mcp.esp.scripts import load_cache  # noqa: E402


def data_dir_for(spec):
    config = ROOT / 'projects' / (spec['project_id'] + '.json')
    if config.exists():
        data = Path(json.loads(config.read_text())['game_root']) / 'Data'
        if data.is_dir():
            return data
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('spec', type=Path)
    parser.add_argument('--adopt', type=Path, help='seed FormIDs from an existing plugin')
    parser.add_argument('--compare', type=Path, help='diff the result against another plugin')
    parser.add_argument('--out', type=Path, default=ROOT / 'build')
    parser.add_argument('--state', type=Path, default=ROOT / 'state')
    parser.add_argument('--dry-run', action='store_true', help='do not save the FormID map or outputs')
    parser.add_argument('--no-assets', action='store_true', help='skip mesh/texture checks')
    args = parser.parse_args()
    try:
        spec = builder.load_spec(args.spec.read_text())
        formids = FormIdMap(args.state / 'formids' / (spec['project_id'] + '.json'), spec['plugin'])
        if args.adopt:
            if formids.assigned or formids.retired:
                raise SpecError('--adopt', 'FormID map already exists; adoption is only for the first build')
            adopted = builder.adopt_existing(formids, spec, args.adopt.read_bytes())
            print(json.dumps({'adopted': len(adopted)}))
        index_files = [args.state / 'index' / (m + '.json.gz') for m in spec['masters']]
        index = MasterIndex([p for p in index_files if p.exists()])
        data, receipt = builder.build(spec, formids, index, base_dir=args.spec.resolve().parent,
                                      script_cache=load_cache(args.state, spec['project_id']))
    except (SpecError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 2
    data_dir = None if args.no_assets else data_dir_for(spec)
    assets = AssetIndex(data_dir) if data_dir else None
    receipt['validation'] = validate(data, index, assets, spec['masters'])
    if assets is None:
        receipt['validation']['warnings'].append('asset checks skipped (game Data folder not available)')
    if not receipt['validation']['ok']:
        print(json.dumps({'ok': False, 'error': 'validation failed', 'validation': receipt['validation']}))
        return 3
    if args.compare:
        receipt['comparedWith'] = str(args.compare)
        receipt['differences'] = diff.diff(args.compare.read_bytes(), data)
    if not args.dry_run:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / spec['plugin']).write_bytes(data)
        (args.out / (Path(spec['plugin']).stem + '.receipt.json')).write_text(json.dumps(receipt, indent=1) + '\n')
        formids.save()
    summary = {k: receipt[k] for k in ('plugin', 'sha256', 'size', 'recordCounts', 'hedrCount', 'warnings')}
    summary['ok'] = True
    summary['validation'] = {'checked': receipt['validation']['checked'],
                             'warnings': receipt['validation']['warnings']}
    if args.compare:
        summary['differences'] = len(receipt['differences'])
    print(json.dumps(summary))
    return 0


if __name__ == '__main__':
    sys.exit(main())
