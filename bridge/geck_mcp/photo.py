"""One-call actor photos: a throwaway "photo studio" plugin, GECK framing, macOS capture, cut-out.

Flow of geck_actor_photo (resumable; call it again with the same subject until stage == "done"):
  1. resolve the subject (EditorID or display name) in the FalloutNV.esm index (NPC_ or CREA);
  2. write/build GeckPhotoStudio.esp: one interior cell, neutral lighting, the subject placed at the
     origin turned to face GECK's look-at camera (never touches the user's own plugins);
  3. install it and load it with FalloutNV.esm only (the editor must have no unsaved edits);
     loading the master takes 1-3 minutes, so the call returns stage "loading" instead of blocking;
  4. frame the subject from Cell View, maximise the Render Window, optionally tilt the camera,
     auto-fit zoom/centre by measuring captures, deselect, capture the Render Window by CGWindowID
     and write <EditorID>-<time>.png plus a transparent <EditorID>-<time>-cutout.png.
"""
import hashlib
import json
import math
from pathlib import Path
import time

from .authoring import Authoring, AuthoringError
from .config import Project
from .transport import BridgeError
from . import imaging

PLUGIN = 'GeckPhotoStudio.esp'
CELL = 'GeckPhotoStudio'
PROJECT_ID = 'photo-studio'
ACTOR_TYPES = ('NPC_', 'CREA')
TITLE = 'Garden of Eden Creation Kit - [%s]' % PLUGIN
MAC_TITLE_BAR_POINTS = 28
# Shift+drag pixels that bring GECK's Cell View look-at camera level with the subject's origin
# (verified live 2026-09-30: the selection box floor collapses to a line). The vertical pan in
# the auto-fit then raises the level camera to the subject's middle.
DEFAULT_PITCH = -60

LIGHTING = {'ambient': [110, 110, 110], 'directional': [200, 200, 200], 'fog_color': [0, 0, 0],
            'fog_near': 0.0, 'fog_far': 10000.0, 'clip_distance': 10000.0,
            'directional_rotation': [45, 30], 'directional_fade': 1.0, 'fog_power': 1.0}


def sha(data):
    return hashlib.sha256(data).hexdigest()


