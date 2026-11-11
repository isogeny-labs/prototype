#!/usr/bin/env python3
"""control-slow -- A DELIBERATELY SLOWED CONTROL. DO NOT USE FOR ANYTHING REAL.

Part of the Isogeny Evidence Lab demo. The speed test also measures this slowed copy of the
component. It is the same component with a stated, modest delay (DELAY_MS) added to every
sign and every verify, inside the timed part of `bench`. A speed test that is working must
flag it as slower: if it doesn't, the test run can't be trusted.

How it is called:  slow.py <path-to-component> keygen|sign|verify|info|bench
(JSON on standard input, JSON on standard output). The path is given by our own test
harness from its fixed table, never by a user or a file. Standard library only.
"""
import importlib.util
import json
import sys
import time

NAME = "control-slow"
DELAY_MS = 6.0
USAGE = "usage: slow.py <path-to-component> keygen|sign|verify|info|bench  (JSON on stdin, JSON on stdout)"


def slowed(fn):
    def wrapper(req):
        end = time.perf_counter() + DELAY_MS / 1000.0
        while time.perf_counter() < end:  # busy-wait: steadier than sleep for a few milliseconds
            pass
        return fn(req)
    return wrapper


def main(argv):
    if len(argv) != 3 or argv[2] not in ("keygen", "sign", "verify", "info", "bench"):
        print(json.dumps({"error": USAGE}))
        return 2
    try:
        spec = importlib.util.spec_from_file_location("slowed_component", argv[1])
        real = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(real)
    except (OSError, ImportError, SyntaxError, AttributeError):
        print(json.dumps({"error": "the component to slow down could not be loaded"}))
        return 2
    inner_info = real.cmd_info
    real.cmd_sign = real.COMMANDS["sign"] = slowed(real.cmd_sign)  # bench looks these names up when it runs
    real.cmd_verify = real.COMMANDS["verify"] = slowed(real.cmd_verify)
    real.COMMANDS["info"] = lambda req: {
        **inner_info(req), "name": NAME, "wraps": f"{real.NAME} {real.VERSION}", "delay_ms": DELAY_MS,
        "control": f"deliberately slowed: {DELAY_MS} ms added to every sign and every verify"}
    return real.main(["slow.py", argv[2]])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
