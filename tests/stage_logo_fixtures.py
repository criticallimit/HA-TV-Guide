"""Stage verified database samples for offline browser tests, outside the integration."""
from hashlib import sha256
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def stage():
    component=ROOT/'custom_components/tv_guide'
    index=json.loads((component/'logo_library/index.json').read_text())
    folder=ROOT/'work/test-logo-fixtures'/index['revision']
    for themes in index['channels'].values():
        for source in themes.values():
            entry=index['entries'][source]
            target=folder/source
            if target.exists() and sha256(target.read_bytes()).hexdigest()==entry['sha256']:continue
            with zipfile.ZipFile(ROOT/'tests/fixtures/logo-samples'/entry['archive']) as archive:data=archive.read(entry['member'])
            if sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Logo fixture checksum mismatch')
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    return folder

if __name__=='__main__':print(stage())
