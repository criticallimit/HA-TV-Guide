"""Offline download, integrity, interruption and retry behavior."""
from hashlib import sha256
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'custom_components/tv_guide'
spec=importlib.util.spec_from_file_location('_logo_download_tests',ROOT/'logo_download.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)
        self.library=SimpleNamespace(root=self.root,archive_root=self.root/'cache')
        self.data={'logos-000.zip':b'first package','logos-001.zip':b'second package'}
        self.manifest={'base_url':'https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/'+'a'*40+'/custom_components/tv_guide/logo_library/',
                       'archives':{name:{'size':len(data),'sha256':sha256(data).hexdigest()} for name,data in self.data.items()}}
        self.write_manifest()
        self.calls=[]
    def write_manifest(self):
        (self.root/'downloads.json').write_text(json.dumps(self.manifest))
    def opener(self,request,timeout):
        name=request.full_url.rsplit('/',1)[-1];self.calls.append(name)
        self.assertEqual(timeout,15)
        return BytesIO(self.data[name])
    def test_valid_download_atomic_files_and_resume_without_network(self):
        downloader=module.LogoDownload(self.library)
        downloader.run(lambda:False,self.opener)
        self.assertTrue(downloader.status()['ready'])
        self.assertEqual(downloader.status()['completed'],2)
        self.assertFalse(list(self.library.archive_root.glob('*.part')))
        restarted=module.LogoDownload(self.library)
        restarted.run(lambda:False,lambda *a,**k:self.fail('Cache downloaded twice'))
        self.assertTrue(restarted.status()['ready'])
    def test_failure_preserves_verified_package_and_retry_only_downloads_missing(self):
        downloader=module.LogoDownload(self.library)
        def failing(request,timeout):
            if request.full_url.endswith('001.zip'):raise OSError('offline')
            return self.opener(request,timeout)
        downloader.run(lambda:False,failing)
        self.assertEqual(downloader.status()['completed'],1)
        self.assertEqual(downloader.status()['error'],'download_failed')
        self.calls.clear();downloader.run(lambda:False,self.opener)
        self.assertEqual(self.calls,['logos-001.zip'])
        self.assertTrue(downloader.status()['ready'])
    def test_hash_size_and_partial_responses_never_become_installed_files(self):
        for data in (b'x'*100,b'bad',b'z'*len(self.data['logos-000.zip'])):
            downloader=module.LogoDownload(self.library)
            downloader.run(lambda:False,lambda *a,**k:BytesIO(data))
            self.assertFalse(downloader.status()['ready'])
            self.assertFalse(list(self.library.archive_root.glob('*')))
    def test_stop_removes_partial_file_and_opens_no_more_requests(self):
        stopped=[False]
        class Response(BytesIO):
            def read(self,size):stopped[0]=True;return super().read(size)
        downloader=module.LogoDownload(self.library)
        downloader.run(lambda:stopped[0],lambda *a,**k:Response(b'first package'))
        self.assertFalse(downloader.status()['running'])
        self.assertFalse(list(self.library.archive_root.glob('*')))
        downloader.run(lambda:True,lambda *a,**k:self.fail('opened after unload'))
    def test_corrupt_existing_file_is_replaced(self):
        self.library.archive_root.mkdir()
        (self.library.archive_root/'logos-000.zip').write_bytes(b'corrupt')
        downloader=module.LogoDownload(self.library)
        downloader.run(lambda:False,self.opener)
        self.assertEqual((self.library.archive_root/'logos-000.zip').read_bytes(),self.data['logos-000.zip'])
    def test_manifest_rejects_external_sources_and_unsafe_names(self):
        self.manifest['base_url']='https://example.org/'
        self.write_manifest()
        with self.assertRaises(ValueError):module.LogoDownload(self.library)
        self.setUp()
        self.manifest['archives']['../options.json']=self.manifest['archives'].pop('logos-000.zip')
        self.write_manifest()
        with self.assertRaises(ValueError):module.LogoDownload(self.library)
