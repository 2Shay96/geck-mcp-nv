"""Compile a spec project's GECK scripts in GECK and cache the result for offline builds.

    python compile_scripts.py --project projects/my_mod.json

1. Build the plugin (scripts without a cache hit are emitted uncompiled) and install it.
2. Load it in GECK (live_load.py --if-needed: skipped when this GECK session already loaded these exact
   bytes; a load whose plugin is active but whose cell check cannot run still counts, since the script
   editor does not need Cell View), then for each uncompiled script (quest scripts first):
   Script Edit > Open > select > Save, through the bridge (Probe "script.compile"). Compile errors
   are GECK's own messages; the run stops at the first failing script.
3. Save the plugin from GECK, lift the compiled subrecords into state/scripts/<project>.json
   (keyed by source SHA-256 and FormID), rebuild offline (now fully compiled) and install that.
Reload GECK afterwards (live_load.py) to have the final build open.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from geck_mcp.authoring import Authoring, AuthoringError, atomic_write  # noqa: E402
from geck_mcp.config import Project  # noqa: E402
from geck_mcp.esp import build as builder, scripts  # noqa: E402
from install_plugin import editor_title  # noqa: E402

PLUGIN = {'name': None, 'project': None}


def probe(*args, timeout=90):
    project = PLUGIN['project']
    env = dict(os.environ)
    env.update(project.helper_env())
    if PLUGIN['name']:
        env['GECK_BRIDGE_PLUGIN'] = PLUGIN['name']      # the helper's expected active plugin
    out = subprocess.run(project.helper_command(*args), capture_output=True, text=True,
                         timeout=timeout, env=env).stdout
    start, end = out.find('{'), out.rfind('}')
    if start < 0:
        raise RuntimeError('no JSON from helper for %s: %r' % (args[0], out[:300]))
    return json.loads(out[start:end + 1])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_lines(text):
    out = []
    for line in (text or '').splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


def load_in_geck(project, project_path):
    """Run live_load.py --if-needed. Returns (ok, summary)."""
    load = subprocess.run([sys.executable, str(ROOT / 'live_load.py'), '--project', str(project_path),
                           '--timeout', '1200', '--if-needed'], capture_output=True, text=True, timeout=1300)
    lines = json_lines(load.stdout)
    summary = lines[-1] if lines else {'stderr': load.stderr[-500:]}
    if load.returncode == 0:
        return True, summary
    # Dispatched in this run and GECK now shows the plugin, clean: the load itself worked; only its check failed.
    dispatched = any((l.get('load') or {}).get('ok') and (l.get('load') or {}).get('outcome') == 'loading'
                     for l in lines)
    status = probe('status')
    after = status.get('after') or {}
    title = 'Garden of Eden Creation Kit - [%s]' % project.plugin
    if dispatched and status.get('ok') and after.get('editorTitle') == title and not after.get('unsavedChanges'):
        return True, dict(summary, warning='load check failed, but GECK shows %s and is clean; continuing '
                                           '(the script editor does not need Cell View)' % project.plugin)
    return False, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--skip-load', action='store_true', help='plugin is already installed and loaded')
    args = parser.parse_args()
    project = Project.load(args.project)
    PLUGIN['name'] = project.plugin
    PLUGIN['project'] = project
    auth = Authoring(project)
    spec = auth.load_spec()
    receipt, _ = auth.build(write=True)
    if not receipt['validation']['ok']:
        print(json.dumps({'ok': False, 'stage': 'build', 'validation': receipt['validation']}))
        return 2
    pending = receipt['uncompiledScripts']
    print(json.dumps({'stage': 'build', 'sha256': receipt['sha256'], 'uncompiled': pending}), flush=True)
    if not pending:
        entry = auth.install(editor_title(project))
        print(json.dumps({'ok': True, 'stage': 'done', 'install': entry.get('sha256'), 'changed': entry.get('changed')}))
        return 0
    probe('script.editor.close')        # a leftover Script Edit window would block loading
    if not args.skip_load:
        entry = auth.install(editor_title(project))
        print(json.dumps({'stage': 'install', 'sha256': entry.get('sha256'), 'changed': entry.get('changed')}), flush=True)
        ok, summary = load_in_geck(project, args.project)
        print(json.dumps(dict(summary, stage='load')), flush=True)
        if not ok:
            print(json.dumps({'ok': False, 'stage': 'load'}))
            return 3
        if summary.get('outcome') != 'already_loaded':
            time.sleep(8)
    kinds = {e: spec['records'][e].get('script_type', 'object') for e in pending}
    order = sorted(pending, key=lambda e: (kinds[e] != 'quest', e))
    for edid in order:
        result = None
        for attempt in range(3):
            result = probe('script.compile', edid)
            if result.get('ok') or 'timed out' not in (result.get('error') or ''):
                break
            time.sleep(5)
        after = result.get('after') or {}
        print(json.dumps({'stage': 'compile', 'script': edid, 'ok': result.get('ok'), 'compiled': after.get('compiled'),
                          'errors': after.get('errors'), 'error': result.get('error')}), flush=True)
        if not result.get('ok') or not after.get('compiled'):
            probe('script.editor.close')
            return 4
    closed = probe('script.editor.close')
    installed = project.game_root / 'Data' / project.plugin
    before = installed.read_bytes()
    time.sleep(1)
    saved = probe('plugin.save', sha(before), timeout=120)
    print(json.dumps({'stage': 'save', 'ok': saved.get('ok'), 'error': saved.get('error')}), flush=True)
    if not saved.get('ok'):
        return 5
    data = installed.read_bytes()
    report = scripts.update_from_plugin(project.state_dir, spec, auth.spec_path.parent, data, receipt['formIds'])
    print(json.dumps({'stage': 'cache', 'report': report}), flush=True)
    history_path = project.state_dir / 'installs' / (spec['project_id'] + '.json')
    history = json.loads(history_path.read_text()) if history_path.exists() else []
    history.append({'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'plugin': project.plugin, 'sha256': sha(data),
                    'previousSha256': sha(before), 'kind': 'geck-script-compile-save', 'backup': None,
                    'specSha256': receipt['specSha256']})
    atomic_write(history_path, (json.dumps(history, indent=1) + '\n').encode())
    receipt2, _ = auth.build(write=True)
    print(json.dumps({'stage': 'rebuild', 'sha256': receipt2['sha256'], 'uncompiled': receipt2['uncompiledScripts'],
                      'ok': receipt2['validation']['ok']}), flush=True)
    if receipt2['uncompiledScripts'] or not receipt2['validation']['ok']:
        return 6
    try:
        entry = auth.install(editor_title(project))
    except AuthoringError as error:
        print(json.dumps({'ok': False, 'stage': 'install-final', 'code': error.code, 'error': str(error)}))
        return 7
    print(json.dumps({'ok': True, 'stage': 'done', 'install': entry.get('sha256'), 'changed': entry.get('changed'),
                      'reloadNeeded': True}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
