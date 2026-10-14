"""Deterministic, offline TV Guide performance probe.

Run from repository root: python tools/benchmark_tv_guide.py --iterations 20
No broadcaster endpoints are queried. Timings are environmental measurements,
not hardware-independent guarantees.
"""
import argparse
import json
import resource
import runpy
import statistics
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def measure(iterations):
    namespace = runpy.run_path(str(ROOT / "tests/test_original_runtime.py"))
    cls = namespace["GuideRuntimeTests"]
    test = cls(methodName="test_known_revision_skips_full_guide_payload")
    test.setUp()
    try:
        backend = test.backend
        samples = {"full_guide_ms": [], "unchanged_ms": [], "snapshot_ms": []}
        tracemalloc.start()
        first = backend.request("guide", "GET")
        revision = first["revision"]
        response_bytes = len(json.dumps(first, ensure_ascii=False).encode("utf-8"))
        for _ in range(iterations):
            start = time.perf_counter()
            backend.request("guide", "GET")
            samples["full_guide_ms"].append((time.perf_counter() - start) * 1000)
            start = time.perf_counter()
            reply = backend.request("guide", "GET", {"known_revision": revision})
            samples["unchanged_ms"].append((time.perf_counter() - start) * 1000)
            assert reply["unchanged"] and reply["revision"] == revision
            start = time.perf_counter()
            backend.state_snapshot()
            samples["snapshot_ms"].append((time.perf_counter() - start) * 1000)
        current, peak = tracemalloc.get_traced_memory()
        return {
            "iterations": iterations,
            "guide_json_bytes": response_bytes,
            "unchanged_json_bytes": len(json.dumps(reply).encode("utf-8")),
            "mean_ms": {key: round(statistics.mean(values), 3) for key, values in samples.items()},
            "p95_ms": {key: round(sorted(values)[min(len(values)-1, int(len(values)*0.95))], 3) for key, values in samples.items()},
            "python_allocated_peak_bytes": peak,
            "process_max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "scope": "offline fixture; cached operations only; no live provider I/O"
        }
    finally:
        tracemalloc.stop()
        test.doCleanups()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 10000:
        parser.error("iterations must be between 1 and 10000")
    print(json.dumps(measure(args.iterations), indent=2))
