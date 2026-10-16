"""Publish the small update descriptor after committing immutable logo packages/index."""
import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'custom_components/tv_guide'


def descriptor():
    modules = {}
    for name in ('logo_assets', 'logo_download',):
        spec = importlib.util.spec_from_file_location(name, COMPONENT / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules[name] = module
    folder = COMPONENT / 'logo_library'
    data = (folder / 'index.json').read_bytes()
    index = json.loads(data)
    modules['logo_assets'].LogoLibrary.validate_index(index)
    manifest = json.loads((folder / 'downloads.json').read_text(encoding='utf-8'))
    modules['logo_download'].validate_manifest(manifest, index['entries'])
    path = folder / 'updates.json'
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    fingerprint = {'size':len(data), 'sha256':sha256(data).hexdigest()}
    same_revision = previous.get('revision') == index['revision']
    if same_revision and (previous.get('index') != fingerprint or previous.get('archives') != manifest['archives']):
        raise ValueError('Changed logo contents require a new index revision')
    generation = previous.get('generation', 1)
    if not same_revision and previous:
        generation += 1
    if type(generation) is not int or not 0 < generation < 2**53:
        raise ValueError('Invalid logo update generation')
    return {'schema_version':1, 'generation':generation, 'revision':index['revision'],
            'index':fingerprint, **manifest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    options = parser.parse_args()
    path = COMPONENT / 'logo_library/updates.json'
    expected = json.dumps(descriptor(), indent=2) + '\n'
    if options.check:
        if not path.exists() or path.read_text(encoding='utf-8') != expected:
            raise SystemExit('Logo update descriptor is stale; run python tools/build_logo_updates.py')
        print('Logo update descriptor matches the bundled index and pinned packages')
    else:
        path.write_text(expected, encoding='utf-8')
        print('Updated', path.relative_to(ROOT))


if __name__ == '__main__':
    main()
