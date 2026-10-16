"""Reproduce theme-aware SVG wrappers without changing verified original artwork."""
import argparse
import base64
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def render(original, mime, theme, variant='original'):
    if mime not in ('image/png','image/svg+xml') or theme not in ('light','dark'):
        raise ValueError('Unsupported artwork format or theme')
    uri='data:'+mime+';base64,'+base64.b64encode(original).decode()
    image=f'<image href="{uri}" x="5" y="4" width="250" height="56" preserveAspectRatio="xMidYMid meet"/>'
    if variant in ('white','black'):
        ink='#fff' if variant=='white' else '#17191c'
        image='<defs><mask id="ink" style="mask-type:alpha">'+image+'</mask></defs>'+f'<rect width="260" height="64" fill="{ink}" mask="url(#ink)"/>'
    elif variant=='dark-wordmark':
        # Overprint only near-white ink. Keep coloured brand elements unchanged.
        image=('<defs><filter id="wordmark" color-interpolation-filters="sRGB">'
               '<feColorMatrix in="SourceGraphic" type="matrix" values="0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 5 5 5 0 -11.5" result="white"/>'
               '<feComposite in="white" in2="SourceAlpha" operator="in" result="mask"/>'
               '<feFlood flood-color="#17191c" result="ink"/><feComposite in="ink" in2="mask" operator="in" result="letters"/>'
               '<feMerge><feMergeNode in="SourceGraphic"/><feMergeNode in="letters"/></feMerge>'
               '</filter></defs>'+image.replace('/>',' filter="url(#wordmark)"/>'))
    elif variant!='original':
        raise ValueError('Unsupported artwork variant: '+variant)
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="260" height="64" viewBox="0 0 260 64" data-tv-guide-theme="{theme}">'+image+'</svg>\n'


def originals(svg):
    match=re.search(r'href="data:(image/[^;]+);base64,([^\"]+)"',svg)
    if not match:raise ValueError('Missing embedded original artwork')
    return base64.b64decode(match[2],validate=True),match[1]


def build(manifest, source_dir=None, output=None, check=False):
    metadata=json.loads(manifest.read_text())
    if not re.fullmatch('[a-z]{2}',metadata['country']):raise ValueError('Invalid country')
    library=None
    if check:
        spec=importlib.util.spec_from_file_location('_artwork_assets',ROOT/'custom_components/tv_guide/logo_assets.py')
        assets=importlib.util.module_from_spec(spec);spec.loader.exec_module(assets)
        library=assets.LogoLibrary();library.archive_root=ROOT/'tests/fixtures/logo-samples'
    for ident,item in metadata['channels'].items():
        for theme in ('light','dark'):
            source=item[theme]
            if check:
                svg=library.read(library.channels[metadata['country']+':'+ident][theme])[0].decode()
                data,mime=originals(svg)
                if mime!=source['mime']:raise ValueError('Artwork format mismatch: '+ident)
            else:
                data=(source_dir/source['file']).read_bytes()
            if sha256(data).hexdigest()!=source['sha256']:raise ValueError('Original artwork checksum mismatch: '+ident)
            expected=render(data,source['mime'],theme,source.get('variant','original'))
            if check:
                if svg!=expected:raise ValueError('Outdated artwork variant: '+ident+'/'+theme)
            else:
                output.mkdir(parents=True,exist_ok=True)
                (output/f'{ident}-{theme}.svg').write_text(expected)
    print(f"Verified {len(metadata['channels'])} light/dark artwork pairs ({metadata['country']})")


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path);parser.add_argument('--source-dir',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if not args.check and (args.source_dir is None or args.output is None):parser.error('Building requires --source-dir and --output')
    build(args.manifest,args.source_dir,args.output,args.check)
