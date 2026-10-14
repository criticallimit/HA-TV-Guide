"""Public logo route handles damaged installed assets without HTTP 500 errors."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch
from zipfile import BadZipFile

ROOT = Path(__file__).resolve().parents[1] / 'custom_components/tv_guide'
PKG = '_tvguide_logo_view_tests'
pkg = types.ModuleType(PKG)
pkg.__path__ = [str(ROOT)]
http = types.ModuleType('homeassistant.components.http')
http.HomeAssistantView = object
aiohttp = types.ModuleType('aiohttp')
class Response:
    def __init__(self, *, status=200, body=None, content_type=None, headers=None):
        self.status, self.body, self.content_type = status, body, content_type
        self.headers = headers or {}
aiohttp.web = types.SimpleNamespace(Response=Response)
with patch.dict(sys.modules, {PKG: pkg, 'homeassistant.components.http': http, 'aiohttp': aiohttp}):
    spec = importlib.util.spec_from_file_location(PKG + '.logo_view', ROOT / 'logo_view.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


class LogoViewTests(unittest.IsolatedAsyncioTestCase):
    def make_view(self, *, known=True, damage=None):
        library = Mock()
        library.contains.return_value = known
        library.render.side_effect = damage
        library.render.return_value = (b'<svg/>', 'image/svg+xml')
        executed = []
        async def executor(fn, *args):
            executed.append(args)
            return fn(*args)
        with patch.object(module, 'bundled_logo_library', return_value=library):
            view = module.TVGuideLogoView(types.SimpleNamespace(async_add_executor_job=executor))
        return view, library, executed

    async def test_unknown_image_never_reads_a_bundle(self):
        view, library, executed = self.make_view(known=False)
        response = await view.get(types.SimpleNamespace(query={}), 'unknown')
        self.assertEqual(response.status, 404)
        library.render.assert_not_called()
        self.assertEqual(executed, [])

    async def test_damaged_archive_returns_not_found(self):
        view, library, executed = self.make_view(damage=BadZipFile('Invalid archive'))
        response = await view.get(types.SimpleNamespace(query={}), 'logos/example.svg')
        self.assertEqual(response.status, 404)
        self.assertEqual(executed, [('logos/example.svg', False)])

    async def test_known_image_preserves_mime_cache_headers_and_normalization(self):
        view, library, executed = self.make_view()
        response = await view.get(types.SimpleNamespace(query={'normalize': '1'}), 'logos/example.svg')
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b'<svg/>')
        self.assertEqual(response.content_type, 'image/svg+xml')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['Cache-Control'], 'public, max-age=86400')
        self.assertEqual(executed, [('logos/example.svg', True)])
