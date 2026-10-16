"""Build the static translated screenshot galleries; never modifies README.md."""
import argparse
from html import escape
import json
from pathlib import Path
import unicodedata

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs'
URL='https://criticallimit.github.io/HA-TV-Guide/'
IMAGES=[('program-overview','overview'),('my-channels','channels'),('other-times','times'),('dashboard-card','card')]


def build():
    locales=json.loads((DOCS/'screenshots/locales.json').read_text())
    registry=json.loads((ROOT/'custom_components/tv_guide/languages.json').read_text())
    if set(locales)!=set(registry):raise ValueError('Gallery translations must cover every registered language')
    keys=set(locales['en'])
    for code,text in locales.items():
        if set(text)!=keys or any(not isinstance(value,str) or not value.strip() for value in text.values()):
            raise ValueError('Incomplete gallery translation: '+code)
    names={code:item['name'].split(' (')[0] for code,item in registry.items()}
    order=sorted(names,key=lambda code:unicodedata.normalize('NFKD',names[code].casefold()))
    flags={'en':'gb','da':'dk','nb':'no','sv':'se'}
    def page(code,entry=False):
        t=locales[code];prefix='' if entry else '../';home=prefix+('index.html' if code=='de' else code+'.html')
        gallery_prefix='screenshots/' if entry else ''
        nav='\n'.join(f'<a href="{gallery_prefix}{lang}.html" lang="{lang}"'+(' aria-current="page"' if lang==code else '')+f'><span class="flagwrap"><img src="{prefix}flags/{flags.get(lang,lang)}.svg" alt=""></span><span>{escape(names[lang])}</span></a>' for lang in order)
        shots='\n'.join(f'<article class="shot"><a class="shot-link" href="{gallery_prefix}{code}/{image}.webp" target="_blank" rel="noopener"><img src="{gallery_prefix}{code}/{image}.webp" alt="{escape(t[key],quote=True)}" width="1400" height="1050" loading="'+('eager' if image=='program-overview' else 'lazy')+f'"></a><h2>{escape(t[key])}</h2><p>{escape(t[key+"_text"])}</p></article>' for image,key in IMAGES)
        alternatives='\n'.join(f'<link rel="alternate" hreflang="{lang}" href="{URL}screenshots/{lang}.html">' for lang in order)
        canonical=URL+('screenshots.html' if entry else 'screenshots/'+code+'.html')
        redirect='<script src="site-language.js" data-gallery-entry data-languages="'+' '.join(order)+'"></script>' if entry else '<script src="../site-language.js" defer></script>'
        return f'''<!doctype html>
<html lang="{code}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(t['gallery'])} – TV Guide</title><meta name="description" content="{escape(t['intro'],quote=True)}">
<link rel="canonical" href="{canonical}">{alternatives}<link rel="alternate" hreflang="x-default" href="{URL}screenshots.html">
<meta property="og:title" content="{escape(t['gallery'],quote=True)} – TV Guide"><meta property="og:description" content="{escape(t['intro'],quote=True)}"><meta property="og:url" content="{canonical}"><meta property="og:locale" content="{code}">
{redirect}<link rel="stylesheet" href="{gallery_prefix}gallery.css"></head><body><div class="wrap">
<header><a class="brand" href="{home}">TV GUIDE</a><div class="header-right"><nav aria-label="Navigation"><a href="{home}">{escape(t['home'])}</a><a href="{home}#installation">{escape(t['installation'])}</a><a href="https://github.com/criticallimit/HA-TV-Guide">GitHub ↗</a></nav><details class="language"><summary aria-label="{escape(t['language'],quote=True)}"><span class="flagwrap"><img src="{prefix}flags/{flags.get(code,code)}.svg" alt=""></span><span>{escape(names[code])}</span></summary><div class="language-menu">{nav}</div></details></div></header>
<main><section class="hero"><div class="eyebrow">TV Guide · {escape(t['eyebrow'])}</div><h1>{escape(t['title'])}</h1><p class="intro">{escape(t['intro'])}</p></section><section class="gallery" aria-label="{escape(t['gallery'],quote=True)}">{shots}</section><p class="samples">{escape(t['samples'])}</p>
<section class="cta"><h2>{escape(t['cta'])}</h2><p>{escape(t['free'])}</p><a class="button" href="https://my.home-assistant.io/redirect/hacs_repository/?owner=criticallimit&amp;repository=HA-TV-Guide&amp;category=integration">{escape(t['install'])}</a></section></main>
<footer><span>TV Guide · criticallimit</span><span><a href="{home}">{escape(t['home'])}</a> · <a href="https://github.com/criticallimit/HA-TV-Guide/issues">{escape(t['help'])}</a></span></footer></div></body></html>
'''
    outputs={DOCS/'screenshots'/f'{code}.html':page(code) for code in order}
    outputs[DOCS/'screenshots.html']=page('en',entry=True)
    return outputs


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    for path,text in build().items():
        if args.check:
            if not path.exists() or path.read_text()!=text:raise SystemExit('Outdated gallery: '+str(path))
        else:path.write_text(text)
    print('Translated galleries match all ten registered languages')
