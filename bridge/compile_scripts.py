"""Shared CLI/MCP compile runner. Pending operations survive cancellation/client restart.

Start: compile_scripts.py --project projects/hellowasteland.json
Resume: compile_scripts.py --project ... --operation-id UUID
Inspect: compile_scripts.py --project ... --operation-id UUID --status
The current build must be installed and loaded through live_load.py first.
"""
import argparse
import json
from pathlib import Path
import time
import uuid

from geck_mcp.config import Project
from geck_mcp.service import Service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--operation-id')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--deadline-seconds', type=int, default=1200)
    parser.add_argument('--extend-seconds', type=int, default=0, help='explicit reviewed deadline extension on resume')
    parser.add_argument('--once', action='store_true', help='advance at most one phase')
    parser.add_argument('--reviewed-roundtrip', help='Exact token from blocked canonical-field diff; retain saved artifact')
    parser.add_argument('--review-note')
    args = parser.parse_args()
    service = Service(Project.load(args.project))
    try:
        if args.status:
            if not args.operation_id:
                parser.error('--status requires --operation-id')
            result = service.compile_status(args.operation_id)
        elif args.operation_id:
            result = service.compile_resume(args.operation_id, args.extend_seconds, args.reviewed_roundtrip, args.review_note)
        else:
            result = service.compile_start('compile-' + uuid.uuid4().hex, args.deadline_seconds)
        print(json.dumps(result), flush=True)
        delay = .2
        while not args.status and not args.once and result.get('ok') and result['outcome'] == 'pending':
            time.sleep(delay)
            delay = min(delay * 1.5, 2)
            result = service.compile_resume(result['operationId'])
            print(json.dumps(result), flush=True)
        return 0 if result.get('ok') and (args.status or result['outcome'] == 'verified') else 3
    finally:
        service.close()


if __name__ == '__main__':
    raise SystemExit(main())
