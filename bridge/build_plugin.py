"""Build a plugin from a spec, offline. Never touches the game's Data folder.

    python3 build_plugin.py projects/coolworld.spec.json [--adopt existing.esp] [--compare other.esp]
    python3 build_plugin.py --project projects/my_mod.json [--dry-run]

Outputs <state>/../build/<Plugin>.esp and <Plugin>.receipt.json (the same folder the MCP tools use),
and saves the project's FormID map in <state>/formids/<project_id>.json. <state> is --state, else the
--project profile's state_dir, else this folder's state/. Record templates and master indexes are read
from <state> first, then from this folder's state/. --adopt seeds FormIDs from a hand-built plugin
(first build only). --compare prints a record-level diff. Standard library only (plus pydantic with
--project).
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from geck_mcp.authoring import index_files  # noqa: E402
from geck_mcp.esp import build as builder, diff, generic  # noqa: E402
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
    parser.add_argument('spec', type=Path, nargs='?', help='spec file (default: the --project profile\'s spec)')
    parser.add_argument('--project', type=Path, help='project profile: supplies spec, state folder and Data folder')
    parser.add_argument('--adopt', type=Path, help='seed FormIDs from an existing plugin')
    parser.add_argument('--compare', type=Path, help='diff the result against another plugin')
    parser.add_argument('--out', type=Path, help='output folder (default: <state>/../build)')
    parser.add_argument('--state', type=Path, help='state folder (default: the profile\'s state_dir, else ./state)')
    parser.add_argument('--dry-run', action='store_true', help='do not save the FormID map or outputs')
    parser.add_argument('--no-assets', action='store_true', help='skip mesh/texture checks')
    args = parser.parse_args()
    project = None
    if args.project:
        from geck_mcp.config import Project
        project = Project.load(args.project)
    args.spec = args.spec or (project.spec if project and project.spec else None)
    if args.spec is None:
        parser.error('give a spec file, or --project with a profile that has "spec"')
    args.state = args.state or (project.state_dir if project else ROOT / 'state')
    args.out = args.out or args.state.parent / 'build'
    try:
        spec = builder.load_spec(args.spec.read_text())
        formids = FormIdMap(args.state / 'formids' / (spec['project_id'] + '.json'), spec['plugin'])
        if args.adopt:
            if formids.assigned or formids.retired:
                raise SpecError('--adopt', 'FormID map already exists; adoption is only for the first build')
            adopted = builder.adopt_existing(formids, spec, args.adopt.read_bytes())
            print(json.dumps({'adopted': len(adopted)}))
        index = MasterIndex(index_files(args.state, spec['masters']))
        data, receipt = builder.build(spec, formids, index, base_dir=args.spec.resolve().parent,
                                      script_cache=load_cache(args.state, spec['project_id']),
                                      templates=generic.template_dirs(args.state))
    except (SpecError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 2
    data_dir = None
    if not args.no_assets:
        data_dir = project.game_root / 'Data' if project and (project.game_root / 'Data').is_dir() else data_dir_for(spec)
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
    summary['out'] = None if args.dry_run else str(args.out)
    summary['validation'] = {'checked': receipt['validation']['checked'],
                             'warnings': receipt['validation']['warnings']}
    if args.compare:
        summary['differences'] = len(receipt['differences'])
    print(json.dumps(summary))
    return 0


if __name__ == '__main__':
    sys.exit(main())
