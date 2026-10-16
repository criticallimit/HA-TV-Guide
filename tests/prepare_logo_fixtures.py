"""Download verified test samples from the same immutable database as the integration."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]

def prepare():
    component=ROOT/'custom_components/tv_guide'
    index=json.loads((component/'logo_library/index.json').read_text())
    manifest=json.loads((component/'logo_library/downloads.json').read_text())
    spec=importlib.util.spec_from_file_location('_logo_fixture_download',component/'logo_download.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.validate_manifest(manifest,index['entries'])
    names={'logos-000.zip','logos-002.zip','logos-017.zip'}
    names.update(index['entries'][source]['archive'] for themes in index['channels'].values() for source in themes.values())
    folder=ROOT/'tests/fixtures/logo-samples';folder.mkdir(parents=True,exist_ok=True)
    for name in sorted(names):
        item=manifest['archives'][name];target=folder/name
        if target.is_file() and target.stat().st_size==item['size'] and sha256(target.read_bytes()).hexdigest()==item['sha256']:continue
        request=Request(manifest['base_url']+name,headers={'User-Agent':'HA-TV-Guide-tests','Accept-Encoding':'identity'})
        with urlopen(request,timeout=30) as response:data=response.read(item['size']+1)
        if len(data)!=item['size'] or sha256(data).hexdigest()!=item['sha256']:raise ValueError('Invalid test logo package: '+name)
        temporary=target.with_suffix('.part');temporary.write_bytes(data);temporary.replace(target)
    print(f'Verified {len(names)} immutable logo sample packages; tests run offline from here')

if __name__=='__main__':prepare()
