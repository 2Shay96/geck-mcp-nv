"""CLI over the same journaled Service runtime operations as MCP."""
import argparse
import json
from pathlib import Path
import sys
import time

from geck_mcp.config import Project
from geck_mcp.service import Service


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    sub = parser.add_subparsers(dest='mode', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--profile', required=True, type=Path)
    prep.add_argument('--save-label', required=True)
    prep.add_argument('--runtime-mapping', required=True, type=Path)
    prep.add_argument('--expected-plugin-hash', required=True)
    prep.add_argument('--request-key', required=True)
    prep.add_argument('--preview', action='store_true')
    collect = sub.add_parser('collect')
    collect.add_argument('session')
    collect.add_argument('--checkpoint-label', required=True)
    collect.add_argument('--watch-seconds', type=float, default=0)
    report = sub.add_parser('report')
    report.add_argument('session')
    report.add_argument('--baseline-checkpoint')
    report.add_argument('--sanitized', action='store_true')
    close = sub.add_parser('close')
    close.add_argument('session')
    close.add_argument('--request-key', required=True)
    close.add_argument('--archive-helpers', action='store_true')
    close.add_argument('--game-exited', action='store_true')
    args = vars(parser.parse_args(argv))
    project = Project.load(args.pop('project'))
    mode = args.pop('mode')
    key = args.pop('request_key', None)
    seconds = args.pop('watch_seconds', 0)
    if not 0 <= seconds <= 60:
        parser.error('--watch-seconds must be 0..60')
    if mode == 'prepare':
        for field in ('profile', 'runtime_mapping'):
            args[field] = json.loads(args[field].read_text(encoding='utf-8'))
    service = Service(project)
    deadline = time.monotonic() + seconds
    while True:
        result = service.runtime_call(mode, args, key)
        if (mode != 'collect' or not result['ok'] or result['data'].get('status') != 'awaiting_output'
                or time.monotonic() >= deadline):
            break
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))
    print(json.dumps(result))
    data = result.get('data') or {}
    return 1 if not result['ok'] or data.get('status') in ('error', 'errored') else 2 if data.get('status') in (
        'awaiting_output', 'partial') or data.get('assertions') == 'inconclusive' else 3 if data.get('assertions') == 'fail' else 0


if __name__ == '__main__':
    sys.exit(main())
