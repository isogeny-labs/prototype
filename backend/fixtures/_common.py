"""Shared helpers for fixtures (statistics, environment capture, timing). No app imports."""
import json
import platform
import statistics
import sys
import time
import tracemalloc


def environment():
    env = {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
    }
    try:
        import cryptography
        from cryptography.hazmat.backends.openssl import backend
        env["cryptography"] = cryptography.__version__
        env["openssl"] = backend.openssl_version_text()
    except Exception:  # pragma: no cover
        pass
    try:
        import dilithium_py  # noqa: F401
        from importlib.metadata import version
        env["dilithium_py"] = version("dilithium-py")
    except Exception:
        pass
    return env


def summarize_ms(samples):
    if not samples:
        return {}
    s = sorted(samples)
    n = len(s)

    def pct(p):
        k = min(n - 1, max(0, int(round(p * (n - 1)))))
        return s[k]

    return {
        "min": s[0],
        "median": statistics.median(s),
        "mean": statistics.fmean(s),
        "p95": pct(0.95),
        "max": s[-1],
        "stdev": statistics.pstdev(s) if n > 1 else 0.0,
        "n": n,
    }


def timed(fn, repeats):
    """Return list of wall-clock ms per call."""
    out = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t0) * 1000.0)
    return out


def peak_alloc_kb(fn):
    """Peak Python-heap allocation during one call, in KiB (tracemalloc). NOT device RAM."""
    tracemalloc.start()
    tracemalloc.reset_peak()
    fn()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak / 1024.0


def read_params():
    raw = sys.stdin.read()
    return json.loads(raw) if raw.strip() else {}


def emit(result):
    sys.stdout.write(json.dumps(result, indent=1, sort_keys=True))
    sys.stdout.flush()


MEMORY_DEFINITION = ("Peak Python heap allocation during a single verify call measured with tracemalloc, "
                     "in KiB. This is an interpreter-level proxy, not device RAM, stack or flash usage.")
TIME_DEFINITION = ("Wall-clock time per call (time.perf_counter) in milliseconds on the runner host, "
                   "across `repeat_count` sequential calls after one warm-up. Not device timing.")
