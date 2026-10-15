"""Read the integration's complete offline logo library from deduplicated bundles."""
import base64
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import zipfile


class LogoLibrary:
    """Only packaged, indexed images are readable; no external files or downloads."""

    def __init__(self, root=None):
        self.root=Path(root) if root is not None else Path(__file__).parent/'logo_library'
        self.archive_root = self.root
        index=json.loads((self.root/'index.json').read_text(encoding='utf-8'))
        self.entries=index['entries']
        self.revision=index['revision']
        for source,item in self.entries.items():
            if not source.startswith('logos/') or '..' in PurePosixPath(source).parts:
                raise ValueError('Invalid bundled logo path')
            if not re.fullmatch(r'logos-\d{3}\.zip',item['archive']) or not re.fullmatch(r'[0-9a-f]{64}',item['member']):
                raise ValueError('Invalid bundled logo object')

    def contains(self, source):
        return source in self.entries

    def configure_cache(self, path):
        path = Path(path) / self.revision
        if self.archive_root != path:
            self._render_cached.cache_clear()
            self.archive_root = path

    def read(self, source):
        item=self.entries.get(source)
        if item is None:
            raise KeyError(source)
        with zipfile.ZipFile(self.archive_root/item['archive']) as archive:
            data=archive.read(item['member'])
        if sha256(data).hexdigest()!=item['sha256']:
            raise ValueError('Damaged bundled logo')
        return data,item['mime']

    def render(self, source, normalize=False):
        """Make referenced Europe artwork self-contained for an HTML img element."""
        return self._render_cached(source,normalize)

    @lru_cache(maxsize=128)
    def _render_cached(self, source, normalize):
        data,mime=self.read(source)
        if mime=='image/svg+xml':
            svg=data.decode('utf-8')
            def embed(match):
                reference=match[1]
                if reference.startswith(('data:','http:','https:','#')):
                    return match[0]
                target=posixpath.normpath(posixpath.join(posixpath.dirname(source),reference))
                if not target.startswith('logos/europe/assets/'):
                    raise ValueError('Invalid relative logo image')
                artwork,artwork_mime=self.read(target)
                return 'href="data:'+artwork_mime+';base64,'+base64.b64encode(artwork).decode('ascii')+'"'
            svg=re.sub(r'href="([^\"]+)"',embed,svg)
            data=svg.encode('utf-8')
        if normalize:
            encoded=base64.b64encode(data).decode('ascii')
            data=f'''<svg xmlns="http://www.w3.org/2000/svg" width="260" height="64" viewBox="0 0 260 64">
  <image x="5" y="4" width="250" height="56" preserveAspectRatio="xMidYMid meet"
         href="data:{mime};base64,{encoded}"/>
</svg>
'''.encode('utf-8')
            mime='image/svg+xml'
        return data,mime


@lru_cache(maxsize=1)
def bundled_logo_library():
    """Build the shared read-only index in an executor, once per HA process."""
    return LogoLibrary()
