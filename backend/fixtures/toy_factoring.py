#!/usr/bin/env python3
"""TOY cryptanalysis experiment: Pollard's rho (Brent variant) factoring of a SMALL synthetic semiprime.

This demonstrates the sandbox workflow (proposal -> approval -> isolated execution -> recorded evidence).
It is NOT a break of deployed cryptography. Moduli are capped at 64 bits and generated inside the
fixture, so the target is always synthetic and owned. Results must never be extrapolated to RSA-2048.

Params: modulus_bits (<= 64, default 48), trials (default 5), max_iterations (default 5_000_000), seed
"""
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _common import environment, summarize_ms, read_params, emit  # noqa: E402

FIXTURE_VERSION = "1.0.0"
MAX_BITS = 64


def is_probable_prime(n, rng, rounds=16):
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29):
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(rounds):
        a = rng.randrange(2, n - 1)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def random_prime(bits, rng):
    while True:
        c = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
        if is_probable_prime(c, rng):
            return c


def pollard_rho_brent(n, rng, max_iter):
    """Return (factor or None, iterations)."""
    if n % 2 == 0:
        return 2, 1
    y, c, m = rng.randrange(1, n), rng.randrange(1, n), 128
    g, r, q, it = 1, 1, 1, 0
    x = ys = y
    while g == 1:
        x = y
        for _ in range(r):
            y = (y * y + c) % n
        k = 0
        while k < r and g == 1:
            ys = y
            for _ in range(min(m, r - k)):
                y = (y * y + c) % n
                q = q * abs(x - y) % n
                it += 1
            g = math.gcd(q, n)
            k += m
            if it > max_iter:
                return None, it
        r *= 2
    if g == n:
        while True:
            ys = (ys * ys + c) % n
            g = math.gcd(abs(x - ys), n)
            it += 1
            if g > 1 or it > max_iter:
                break
    if g in (1, n):
        return None, it
    return g, it


def main():
    p = read_params()
    bits = int(p.get("modulus_bits", 48))
    trials = int(p.get("trials", 5))
    max_iter = int(p.get("max_iterations", 5_000_000))
    rng = random.Random(int(p.get("seed", 7)))
    if bits > MAX_BITS or bits < 16:
        emit({"fixture": "toy_factoring", "fixture_version": FIXTURE_VERSION, "status": "failed",
              "failures": [f"modulus_bits must be between 16 and {MAX_BITS}; refusing {bits}"]})
        return 2
    half = bits // 2
    results, iters, times = [], [], []
    for t in range(trials):
        pq = random_prime(half, rng), random_prime(bits - half, rng)
        n = pq[0] * pq[1]
        t0 = time.perf_counter()
        f, it = pollard_rho_brent(n, rng, max_iter)
        dt = time.perf_counter() - t0
        ok = f is not None and n % f == 0 and f not in (1, n)
        results.append({"trial": t, "n_bits": n.bit_length(), "found": ok, "iterations": it, "seconds": dt,
                        "factor_bits": f.bit_length() if ok else None})
        if ok:
            iters.append(it)
            times.append(dt * 1000)
    smallest_prime_bits = half
    expected_iter = math.sqrt(math.pi * 2 ** smallest_prime_bits / 2)  # heuristic E[iterations] ~ sqrt(pi p / 2)
    total_iter = sum(r["iterations"] for r in results)
    total_sec = sum(r["seconds"] for r in results)
    metrics = {
        "trials": trials, "successes": len(iters),
        "success_rate": len(iters) / trials if trials else 0,
        "iterations_median": sorted(iters)[len(iters) // 2] if iters else None,
        "iterations_mean": sum(iters) / len(iters) if iters else None,
        "expected_iterations_heuristic": expected_iter,
        "iterations_per_second": total_iter / total_sec if total_sec > 0 else None,
        "time_ms_median": summarize_ms(times).get("median"),
        "modulus_bits": bits,
    }
    emit({
        "fixture": "toy_factoring", "fixture_version": FIXTURE_VERSION, "status": "completed",
        "environment": environment(), "repeat_count": trials,
        "parameters": {"modulus_bits": bits, "trials": trials, "max_iterations": max_iter, "seed": p.get("seed", 7)},
        "scenarios": [{"id": f"trial_{r['trial']}", "name": f"factor {r['n_bits']}-bit synthetic semiprime",
                       "expected": "accept", "observed": "accept" if r["found"] else "reject", "pass": r["found"],
                       "detail": f"{r['iterations']} iterations, {r['seconds']*1000:.1f} ms"} for r in results],
        "metrics": metrics,
        "metric_definitions": {
            "iterations_per_second": "Pollard-rho iterations (one modular squaring + multiply + occasional gcd) per second in pure Python on the runner host.",
            "expected_iterations_heuristic": "sqrt(pi * p / 2) for the smallest prime factor p; birthday-bound heuristic, not a guarantee.",
            "success_rate": "Fraction of trials that found a non-trivial factor within max_iterations.",
        },
        "probability_model": "P(success within k iterations) ~ 1 - exp(-k^2 / (2p)) for smallest prime p (birthday heuristic).",
        "raw": {"trials": results},
        "failures": [],
        "limitations": [
            "TOY parameters (<= 64-bit modulus). Demonstrates the sandbox workflow; not evidence about any deployed key.",
            "Pollard rho scales as sqrt(p); it is irrelevant to RSA-2048 and must not be extrapolated to it.",
            "Pure-Python throughput; optimised implementations differ by orders of magnitude.",
        ],
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
