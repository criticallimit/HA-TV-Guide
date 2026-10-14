"""Regression tests for the native guide's read-only fast path."""
import ast
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / "custom_components/tv_guide/original_coordinator.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
CLASS = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "TVGuideOriginalCoordinator")
METHOD = next(node for node in CLASS.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_original_request")
# Exercise the real method without importing Home Assistant in offline unit tests.
NAMESPACE = {"RuntimeError": RuntimeError}
exec(compile(ast.Module(body=[METHOD], type_ignores=[]), str(SOURCE), "exec"), NAMESPACE)


class FastReadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        async def executor(fn, *args):
            self.calls.append(("request", args))
            return fn(*args)
        async def sync():
            self.calls.append(("sync",))
        self.coordinator = SimpleNamespace(
            _closed=False,
            hass=SimpleNamespace(async_add_executor_job=executor),
            backend=SimpleNamespace(request=lambda *args: {"channels": [], "ok": True}),
            _async_sync=sync,
        )

    async def test_cached_guide_read_skips_snapshot(self):
        response = await NAMESPACE["async_original_request"](self.coordinator, "guide")
        self.assertEqual(response["channels"], [])
        self.assertEqual([item[0] for item in self.calls], ["request"])

    async def test_settings_and_channel_reads_skip_snapshot(self):
        for endpoint in ("settings", "personal-channels", "channels", "status"):
            self.calls.clear()
            await NAMESPACE["async_original_request"](self.coordinator, endpoint)
            self.assertEqual([item[0] for item in self.calls], ["request"])

    async def test_mutation_updates_entities(self):
        await NAMESPACE["async_original_request"](self.coordinator, "settings", "POST", {"language": "de"})
        self.assertEqual([item[0] for item in self.calls], ["request", "sync"])

    async def test_refresh_updates_entities(self):
        await NAMESPACE["async_original_request"](self.coordinator, "refresh")
        self.assertEqual([item[0] for item in self.calls], ["request", "sync"])

    async def test_unloaded_coordinator_rejects_request(self):
        self.coordinator._closed = True
        with self.assertRaises(RuntimeError):
            await NAMESPACE["async_original_request"](self.coordinator, "guide")
        self.assertFalse(self.calls)


if __name__ == "__main__":
    unittest.main()
