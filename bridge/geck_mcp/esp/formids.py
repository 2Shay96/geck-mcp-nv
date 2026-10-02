"""Stable FormID allocation and reference resolution for generated plugins.

A plugin's own records get FormIDs (master_count << 24) | local, where local
starts at 0x800. The mapping key -> local ID is persisted per project so a
rebuild never renumbers existing content:

  * keys are record EditorIDs, or "REFR:<cell>:<ref_id>" for placed references;
  * new keys receive fresh IDs in spec order (deterministic);
  * keys that disappear from the spec are retired, never handed to another key,
    and revived with the same ID if they come back;
  * HEDR next-object-ID is always one past the highest ID ever issued.

Standard library only.
"""
import gzip
import json
import os
from pathlib import Path
import re
import tempfile

FIRST_LOCAL = 0x800
MAX_LOCAL = 0xFFFFFF
HEX8 = re.compile(r'^[0-9A-Fa-f]{8}$')


class FormIdError(ValueError):
    pass


class FormIdMap:
    def __init__(self, path, plugin):
        self.path = Path(path)
        self.plugin = plugin
        self.assigned, self.retired, self.next = {}, {}, FIRST_LOCAL
        if self.path.exists():
            data = json.loads(self.path.read_text())
            if data.get('plugin') != plugin:
                raise FormIdError('FormID map %s belongs to %s, not %s' % (self.path, data.get('plugin'), plugin))
            self.assigned = {k: int(v, 16) for k, v in data['assigned'].items()}
            self.retired = {k: int(v, 16) for k, v in data.get('retired', {}).items()}
            self.next = int(data['next'], 16)

    # -- allocation ------------------------------------------------------------------
    def _issue(self, key):
        if key in self.retired:
            local = self.retired.pop(key)
        else:
            if self.next > MAX_LOCAL:
                raise FormIdError('FormID space exhausted')
            local, self.next = self.next, self.next + 1
        self.assigned[key] = local
        return local

    def sync(self, keys):
        """Assign every key (in the given order), retire keys no longer present.

        Returns {key: local_id} for exactly `keys`.
        """
        keys = list(keys)
        if len(set(keys)) != len(keys):
            dupes = sorted({k for k in keys if keys.count(k) > 1})
            raise FormIdError('duplicate keys: %s' % ', '.join(dupes))
        for key in list(self.assigned):
            if key not in keys:
                self.retired[key] = self.assigned.pop(key)
        return {key: self.assigned[key] if key in self.assigned else self._issue(key) for key in keys}

    def seed(self, key, local):
        """Adopt an existing ID (e.g. from a hand-built plugin) before the first sync."""
        if not FIRST_LOCAL <= local <= MAX_LOCAL:
            raise FormIdError('local FormID %06X outside %06X..%06X' % (local, FIRST_LOCAL, MAX_LOCAL))
        owner = self.owner(local)
        if owner is not None and owner != key:
            raise FormIdError('local FormID %06X already belongs to %s' % (local, owner))
        self.retired.pop(key, None)
        self.assigned[key] = local
        self.next = max(self.next, local + 1)

    def owner(self, local):
        for table in (self.assigned, self.retired):
            for key, value in table.items():
                if value == local:
                    return key
        return None

    @property
    def next_object_id(self):
        return self.next

    # -- persistence -----------------------------------------------------------------
    def to_json(self):
        return {'plugin': self.plugin, 'next': '%06X' % self.next,
                'assigned': {k: '%06X' % v for k, v in sorted(self.assigned.items(), key=lambda kv: kv[1])},
                'retired': {k: '%06X' % v for k, v in sorted(self.retired.items(), key=lambda kv: kv[1])}}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix='.formids-')
        with os.fdopen(fd, 'w') as stream:
            json.dump(self.to_json(), stream, indent=1)
            stream.write('\n')
        os.replace(tmp, self.path)


