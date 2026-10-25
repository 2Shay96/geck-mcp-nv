"""Explicit opt-in console-companion setup and shared CLI/MCP command operations."""
import argparse
import json
from pathlib import Path
from geck_mcp.config import Project
from geck_mcp.service import Service
from geck_mcp import console


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path)
    sub = parser.add_subparsers(dest='mode', required=True)
    sub.add_parser('preflight')
    ready = sub.add_parser('readiness'); ready.add_argument('--expected-plugin-hash', required=True)
    build = sub.add_parser('build'); build.add_argument('--zig', type=Path, required=True)
    build.add_argument('--expected-plugin-hash', required=True)
    install = sub.add_parser('install'); install.add_argument('--build-receipt', type=Path, required=True)
    install.add_argument('--expected-plugin-hash', required=True)
    execute = sub.add_parser('execute'); execute.add_argument('--command', required=True)
    execute.add_argument('--intent', required=True); execute.add_argument('--target', type=Path, required=True)
    execute.add_argument('--expected-plugin-hash', required=True); execute.add_argument('--request-key', required=True)
    execute.add_argument('--binding', type=Path); execute.add_argument('--authorize-teleport', action='store_true')
    execute.add_argument('--verify', type=Path); execute.add_argument('--timeout-seconds', type=int, default=10)
    query = sub.add_parser('query')
    query.add_argument('--kind', choices=['plugin_index','item_count','equipped','weapon_health_percent','equipped_health'], required=True)
    query.add_argument('--intent', required=True); query.add_argument('--target', type=Path, required=True)
    query.add_argument('--expected-plugin-hash', required=True); query.add_argument('--request-key', required=True)
    query.add_argument('--binding', type=Path); query.add_argument('--slot', type=int, default=5)
    status = sub.add_parser('status'); status.add_argument('operation_id')
    release = sub.add_parser('release'); release.add_argument('operation_id'); release.add_argument('--note', required=True)
    args = parser.parse_args(); project = Project.load(args.project)
    if args.mode == 'preflight': result = console.preflight(project)
    elif args.mode == 'build': result = console.build(project, args.zig, args.expected_plugin_hash)
    elif args.mode == 'install': result = console.install(project, json.loads(args.build_receipt.read_text()), args.expected_plugin_hash)
    else:
        service = Service(project)
        try:
            if args.mode == 'readiness': result = service.console_readiness(args.expected_plugin_hash)
            elif args.mode == 'status': result = service.console_status(args.operation_id)
            elif args.mode == 'release': result = service.console_release(args.operation_id, args.note)
            else:
                target = json.loads(args.target.read_text())
                if target.get('ok') is True: target = target['data']['target']
                if args.mode == 'query':
                    result = service.console_query(args.kind, args.intent, target, args.expected_plugin_hash, args.request_key,
                        json.loads(args.binding.read_text()) if args.binding else None, args.slot)
                else:
                    result = service.console_execute(args.command, args.intent, target, args.expected_plugin_hash,
                        args.request_key, json.loads(args.verify.read_text()) if args.verify else None, args.timeout_seconds, json.loads(args.binding.read_text()) if args.binding else None, args.authorize_teleport)
        finally: service.close()
    print(json.dumps(result))
    return 1 if result.get('ok') is False else 0


if __name__ == '__main__': raise SystemExit(main())
