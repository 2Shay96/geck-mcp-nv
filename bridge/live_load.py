"""Load a project's plugin in GECK through the bridge and wait until it is verified.

    .venv/bin/python live_load.py --project projects/coolworld.json [--timeout 780] [--if-needed]

Uses the same Service the MCP server uses (persistent worker). Prints each poll and
writes evidence/live-load-<operation>.json. Loading FalloutNV.esm takes minutes.
Exit 0 when the load ends loaded_verified, or loaded_unverified (the plugin is active but the cell
check could not run; the last line says why). --if-needed skips the load when this GECK session already
loaded the same plugin bytes through the bridge and has no unsaved changes.
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


def poll_observation(result):
    """Transient helper evidence can be a list; only nested load dicts carry state."""
    data = result.get('data') if isinstance(result.get('data'), dict) else {}
    load = data.get('load') if isinstance(data.get('load'), dict) else {}
    error = result.get('error') if isinstance(result.get('error'), dict) else {}
    transient = error.get('code') in ('EDITOR_BUSY', 'EDITOR_UNRESPONSIVE')
    outcome = load.get('outcome', 'loading' if transient or result.get('outcome') in ('pending', 'outcome_unknown') else None)
    terminal = (not result.get('ok') and not transient) or outcome in ('loaded_verified', 'loaded_unverified')
    return data, outcome, terminal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=780)
    parser.add_argument('--if-needed', action='store_true',
                        help='skip when GECK already has these exact plugin bytes loaded')
    parser.add_argument('--operation-id', help='Resume polling the original load; never dispatch another load')
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
        if (args.if_needed and state['editorTitle'] == loaded_title and not state['unsavedChanges']
                and service.loaded_plugin(state['sessionId']) == snapshot['sha256']):
            print(json.dumps({'skipped': 'GECK already has this plugin loaded', 'sha256': snapshot['sha256'],
                              'outcome': 'already_loaded'}))
            return 0
        load = service.operation(args.operation_id) if args.operation_id else service.load_plugin(
            state['sessionId'], state['editorTitle'], snapshot['sha256'],
            'live-load-' + str(uuid.uuid4()), reload=state['editorTitle'] == loaded_title)
        released = (load.get('data') or {}).get('releasedStaleOperations') if isinstance(load.get('data'), dict) else None
        print(json.dumps({'load': {k: load.get(k) for k in ('ok', 'outcome', 'operationId', 'error')},
                          **({'releasedStaleOperations': released} if released else {})}), flush=True)
        if not load['ok']:
            return 2
        if load['outcome'] != 'loading':
            return 0
        delay, result = 3, None
        while time.monotonic() - started < args.timeout:
            time.sleep(delay)
            delay = min(delay * 1.5, 5)
            result = service.load_status(load['operationId'])
            data, outcome, terminal = poll_observation(result)
            print(json.dumps({'t': round(time.monotonic() - started), 'ok': result['ok'], 'outcome': outcome,
                              'observation': data.get('lastObservation'),
                              'error': result.get('error')}), flush=True)
            if terminal:
                break
        evidence = ROOT / 'evidence' / ('live-load-%s.json' % load['operationId'])
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps({'load': load, 'final': result,
                                        'seconds': round(time.monotonic() - started)}, indent=1) + '\n')
        final_data = (result or {}).get('data')
        load_data = final_data.get('load', {}) if isinstance(final_data, dict) else {}
        if not isinstance(load_data, dict): load_data = {}
        print(json.dumps({'outcome': outcome, 'verification': (load_data['data'].get('verification') if isinstance(load_data.get('data'), dict) else None),
                          'evidence': str(evidence), 'seconds': round(time.monotonic() - started)}))
        return 0 if result and result['ok'] and outcome in ('loaded_verified', 'loaded_unverified') else 3
    finally:
        service.close()


if __name__ == '__main__':
    sys.exit(main())
