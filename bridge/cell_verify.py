"""Tier-3 check: does GECK's Cell View show exactly the references the build receipt promises?

    .venv/bin/python cell_verify.py --project projects/coolworld.json --cell CoolWorld [--frame salvatore]

--frame <ref_id> also loads the cell in the Render Window and selects that reference
(double-click in Cell View), so the camera frames it. Visual correctness still needs a human.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from geck_mcp.config import Project  # noqa: E402
from geck_mcp.service import Service  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--cell', required=True)
    parser.add_argument('--frame', metavar='REF_ID')
    args = parser.parse_args()
    project = Project.load(args.project)
    receipt = json.loads((ROOT / 'build' / (Path(project.plugin).stem + '.receipt.json')).read_text())
    frame = None
    if args.frame:
        refs = [r for r in receipt['references'].get(args.cell, []) if r['refId'] == args.frame]
        if len(refs) != 1:
            print(json.dumps({'ok': False, 'error': 'ref_id %r not in receipt for %s' % (args.frame, args.cell)}))
            return 2
        frame = refs[0]['formId']
    service = Service(project)
    try:
        status = service.status()
        if not status['ok']:
            print(json.dumps(status))
            return 2
        result = service.cell_verify(args.cell, status['data']['sessionId'], receipt, frame)
    finally:
        service.close()
    evidence = ROOT / 'evidence' / ('cell-verify-%s.json' % result['operationId'])
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(result, indent=1) + '\n')
    data = result.get('data') or {}
    match = data.get('match') or {}
    print(json.dumps({'ok': result['ok'], 'error': result.get('error'),
                      'match': {k: match.get(k) for k in ('expected', 'shown', 'matched', 'missing')},
                      'columns': data.get('columns'), 'camera': (data.get('camera') or {}).get('renderTitle'),
                      'evidence': str(evidence)}))
    return 0 if result['ok'] else 3


if __name__ == '__main__':
    sys.exit(main())