class PhotoStudio:
    def __init__(self, main_project, service_factory):
        self.main = main_project
        self.folder = main_project.state_dir / 'photo'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.spec_path = self.folder / 'GeckPhotoStudio.spec.json'
        self.state_path = self.folder / 'state.json'
        self.output_dir = main_project.state_dir.parent / 'photos'
        if not self.spec_path.exists():
            self.spec_path.write_text(json.dumps(self.spec_for('XMarker', 180), indent=1) + '\n')
        self.project = Project(project_id=PROJECT_ID, launcher=main_project.launcher, wine=main_project.wine,
                               bottle=main_project.bottle,
                               game_root=main_project.game_root, plugin=PLUGIN, records=[],
                               state_dir=main_project.state_dir, helper=main_project.helper,
                               helper_timeout_seconds=main_project.helper_timeout_seconds,
                               transport=main_project.transport, spec=self.spec_path)
        self._factory = service_factory
        self._service = None

    @property
    def service(self):
        if self._service is None:
            self._service = self._factory(self.project)
        return self._service

    def close(self):
        if self._service is not None:
            self._service.close()
            self._service = None

    # -- state ------------------------------------------------------------------------------
    def load_state(self):
        return json.loads(self.state_path.read_text()) if self.state_path.exists() else {}

    def save_state(self, state):
        self.state_path.write_text(json.dumps(state, indent=1) + '\n')

    # -- subject ----------------------------------------------------------------------------
    def resolve(self, subject):
        index = Authoring(self.project).index(['FalloutNV.esm'])
        hits = [h for h in index.lookup(subject) if h[1] in ACTOR_TYPES]
        if not hits:
            wanted = subject.strip().lower()
            hits = [h for rows in index.entries.values() for h in rows
                    if h[1] in ACTOR_TYPES and h[3] and h[3].strip().lower() == wanted]
        if not hits:
            near = [r for t in ACTOR_TYPES for r in index.search(subject.replace(' ', ''), t, 10)]
            raise BridgeError('SUBJECT_NOT_FOUND', 'No NPC_/CREA with that EditorID or name in FalloutNV.esm',
                              {'suggestions': [{'editorId': r['editorId'], 'name': r['name'], 'type': r['type']}
                                               for r in near[:15]]})
        if len({h[5] for h in hits}) > 1:
            raise BridgeError('SUBJECT_AMBIGUOUS', 'Several actors share that name; pass an EditorID',
                              {'candidates': [{'editorId': h[5], 'type': h[1], 'formId': '%08X' % h[2],
                                               'name': h[3]} for h in hits[:25]]})
        h = hits[0]
        return {'editorId': h[5], 'type': h[1], 'formId': '%08X' % h[2], 'name': h[3]}

    def spec_for(self, editor_id, rotation):
        return {'schema': 1, 'project_id': PROJECT_ID, 'plugin': PLUGIN, 'author': 'geck-bridge',
                'description': 'Throwaway photo studio generated by geck_actor_photo. Safe to delete.',
                'masters': ['FalloutNV.esm'], 'records': {},
                'cells': {CELL: {'name': 'GECK Photo Studio', 'lighting': LIGHTING,
                                 'objects': [{'ref_id': 'subject', 'base': '@' + editor_id,
                                              'position': [0, 0, 0], 'rotation': [0, 0, rotation]}]}},
                'release': {}}

    # -- main entry ---------------------------------------------------------------------------
    def photo(self, subject, rotation=180, pitch=DEFAULT_PITCH, fill=0.86, lighting='auto', render_size=None):
        started = time.monotonic()
        actor = self.resolve(subject)
        spec = self.spec_for(actor['editorId'], rotation)
        text = json.dumps(spec, indent=1) + '\n'
        if self.spec_path.read_text() != text:
            self.spec_path.write_text(text)
        try:
            receipt, _ = Authoring(self.project).build(write=True)
        except AuthoringError as e:
            raise BridgeError(e.code, str(e), e.evidence)
        if not receipt['validation']['ok']:
            raise BridgeError('VALIDATION_FAILED', 'Photo studio build failed validation', receipt['validation'])
        ref_form = [r for r in receipt['references'][CELL] if r['refId'] == 'subject'][0]['formId']
        svc = self.service
        state = self.load_state()
        pending = state.get('pendingLoad')
        if pending:
            polled = svc.load_status(pending['operationId'])
            if not polled['ok']:
                state.pop('pendingLoad', None)
                self.save_state(state)
                raise BridgeError(polled['error']['code'], 'Photo studio load failed: ' + polled['error']['message'],
                                  polled.get('data'))
            load = polled['data']['load']
            if polled['data'].get('loading') or load.get('outcome') == 'loading':
                return self._loading(actor, pending, started)
            state.pop('pendingLoad', None)
            self.save_state(state)
        status = self._status()
        title, session = status['editorTitle'], status['sessionId']
        installed = self.project.plugin_path
        installed_sha = sha(installed.read_bytes()) if installed.exists() else None
        if title.rstrip('*') != TITLE or installed_sha != receipt['sha256']:
            if status['unsavedChanges']:
                raise BridgeError('UNSAVED_CHANGES', 'GECK has unsaved edits. Save or discard them yourself; '
                                  'the photo workflow never discards work.', {'editorTitle': title})
            stamp = '%s-%d' % (receipt['sha256'][:12], int(time.time()))
            if installed_sha != receipt['sha256']:
                done = svc.plugin_install(session, 'photo-install-' + stamp)
                if not done['ok']:
                    raise BridgeError(done['error']['code'], done['error']['message'], done.get('data'))
            load = svc.load_plugin(session, title, receipt['sha256'], 'photo-load-' + stamp,
                                   title.rstrip('*') == TITLE)
            if not load['ok']:
                raise BridgeError(load['error']['code'], load['error']['message'], load.get('data'))
            if not load['data'].get('alreadyLoaded'):
                pending = {'operationId': load['operationId'], 'subject': actor['editorId'],
                           'sha256': receipt['sha256'], 'dispatched': time.time()}
                state['pendingLoad'] = pending
                self.save_state(state)
                return self._loading(actor, pending, started)
        return self._capture(session, actor, ref_form, pitch, fill, lighting, render_size, started)

    def _status(self):
        result = self.service.status()
        if not result['ok']:
            message = result['error']['message']
            if 'matched 0 controls' in message or 'found 0' in message or 'timed out' in message:
                raise BridgeError('EDITOR_NOT_READY', 'GECK is not running or still starting/busy; retry shortly: '
                                  + message, {'retryAfterSeconds': 15})
            raise BridgeError(result['error']['code'], message, result.get('data'))
        return result['data']

    def _loading(self, actor, pending, started):
        return {'stage': 'loading', 'subject': actor, 'loadOperationId': pending['operationId'],
                'secondsSinceDispatch': round(time.time() - pending['dispatched']),
                'retryAfterSeconds': 20, 'elapsedMs': round((time.monotonic() - started) * 1000),
                'next': 'GECK is loading FalloutNV.esm + the photo studio (1-3 min). Call geck_actor_photo '
                        'again with the same subject; do not reload manually.'}

    # -- framing and capture ------------------------------------------------------------------
    def _capture(self, session, actor, ref_form, pitch, fill, lighting, render_size, started):
        svc = self.service

        def action():
            svc.check_session(session)
            framed = svc.call('cell.show', CELL, ref_form, session=session)
            layout = 'size:%d:%d' % tuple(render_size) if render_size else 'max'
            steps = [layout, 'sleep:1200', 'redraw']
            if lighting == 'toggle':
                steps.append('key:a')
            if pitch:
                steps.append('orbit:0:%d' % int(pitch))
            prepared = svc.call('render.steps', CELL, ';'.join(steps), session=session)
            client = prepared['client']
            # Deselect before measuring: the selection box lines would inflate the subject's box.
            svc.call('render.steps', CELL, 'realclick:6:%d;sleep:300;redraw' % (client[1] - 6), session=session)
            window = imaging.render_window(CELL)
            work = self.folder / 'work'
            chosen = lighting
            if lighting == 'auto':
                # GECK toggles between a dark cell-lit view and a bright editor light with "A"; keep the brighter.
                before = self._measure(window, client, work, 90)
                svc.call('render.steps', CELL, 'key:a;sleep:900;redraw;sleep:300', session=session)
                after = self._measure(window, client, work, 91)
                chosen = 'toggled'
                if (after or {}).get('luminance', 0) < (before or {}).get('luminance', 0):
                    svc.call('render.steps', CELL, 'key:a;sleep:900;redraw;sleep:300', session=session)
                    chosen = 'kept'
            fit = self._autofit(session, window, client, fill, work)
            if not fit['converged']:
                raise BridgeError('FRAMING_FAILED', 'Could not frame the subject automatically', fit)
            # Let FaceGen textures settle and force a redraw before the final capture.
            svc.call('render.steps', CELL, 'sleep:1500;redraw;sleep:300', session=session)
            stamp = time.strftime('%Y%m%d-%H%M%S')
            self.output_dir.mkdir(parents=True, exist_ok=True)
            raw = imaging.capture_window(window['id'], work / 'final-raw.png')
            np, Image = imaging._np()
            image = Image.open(raw)
            top = imaging.title_bar_pixels(image.height, client[1], image.width, client[0])
            frame = self.output_dir / ('%s-%s.png' % (actor['editorId'], stamp))
            rgb, _ = imaging.load_rgb(raw, top)
            Image.fromarray(rgb.astype('uint8'), 'RGB').save(frame)
            cut = imaging.cutout(frame, self.output_dir / ('%s-%s-cutout.png' % (actor['editorId'], stamp)))
            return {'stage': 'done', 'subject': actor, 'photo': str(frame), 'cutout': cut,
                    'frame': framed.get('renderTitle'), 'fit': fit, 'pitch': pitch, 'lighting': chosen,
                    'visualVerified': False,
                    'note': 'Automated framing; a human should glance at the result.'}
        result = svc.run('geck_actor_photo', {'subject': actor['editorId'], 'pitch': pitch, 'fill': fill,
                                             'lighting': lighting}, action)
        if not result['ok']:
            raise BridgeError(result['error']['code'], result['error']['message'], result.get('data'))
        data = result['data']
        data['operationId'] = result['operationId']
        data['elapsedMs'] = round((time.monotonic() - started) * 1000)
        return data

    def _measure(self, window, client, work, n):
        path = imaging.capture_window(window['id'], work / ('fit-%d.png' % n))
        rgb, image = imaging.load_rgb(path)
        top = imaging.title_bar_pixels(rgb.shape[0], client[1], rgb.shape[1], client[0])
        rgb = rgb[top:]
        scale = rgb.shape[1] / float(client[0])
        small = rgb[::4, ::4]
        box, bg = imaging.subject_bbox(small)
        if box is None:
            return None
        # back to client coordinates
        x0, y0, x1, y1 = [v * 4 / scale for v in box]
        bx0, by0, bx1, by1 = box
        sub = small[by0:by1, bx0:bx1]
        fg = imaging.background_mask(sub, bg)[0] == False
        lum = float(sub[fg].mean()) if fg.any() else 0.0
        return {'box': [round(x0), round(y0), round(x1), round(y1)], 'background': bg, 'luminance': round(lum, 1),
                'height': (y1 - y0) / client[1], 'cx': (x0 + x1) / 2.0, 'cy': (y0 + y1) / 2.0,
                'touchesEdge': y0 <= 2 or x0 <= 2 or y1 >= client[1] - 2 or x1 >= client[0] - 2}

    def _autofit(self, session, window, client, fill, work, max_moves=16):
        """Closed-loop framing: centre the subject by panning, then zoom until it fills about `fill`.

        Wheel zoom behaves like a dolly (the size change per tick grows as the camera gets closer),
        so zoom-ins are capped until a clean (unclipped) observation calibrates q = camera travel per
        tick / distance, a zoom-in that clips the subject is undone, and the size settles on the
        largest whole-tick framing that does not overshoot. Pan gains are signed and measured from a
        small first probe; a pan that loses the subject is undone. Always finishes on a measurement.
        """
        svc = self.service
        history, actions = [], []
        q, calibrated, up_cap = 0.15, False, 2
        pan_gain = [None, None]
        probe = 16
        last, m, converged, settled = None, None, False, False

        def act(kind, value):
            if kind == 'zoom':
                svc.call('render.steps', CELL, 'zoom:%d;sleep:300' % value, session=session)
            else:
                svc.call('render.steps', CELL, 'pan:%d:%d;sleep:300' % tuple(value), session=session)
            actions.append({kind: value})

        for n in range(max_moves + 1):
            m = self._measure(window, client, work, n)
            history.append(m)
            visible = m is not None and m['height'] >= 0.02
            if not visible:
                if last and n < max_moves:
                    if last.get('pan'):
                        act('pan', [-v for v in last['pan']])
                        probe = max(2, probe // 3)
                        pan_gain = [None if g is None else g * 3 for g in pan_gain]
                    else:
                        act('zoom', -last['ticks'])
                        up_cap = max(1, abs(last['ticks']) - 1)
                    last = None
                    continue
                return {'client': client, 'converged': False, 'iterations': len(history), 'final': m,
                        'actions': actions, 'q': q, 'panGain': pan_gain}
            h, clipped = m['height'], m['touchesEdge']
            if last and last.get('ticks'):
                t = last['ticks']
                was_clipped = last['m']['touchesEdge']
                if t > 0 and clipped and not was_clipped and n < max_moves:
                    act('zoom', -t)                              # overshot into the frame edge: undo
                    settled = settled or t == 1
                    up_cap = max(1, t - 1)
                    last = None
                    continue
                if not clipped and not was_clipped:
                    q0 = (1 - last['m']['height'] / h) / t      # relative to the previous distance
                    if 0.005 < q0 < 0.6 and q0 * t < 0.95:
                        q, calibrated = q0 / (1 - q0 * t), True
                        up_cap = 10
            if last and last.get('pan'):
                for axis, key in ((0, 'cx'), (1, 'cy')):
                    push = last['pan'][axis]
                    if abs(push) >= 2:
                        observed = (m[key] - last['m'][key]) / push
                        if 0.02 < abs(observed) < 200:
                            pan_gain[axis] = observed
            dx = client[0] / 2.0 - m['cx']
            dy = client[1] / 2.0 - m['cy']
            centre_ok = abs(dx) <= client[0] * 0.025 and abs(dy) <= client[1] * 0.025
            next_up = h / (1 - q) if q < 0.95 else 99
            size_ok = not clipped and h <= fill * 1.08 and (h >= fill * 0.92 or settled
                                                             or (calibrated and next_up > fill * 1.08))
            if size_ok and centre_ok:
                converged = True
                break
            if n == max_moves:
                break
            if clipped and h >= fill * 0.9:
                ticks = max(-3, min(-1, int(round((1 - h / (fill * 0.8)) / q))))
                act('zoom', ticks)
                last = {'m': m, 'ticks': ticks}
            elif not centre_ok:
                push = []
                for d, g in ((dx, pan_gain[0]), (dy, pan_gain[1])):
                    if abs(d) < 2:
                        push.append(0)
                    elif g is None:
                        push.append(int(math.copysign(probe, d)))
                    else:
                        push.append(int(round(max(-900, min(900, 0.9 * d / g)))))
                act('pan', push)
                last = {'m': m, 'pan': push}
            elif h > fill * 1.08:
                ticks = max(-3, min(-1, int(math.floor((1 - h / fill) / q))))
                act('zoom', ticks)
                last = {'m': m, 'ticks': ticks}
            else:
                ticks = max(1, min(up_cap, int(math.floor((1 - h / fill) / q))))
                act('zoom', ticks)
                last = {'m': m, 'ticks': ticks}
        return {'client': client, 'converged': converged, 'iterations': len(history), 'final': m,
                'actions': actions, 'q': q, 'calibrated': calibrated, 'panGain': pan_gain}
