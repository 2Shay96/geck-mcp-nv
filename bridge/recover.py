"""List or clear recovery barriers (uncertain operations that block editor work).

    python recover.py --project projects/my_mod.json --list
    python recover.py --project projects/my_mod.json --ack <operation-id> --note "what you checked"
    python recover.py --project projects/my_mod.json --release-stale

--list shows every unresolved operation for this GECK install with the GECK session it ran against, and the
current session. Barriers from an earlier GECK session are released automatically by the next editor call
(state "stale"); --release-stale does that now. --ack clears one barrier after you looked at GECK and the
plugin on disk, like the geck_recovery_acknowledge MCP tool (it checks the running editor and the plugin
hash). If GECK is not running, add --offline to record the acknowledgement without the editor check.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from esp_check import file_snapshot  # noqa: E402
from geck_mcp.config import Project  # noqa: E402
from geck_mcp.service import UNRESOLVED, Service  # noqa: E402


def describe(service, row):
    return {'operationId': row['id'], 'operation': row['name'], 'state': row['state'],
            'started': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(row['started'] or 0)),
            'session': service.operation_session(row), 'requestKey': row['request_key']}


def plugin_hash(project):
    try:
        return file_snapshot(project.plugin_path)[0]['sha256']
    except FileNotFoundError:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--project', type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--list', action='store_true')
    action.add_argument('--ack', metavar='OPERATION_ID')
    action.add_argument('--release-stale', action='store_true')
    parser.add_argument('--note', help='what you checked (12+ characters); required with --ack')
    parser.add_argument('--offline', action='store_true', help='with --ack: GECK is not running; skip the editor check')
    args = parser.parse_args()
    project = Project.load(args.project)
    service = Service(project)
    try:
        current = service.current_session()
        if args.list:
            rows = [describe(service, r) for r in service.unresolved()]
            print(json.dumps({'currentSession': current, 'pluginSha256': plugin_hash(project),
                              'unresolved': rows,
                              'hint': None if not rows else
                              'Barriers whose session differs from currentSession are released by the next '
                              'editor call or --release-stale. Others: inspect, then --ack ID --note ...'},
                             indent=1))
            return 0
        if args.release_stale:
            released, blocking = service.release_stale()
            print(json.dumps({'currentSession': current, 'released': released,
                              'stillBlocking': [describe(service, r) for r in blocking]}, indent=1))
            return 0 if not blocking else 1
        if not args.note or len(args.note) < 12:
            parser.error('--ack needs --note with at least 12 characters')
        expected = plugin_hash(project)
        if not args.offline:
            if current is None:
                print(json.dumps({'ok': False, 'error': 'GECK is not running or not answering. Start it, or use '
                                  '--offline to acknowledge without the editor check.'}))
                return 2
            result = service.acknowledge(args.ack, current, expected, args.note)
            print(json.dumps({k: result.get(k) for k in ('ok', 'error', 'data')}, indent=1))
            return 0 if result['ok'] else 3
        if current is not None:
            parser.error('GECK is running; acknowledge without --offline so the editor is checked')
        with closing(service.db()) as db, db:
            row = db.execute('SELECT * FROM operations WHERE id=? AND project=?',
                             (args.ack, project.project_id)).fetchone()
            if row is None or row['state'] not in UNRESOLVED or row['recovery_ack']:
                print(json.dumps({'ok': False, 'error': 'not an unresolved operation of this project'}))
                return 3
            db.execute('UPDATE operations SET recovery_ack=? WHERE id=?',
                       (json.dumps({'offline': True, 'session': None, 'file': {'sha256': expected},
                                    'note': args.note, 'time': time.time()}), args.ack))
        print(json.dumps({'ok': True, 'acknowledged': args.ack, 'offline': True,
                          'warning': 'Barrier cleared without an editor check; this is not rollback'}))
        return 0
    finally:
        service.close()


if __name__ == '__main__':
    sys.exit(main())
