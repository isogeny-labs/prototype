"""Adapter loading for fixtures.

Two adapter kinds:
* profile  — an established library profile from sigschemes (cryptography/OpenSSL or the ML-DSA reference).
* module   — a customer-supplied Python module (source snapshot) exposing the adapter interface:
      ADAPTER = {"name": str, "version": str, "algorithm": str, "library": str}
      keygen() -> (pk, sk)
      sign(sk, msg: bytes) -> bytes
      verify(pk, msg: bytes, sig: bytes) -> bool        # must not raise
      public_key_bytes(pk) -> bytes
      public_key_from_bytes(b: bytes) -> pk             # optional; needed for official test vectors
      private_key_from_bytes(b: bytes) -> sk            # optional; needed for official test vectors
A module is loaded only inside the isolated runner, never at import time by the platform.
"""
from __future__ import annotations

import importlib.util
import os
import sys


class ProfileAdapter:
    kind = "profile"

    def __init__(self, profile: str):
        from sigschemes import get_scheme, SCHEMES  # noqa: F401
        self.scheme = get_scheme(profile)
        self.name, self.version = profile, "catalog"
        self.algorithm, self.library = profile, self.scheme.library
        self.production_grade = self.scheme.production_grade
        self.notes = self.scheme.notes

    def keygen(self):
        return self.scheme.keygen()

    def sign(self, sk, msg):
        return self.scheme.sign(sk, msg)

    def verify(self, pk, msg, sig):
        return self.scheme.verify(pk, msg, sig)

    def public_key_bytes(self, pk):
        return self.scheme.pk_bytes(pk)

    def public_key_from_bytes(self, b):
        return self.scheme.pk_from_bytes(b)

    def private_key_from_bytes(self, b):
        return self.scheme.sk_from_bytes(b)


class ModuleAdapter:
    kind = "module"

    def __init__(self, path: str):
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        spec = importlib.util.spec_from_file_location("customer_adapter", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["customer_adapter"] = mod
        spec.loader.exec_module(mod)
        for fn in ("keygen", "sign", "verify", "public_key_bytes"):
            if not callable(getattr(mod, fn, None)):
                raise AttributeError(f"adapter module lacks {fn}()")
        meta = getattr(mod, "ADAPTER", {}) or {}
        self.mod = mod
        self.name, self.version = meta.get("name", "customer-adapter"), meta.get("version", "unknown")
        self.algorithm, self.library = meta.get("algorithm", "unknown"), meta.get("library", "unknown")
        self.production_grade = None
        self.notes = "Customer-supplied adapter; correctness of the adapter itself is part of what is under test."

    def keygen(self):
        return self.mod.keygen()

    def sign(self, sk, msg):
        return self.mod.sign(sk, msg)

    def verify(self, pk, msg, sig):
        try:
            return bool(self.mod.verify(pk, msg, sig))
        except Exception as e:  # an adapter that raises on malformed input is recorded as 'raised', not as reject
            raise RuntimeError(f"adapter.verify raised {type(e).__name__}: {e}") from e

    def public_key_bytes(self, pk):
        return self.mod.public_key_bytes(pk)

    def public_key_from_bytes(self, b):
        fn = getattr(self.mod, "public_key_from_bytes", None)
        if not fn:
            raise NotImplementedError("adapter has no public_key_from_bytes")
        return fn(b)

    def private_key_from_bytes(self, b):
        fn = getattr(self.mod, "private_key_from_bytes", None)
        if not fn:
            raise NotImplementedError("adapter has no private_key_from_bytes")
        return fn(b)


def load_adapter(spec: dict):
    kind = (spec or {}).get("kind", "profile")
    if kind == "profile":
        return ProfileAdapter(spec.get("profile", "ed25519"))
    if kind == "module":
        return ModuleAdapter(spec["path"])
    raise ValueError(f"unknown adapter kind {kind}")
