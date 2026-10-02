"""Load a project's plugin in GECK through the bridge and wait until it is verified.

    .venv/bin/python live_load.py --project projects/coolworld.json [--timeout 780]

Uses the same Service the MCP server uses (persistent worker). Prints each poll and
writes evidence/live-load-<operation>.json. Loading FalloutNV.esm takes minutes.
"""
import argparse
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from esp_check import file_snapshot  # noqa: E402
from geck_mcp.config import Project  # noqa: E402
from geck_mcp.service import Service  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=780)
    args = parser.parse_args()
    project = Project.load(args.project)
    service = Service(project)
    started = time.monotonic()
    try:
        status = service.status()
        print(json.dumps({'status': {k: status['data'].get(k) for k in ('editorTitle', 'sessionId', 'unsavedChanges')}
                          if status['ok'] else status['error']}), flush=True)
        if not status['ok']:
            return 2
        state = status['data']
        snapshot, _ = file_snapshot(project.plugin_path)
        loaded_title = 'Garden of Eden Creation Kit - [%s]' % project.plugin
        load = service.load_plugin(state['sessionId'], state['editorTitle'], snapshot['sha256'],
                                   'live-load-' + str(uuid.uuid4()), reload=state['editorTitle'] == loaded_title)
        print(json.dumps({'load': {k: load.get(k) for k in ('ok', 'outcome', 'operationId', 'error')}}), flush=True)
        if not load['ok']:
            return 2
        if load['outcome'] != 'loading':
            return 0
        delay, result = 3, None
        while time.monotonic() - started < args.timeout:
            time.sleep(delay)
            delay = min(delay * 1.5, 5)
            result = service.load_status(load['operationId'])
            data = result.get('data') or {}
            outcome = (data.get('load') or {}).get('outcome')
            print(json.dumps({'t': round(time.monotonic() - started), 'ok': result['ok'], 'outcome': outcome,
                              'observation': data.get('lastObservation'),
                              'error': result.get('error')}), flush=True)
            if not result['ok'] or outcome == 'loaded_verified':
                break
        evidence = ROOT / 'evidence' / ('live-load-%s.json' % load['operationId'])
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps({'load': load, 'final': result,
                                        'seconds': round(time.monotonic() - started)}, indent=1) + '\n')
        print(json.dumps({'evidence': str(evidence), 'seconds': round(time.monotonic() - started)}))
        return 0 if result and result['ok'] and outcome == 'loaded_verified' else 3
    finally:
        service.close()


if __name__ == '__main__':
    sys.exit(main())
