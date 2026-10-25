"""Build/install optional xNVSE companion, or read snapshots via the same core as MCP."""
import argparse
import json
from pathlib import Path
from geck_mcp.config import Project
from geck_mcp import runtime_companion as core
from geck_mcp.service import Service


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True)
    sub=parser.add_subparsers(dest='mode',required=True)
    preflight=sub.add_parser('preflight')
    preflight.add_argument('--profile',required=True,type=Path)
    preflight.add_argument('--zig',type=Path)
    ready=sub.add_parser('readiness')
    ready.add_argument('--profile',required=True,type=Path)
    ready.add_argument('--expected-plugin-hash',required=True)
    ready.add_argument('--adapter',choices=['vanilla','xnvse'],default='xnvse')
    context=sub.add_parser('save-context')
    context.add_argument('--label',required=True)
    build=sub.add_parser('build')
    build.add_argument('--profile',required=True,type=Path)
    build.add_argument('--zig',required=True,type=Path)
    install=sub.add_parser('install')
    install.add_argument('--build-receipt',required=True,type=Path)
    install.add_argument('--expected-plugin-hash',required=True)
    snapshot=sub.add_parser('snapshot')
    snapshot.add_argument('--profile',required=True,type=Path)
    snapshot.add_argument('--expected-plugin-hash',required=True)
    snapshot.add_argument('--baseline',type=Path)
    args=parser.parse_args()
    project=Project.load(args.project)
    if args.mode=='preflight':
        result=core.preflight(project,json.loads(args.profile.read_text()),args.zig)
    elif args.mode=='readiness':
        result=core.readiness(project,json.loads(args.profile.read_text()),args.expected_plugin_hash,args.adapter)
    elif args.mode=='save-context':
        service=Service(project)
        try:result=service.runtime_save_context(args.label)
        finally:service.close()
    elif args.mode=='build':
        result=core.build(project,json.loads(args.profile.read_text()),args.zig)
    elif args.mode=='install':
        result=core.install(project,json.loads(args.build_receipt.read_text()),args.expected_plugin_hash)
    else:
        service=Service(project)
        try:
            baseline=json.loads(args.baseline.read_text()) if args.baseline else None
            if baseline and baseline.get('ok') is True:baseline=baseline['data']
            result=service.runtime_snapshot(json.loads(args.profile.read_text()),args.expected_plugin_hash,
                baseline)
        finally:service.close()
    print(json.dumps(result))
    return 1 if result.get('ok') is False else 0


if __name__=='__main__':raise SystemExit(main())
