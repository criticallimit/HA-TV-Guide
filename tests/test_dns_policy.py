"""Offline tests for DNS rebinding policy."""
import importlib.util
import unittest
from pathlib import Path


def load_module(name):
    """Load pure helpers without shadowing standard-library modules."""
    path = Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

_module = load_module("dns_policy")
validate_resolved_addresses = _module.validate_resolved_addresses


class DNSPolicyTests(unittest.TestCase):
    def test_public_addresses(self):
        records = [{"host": "8.8.8.8"}, {"host": "2606:4700:4700::1111"}]
        self.assertEqual(validate_resolved_addresses(records), records)

    def test_private_or_mixed_answers(self):
        for records in (
            [], [{"host": "127.0.0.1"}], [{"host": "169.254.169.254"}],
            [{"host": "::1"}], [{"host": "8.8.8.8"}, {"host": "10.1.0.1"}],
            [{"host": "not-an-ip"}], [{}],
        ):
            with self.subTest(records=records), self.assertRaises(ValueError):
                validate_resolved_addresses(records)


if __name__ == "__main__":
    unittest.main()
