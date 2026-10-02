"""Take an actor photo from the command line (same code path as the geck_actor_photo MCP tool).

    .venv/bin/python photo_cli.py "Sunny Smiles" [--pitch N] [--fill 0.86] [--wait 300]

Repeats the resumable call until the photo is done (or --wait seconds pass) and prints JSON.
"""
import argparse
import json
import time

from geck_mcp.config import Project
from geck_mcp.service import Service

parser = argparse.ArgumentParser()
parser.add_argument('subject')
parser.add_argument('--project', default='projects/salvatore_mod.json')
parser.add_argument('--pitch', type=int, default=None, help='default -60 (level camera)')
parser.add_argument('--fill', type=float, default=0.86)
parser.add_argument('--rotation', type=float, default=180)
parser.add_argument('--lighting', choices=['auto', 'keep', 'toggle'], default='auto')
parser.add_argument('--size', nargs=2, type=int, metavar=('W', 'H'))
parser.add_argument('--wait', type=int, default=300)
args = parser.parse_args()

service = Service(Project.load(args.project))
started = time.time()
try:
    while True:
        result = service.actor_photo(args.subject, args.rotation, args.pitch, args.fill,
                                     args.lighting, tuple(args.size) if args.size else None)
        stage = (result.get('data') or {}).get('stage')
        print(json.dumps({'t': round(time.time() - started), 'ok': result['ok'], 'stage': stage,
                          'error': result['error']}), flush=True)
        not_ready = not result['ok'] and result['error']['code'] in ('EDITOR_NOT_READY', 'EDITOR_BUSY')
        if (not not_ready and (not result['ok'] or stage != 'loading')) or time.time() - started > args.wait:
            break
        time.sleep(15 if not_ready else result['data'].get('retryAfterSeconds', 20))
    print(json.dumps(result, indent=1))
finally:
    service.close()
