"""Create synthetic disposable acceptance inputs; never builds/installs or interacts with GECK/FNV."""
import argparse
import hashlib
import json
from pathlib import Path


def create(output, game_root, helper, *, size=0, shape='comments', references=0):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    records, metrics = {}, {}
    for index in range(9):
        edid = 'HelloRelScript%02d' % index
        source = 'scn %s\r\nshort Count\r\nbegin GameMode\r\n' % edid
        source += 'set Count to 1\r\n' if index == 0 else 'set Count to HelloRelQuest00.Count\r\n'
        if index == 0:
            for ref in range(references):
                source += 'set Count to HelloRelGlobal%04d\r\n' % ref
            unit = {'comments': '; synthetic source padding ' + 'x' * 80 + '\r\n',
                    'flat': 'if Count == 0\r\nset Count to 1\r\nendif\r\n',
                    'elseif': 'elseif Count == 0\r\nset Count to 1\r\n'}[shape]
            if shape == 'elseif' and size:
                source += 'if Count == 1\r\nset Count to 0\r\n'
            while len(source) + len(unit) + 7 < size:
                source += unit
            if shape == 'elseif' and size:
                source += 'endif\r\n'
        source += 'end\r\n'
        payload = source.encode('cp1252')
        (output / (edid + '.gek')).write_bytes(payload)
        metrics[edid] = {'characters': len(source), 'sourceSha256': hashlib.sha256(payload).hexdigest()}
        records[edid] = {'type': 'SCPT', 'source': edid + '.gek', 'script_type': 'quest'}
        records['HelloRelQuest%02d' % index] = {'type': 'QUST', 'fields': [
            {'tag': 'SCRI', 'form': '@' + edid}, {'tag': 'FULL', 'text': 'Disposable reliability quest'},
            # QUST DATA: flags/priority/padding/float delay (xEdit FNV record definition).
            {'tag': 'DATA', 'hex': '003200000000803f'}]}
    for index in range(references):
        records['HelloRelGlobal%04d' % index] = {'type': 'GLOB', 'fields': [
            {'tag': 'FNAM', 'hex': '73'}, {'tag': 'FLTV', 'float': 0}]}
    spec = {'schema': 1, 'project_id': 'hello-reliability-v040', 'plugin': 'HelloReliability.esp',
            'author': 'GECK MCP synthetic acceptance fixture', 'masters': ['FalloutNV.esm'], 'records': records}
    profile = {'schema_version': 1, 'project_id': spec['project_id'], 'launcher': 'native',
               'game_root': str(Path(game_root).resolve()), 'plugin': spec['plugin'], 'records': [],
               'state_dir': str((output / 'state').resolve()), 'helper': str(Path(helper).resolve()),
               'spec': str((output / 'fixture.spec.json').resolve())}
    for name, data in [('fixture.spec.json', spec), ('project.json', profile),
                       ('inputs.json', {'shape': shape, 'requestedCharacters': size, 'references': references,
                                        'scripts': metrics, 'installed': False})]:
        (output / name).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    return {'project': str((output / 'project.json').resolve()), 'inputs': metrics, 'installed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--game-root', required=True, type=Path)
    parser.add_argument('--helper', required=True, type=Path)
    parser.add_argument('--size', type=int, default=0)
    parser.add_argument('--shape', choices=['comments', 'flat', 'elseif'], default='comments')
    parser.add_argument('--references', type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.size <= 1024 * 1024 or not 0 <= args.references <= 4096:
        parser.error('size must be 0..1048576 and references 0..4096')
    print(json.dumps(create(args.output, args.game_root, args.helper, size=args.size,
                            shape=args.shape, references=args.references)))