class MasterIndex:
    """EditorID lookup over one or more index files written by esm_index.py."""

    def __init__(self, paths=()):
        self.masters = []          # names in load order
        self.entries = {}          # edid -> list of (master_position, type, formid, full, model)
        for path in paths:
            self.add(path)

    def add(self, path):
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            data = json.load(stream)
        position = len(self.masters)
        self.masters.append(data['master'])
        for edid, row in data['entries'].items():
            rows = row if isinstance(row[0], list) else [row]
            for r in rows:
                self.entries.setdefault(edid.lower(), []).append(
                    (position, r[0], int(r[1], 16), r[2], r[3], edid))
        return data

    def lookup(self, edid):
        return self.entries.get(edid.lower(), [])

    def search(self, text, record_type=None, limit=25):
        text = text.lower()
        rows = []
        for key, hits in self.entries.items():
            if text in key:
                for pos, rtype, form, full, model, edid in hits:
                    if record_type is None or rtype == record_type:
                        rows.append({'editorId': edid, 'type': rtype, 'formId': '%08X' % form,
                                     'master': self.masters[pos], 'name': full, 'model': model})
        rows.sort(key=lambda r: (len(r['editorId']), r['editorId']))
        return rows[:limit]


class Resolver:
    """Turns spec references into FormIDs valid inside the generated plugin.

    "@EditorID"  -> our own record, or a master record via the index.
    "XXXXXXXX"   -> raw FormID; its top byte must name a master or this plugin.
    Master FormIDs are rewritten to the master's position in *our* MAST list.
    """

    def __init__(self, masters, own, index=None, own_types=None):
        self.masters = list(masters)              # our MAST list, in order
        self.own = dict(own)                      # edid -> full FormID in our plugin
        self.own_types = {k.lower(): v for k, v in (own_types or {}).items()}   # edid -> record type
        self.own_lower = {k.lower(): v for k, v in self.own.items()}
        self.index = index or MasterIndex()
        self.self_byte = len(self.masters)

    def resolve_typed(self, ref):
        """Like resolve(), but also return the base record type when known (else None)."""
        form = self.resolve(ref)
        rtype = None
        if isinstance(ref, str) and ref.startswith('@'):
            edid = ref[1:].lower()
            if edid in self.own_lower:
                rtype = self.own_types.get(edid)
            else:
                hits = [h for h in self.index.lookup(ref[1:]) if self.index.masters[h[0]] in self.masters]
                rtype = max(hits, key=lambda h: h[0])[1] if hits else None
        return form, rtype

    def resolve(self, ref, expect_types=None):
        if isinstance(ref, int):
            ref = '%08X' % ref
        if not isinstance(ref, str) or not ref:
            raise FormIdError('reference must be "@EditorID" or an 8-digit FormID: %r' % (ref,))
        if ref.startswith('@'):
            edid = ref[1:]
            if edid.lower() in self.own_lower:
                return self.own_lower[edid.lower()]
            hits = [h for h in self.index.lookup(edid) if self.index.masters[h[0]] in self.masters]
            if expect_types:
                typed = [h for h in hits if h[1] in expect_types]
                if not typed and hits:
                    raise FormIdError('%s is a %s, expected %s' % (ref, hits[0][1], '/'.join(expect_types)))
                hits = typed
            if not hits:
                raise FormIdError('unresolved reference %s (not in this plugin or indexed masters %s)'
                                  % (ref, ', '.join(self.index.masters) or 'none'))
            # Later masters override earlier ones for the same EditorID.
            if len({h[2] & 0xFFFFFF for h in hits}) > 1 and len({h[0] for h in hits}) == 1:
                raise FormIdError('ambiguous reference %s: %s' % (
                    ref, ', '.join('%s %08X' % (h[1], h[2]) for h in hits)))
            pos, _type, form, *_ = max(hits, key=lambda h: h[0])
            return self._from_master(self.index.masters[pos], form)
        if not HEX8.match(ref):
            raise FormIdError('reference must be "@EditorID" or an 8-digit FormID: %r' % ref)
        form = int(ref, 16)
        top = form >> 24
        if top > self.self_byte:
            raise FormIdError('FormID %s has load-order byte %02X; this plugin has %d master(s)'
                              % (ref, top, len(self.masters)))
        if top == self.self_byte and form not in self.own.values():
            raise FormIdError('FormID %s is not a record in this plugin' % ref)
        return form

    def _from_master(self, master, form_in_master):
        # Inside a master file, its own records carry that master's master-count as top byte.
        return (self.masters.index(master) << 24) | (form_in_master & 0xFFFFFF)
