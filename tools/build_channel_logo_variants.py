"""Build transparent dark variants from verified original artwork embedded in light SVGs."""
import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import re
import struct
import importlib.util

ROOT = Path(__file__).resolve().parents[1] / 'custom_components/tv_guide'


def render_dark(item, original, mime):
    uri = 'data:' + mime + ';base64,' + base64.b64encode(original).decode()
    image = f'<image href="{uri}" x="5" y="4" width="250" height="56" preserveAspectRatio="xMidYMid meet"/>'
    variant = item.get('dark_variant', 'original')
    if variant == 'white-wordmark':
        width, height = struct.unpack('>II', original[16:24])
        split = item['wordmark_start']
        if mime != 'image/png' or not original.startswith(b'\x89PNG\r\n\x1a\n') or not 0 < split < width:
            raise ValueError('Invalid wordmark geometry')
        image = (f'<defs><image id="mark" width="{width}" height="{height}" href="{uri}"/>'
                 f'<clipPath id="brand"><rect width="{split}" height="{height}"/></clipPath>'
                 f'<mask id="wordmark" maskUnits="userSpaceOnUse" x="{split}" y="0" width="{width-split}" height="{height}" style="mask-type:alpha"><use href="#mark"/></mask></defs>'
                 f'<svg x="5" y="4" width="250" height="56" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet">'
                 f'<use href="#mark" clip-path="url(#brand)"/><rect x="{split}" width="{width-split}" height="{height}" fill="#fff" mask="url(#wordmark)"/></svg>')
    elif variant == 'white':
        image = ('<defs><mask id="ink" maskUnits="userSpaceOnUse" x="0" y="0" width="260" height="64" style="mask-type:alpha">'
                 + image + '</mask></defs><rect width="260" height="64" fill="#fff" mask="url(#ink)"/>')
    elif variant != 'original':
        raise ValueError('Unknown dark variant: ' + variant)
    return '<svg xmlns="http://www.w3.org/2000/svg" width="260" height="64" viewBox="0 0 260 64" data-tv-guide-theme="dark">' + image + '</svg>\n'


def build(manifest, check=False, archives=None, output=None):
    spec=importlib.util.spec_from_file_location('_logo_variant_assets',ROOT/'logo_assets.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    library=module.LogoLibrary()
    library.archive_root=archives or ROOT.parents[1]/'tests/fixtures/logo-samples'
    metadata = json.loads(manifest.read_text())
    country = metadata['country']
    if not re.fullmatch('[a-z]{2}', country):
        raise ValueError('Invalid country')
    for ident, item in metadata['channels'].items():
        themes=library.channels[country+':'+ident]
        svg=library.read(themes['light'])[0].decode()
        match=re.search(r'href="data:(image/[^;]+);base64,([^\"]+)"',svg)
        if not match:
            raise ValueError('Missing embedded original: '+ident)
        mime,encoded=match.groups()
        original=base64.b64decode(encoded,validate=True)
        if sha256(original).hexdigest()!=item['expected_sha256'] or mime!=item['mime']:
            raise ValueError('Artwork provenance mismatch: '+ident)
        expected=render_dark(item,original,mime)
        if output is None or check:
            if library.read(themes['dark'])[0].decode()!=expected:
                raise ValueError('Outdated dark variant: '+ident)
        else:
            output.mkdir(parents=True,exist_ok=True)
            (output/f'{country}-{ident}-dark.svg').write_text(expected)
    print(f"Verified {len(metadata['channels'])} transparent dark logo variants ({country})")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--archives',type=Path)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    build(args.manifest,args.check,args.archives,args.output)
