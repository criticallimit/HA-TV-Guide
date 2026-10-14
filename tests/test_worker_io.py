"""Unloading stops future provider requests and chunk reads without changing IO."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

spec=importlib.util.spec_from_file_location('_tvguide_worker_io_tests',Path(__file__).resolve().parents[1]/'custom_components/tv_guide/worker_io.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class WorkerIOTests(unittest.TestCase):
    def test_unload_before_context_entry_closes_the_connection(self):
        closed=False
        response=Mock()
        wrapped=module.worker_urlopen(Mock(return_value=response),lambda:closed,'https://example.org')
        closed=True
        with self.assertRaises(RuntimeError):wrapped.__enter__()
        response.close.assert_called_once()

    def test_closed_runtime_never_opens_another_provider_request(self):
        opener=Mock()
        with self.assertRaises(RuntimeError):module.worker_urlopen(opener,lambda:True,'https://example.org',timeout=20)
        opener.assert_not_called()

    def test_late_connection_result_is_closed_before_reading(self):
        response=Mock();closed=False
        def opener(*args,**kwargs):
            nonlocal closed
            closed=True
            return response
        with self.assertRaises(RuntimeError):module.worker_urlopen(opener,lambda:closed,'https://example.org')
        response.close.assert_called_once()
        response.read.assert_not_called()

    def test_response_keeps_context_headers_and_blocks_next_read_on_unload(self):
        closed=False
        response=Mock(status=200,headers={'Content-Type':'application/xml'})
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.read.return_value=b'<tv>'
        opener=Mock(return_value=response)
        with module.worker_urlopen(opener,lambda:closed,'https://example.org',timeout=20) as wrapped:
            self.assertEqual(wrapped.status,200)
            self.assertEqual(wrapped.read(4),b'<tv>')
            closed=True
            with self.assertRaises(RuntimeError):wrapped.read(4)
        response.read.assert_called_once_with(4)
        response.__exit__.assert_called_once()
