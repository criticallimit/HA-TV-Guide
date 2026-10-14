"""Read-only import of the reference frontend into this native integration."""
import ast
import base64
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

reference = Path(sys.argv[1]).resolve()
target = Path('custom_components/tv_guide/frontend/app')
target.mkdir(parents=True, exist_ok=True)
files=['index.html','styles.css','guide-core.js','channel-picker.js','translations.js','i18n.js','app.js']
provenance={}
for name in files:
    source=reference/'tv-guide'/'www'/name
    if name not in ("index.html","app.js") or not (target/name).exists():
        shutil.copyfile(source,target/name)
    # Preserve native RPC/configuration adaptations on subsequent imports.
    provenance[name]=hashlib.sha256(source.read_bytes()).hexdigest()
shutil.copytree(reference/'tv-guide'/'www'/'fonts',target/'fonts',dirs_exist_ok=True)
shutil.copyfile(reference/'tv-guide'/'icon.png',target/'icon.png')
shutil.copyfile(reference/'THIRD_PARTY_NOTICES.md',Path('THIRD_PARTY_NOTICES.md'))

# Reuse the reference's pure logo selection/normalization helpers without
# importing its runtime, running its server, or writing to its checkout.
base=reference/'tv-guide'
lib=json.loads((base/'data'/'logo_library.json').read_text(encoding='utf-8'))
updates=base/'data'/'logo_updates.json'
if updates.is_file():
    for part in json.loads(updates.read_text(encoding='utf-8'))['library_parts']:
        extra=json.loads((base/'data'/part).read_text(encoding='utf-8'))
        lib['channels'].update(extra['channels']);lib['assets'].update(extra['assets'])
europe=json.loads((base/'data'/'europe_logo_library.json').read_text(encoding='utf-8'))
ns={'base64':base64,'html':html,'re':re,'LOGO_LIBRARY':lib,'EUROPE_LOGO_LIBRARY':europe}
source=(base/'tvguide'/'services.py').read_text(encoding='utf-8')
tree=ast.parse(source)
for node in tree.body:
    if isinstance(node,ast.FunctionDef) and node.name in ('_europe_logo_key','_europe_logo_source','_logo_source_for_channel','_normalized_logo_svg','_normalized_text_logo_svg'):
        exec(compile(ast.Module(body=[node],type_ignores=[]),'reference_logo_helpers','exec'),ns)
logo_map={}
for catalog_path in Path('custom_components/tv_guide/catalogs').glob('*.json'):
    country='de' if catalog_path.stem=='channels' else catalog_path.stem.split('_')[-1]
    channels=json.loads(catalog_path.read_text(encoding='utf-8'))['channels']
    for channel in channels:
        channel={**channel,'source_country':country}
        logos={}
        for theme in ('light','dark'):
            path=ns['_logo_source_for_channel'](channel,theme)
            if path:
                asset=(base/'www'/path).resolve()
                assert (base/'www').resolve() in asset.parents
                data=asset.read_bytes()
                if path.startswith('logos/europe/'):
                    text=data.decode('utf-8')
                    def embed(match):
                        image=(asset.parent/match[1]).resolve()
                        assert (base/'www'/'logos'/'europe'/'assets').resolve() in image.parents
                        mime='image/png' if image.suffix=='.png' else 'image/svg+xml' if image.suffix=='.svg' else 'image/webp'
                        return 'href="data:'+mime+';base64,'+base64.b64encode(image.read_bytes()).decode('ascii')+'"'
                    data=re.sub(r'href="(\.\./assets/[^\"]+)"',embed,text).encode('utf-8')
                elif not path.startswith(('logos/library/','logos/uk/')):
                    data=ns['_normalized_logo_svg'](data,'image/svg+xml',theme).encode('utf-8')
            else:
                data=ns['_normalized_text_logo_svg'](channel['name'],theme).encode('utf-8')
            output=target/'logos'/f'{country}-{channel["id"]}-{theme}.svg'
            output.parent.mkdir(exist_ok=True)
            output.write_bytes(data)
            logos['logo_normalized_'+theme]='logos/'+output.name
        logo_map.setdefault(country,{})[channel['id']]=logos
(target/'logo_catalog.json').write_text(json.dumps(logo_map,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
sha=subprocess.check_output(['git','-C',str(reference),'rev-parse','HEAD'],text=True).strip()
(target/'REFERENCE.json').write_text(json.dumps({'repository':'criticallimit/TV-Guide','commit':sha,'source_sha256':provenance},indent=2)+'\n',encoding='utf-8')
print('Imported reference UI and',sum(len(v) for v in logo_map.values()),'main-channel logo pairs; reference checkout unchanged')
