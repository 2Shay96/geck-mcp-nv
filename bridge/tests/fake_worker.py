"""Stand-in for `Probe.Mcp.exe serve` used by transport tests.

Behaviour is selected with FAKE_WORKER_MODE:
  normal      answer every request
  no_hello    never send the handshake (like a legacy helper)
  legacy      answer the handshake as an old helper would (unknown operation)
  hang:<op>   never answer <op>
  die:<op>    exit immediately after reading <op>
  noise       print Wine-style noise lines between responses
  deaf        send the handshake, then never read requests (stdin not forwarded)
Each started worker appends a line to FAKE_WORKER_LOG so tests can count starts.
"""
import json
import os
import sys
import time

mode = os.environ.get('FAKE_WORKER_MODE', 'normal')
log = os.environ.get('FAKE_WORKER_LOG')
if log:
    with open(log, 'a') as f:
        f.write('start %d\n' % os.getpid())

leaked = sorted(k for k in os.environ if k.startswith('GECK_BRIDGE_'))


def emit(value):
    sys.stdout.write(json.dumps(value) + '\n')
    sys.stdout.flush()


if mode == 'no_hello':
    time.sleep(60)
    sys.exit(0)
if mode == 'legacy':
    emit({'ok': False, 'operation': 'serve', 'error': 'unknown operation'})
    sys.exit(2)

emit({'id': None, 'ok': True, 'operation': 'hello', 'after': {'protocol': 1, 'workerPid': os.getpid()}})
if mode == 'deaf':
    time.sleep(60)
    sys.exit(0)
served = 0
for line in sys.stdin:
    request = json.loads(line)
    rid = request.get('id')
    if mode == 'noise':
        print('0024:fixme:ntdll:NtQuerySystemInformation noise', flush=True)
    if 'batch' in request:
        results = []
        ok = True
        for step in request['batch']:
            op = step['args'][0]
            good = op != 'fail.op'
            results.append({'ok': good, 'operation': op, 'after': {'args': step['args']},
                            'error': None if good else 'step failed'})
            served += 1
            if not good:
                ok = False
                if request.get('stopOnError', True):
                    break
        emit({'id': rid, 'ok': ok, 'operation': 'batch', 'results': results,
              'after': {'completed': len(results)}, 'error': None if ok else 'batch step failed'})
        continue
    op = request['args'][0]
    if mode == 'hang:' + op:
        time.sleep(60)
    if mode == 'die:' + op:
        sys.exit(3)
    if op == 'shutdown':
        emit({'id': rid, 'ok': True, 'operation': 'shutdown', 'after': {'served': served}})
        break
    if op == 'ping':
        emit({'id': rid, 'ok': True, 'operation': 'ping', 'after': {'protocol': 1, 'served': served}})
        continue
    if op == 'bad.request':
        emit({'id': rid, 'ok': False, 'operation': 'protocol', 'error': 'PROTOCOL_ERROR: test'})
        continue
    served += 1
    if op == 'fail.op':
        emit({'id': rid, 'ok': False, 'operation': op, 'after': None,
              'error': 'blocked by existing dialog: Static'})
        continue
    emit({'id': rid, 'ok': True, 'operation': op,
          'after': {'args': request['args'], 'env': request.get('env'), 'served': served,
                    'workerPid': os.getpid(), 'leakedProcessEnv': leaked}})
