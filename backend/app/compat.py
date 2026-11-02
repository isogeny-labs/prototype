"""Compatibility and safety checks for imported source snapshots.

Importing code never executes it. A snapshot is statically checked (AST) against the adapter interface and an import
allowlist. This is a COMPATIBILITY gate, not a security boundary: the sandbox runner (subprocess, rlimits, no
network, empty environment) is the boundary. Recognised private-key formats are rejected on upload.
"""
from __future__ import annotations

import ast
import io
import re
import zipfile

ALLOWED_IMPORT_ROOTS = {"cryptography", "hashlib", "hmac", "secrets", "struct", "typing", "dataclasses", "base64", "json",
                        "math", "dilithium_py", "binascii", "collections", "functools", "itertools", "enum", "abc", "os"}
ALLOWED_OS_ATTRS = {"urandom"}
FORBIDDEN_CALLS = {"exec", "eval", "compile", "__import__", "open", "input", "breakpoint"}
FORBIDDEN_MODULES = {"subprocess", "socket", "importlib", "ctypes", "sys", "shutil", "pathlib", "http", "urllib", "requests",
                     "multiprocessing", "threading", "signal", "pickle", "marshal", "code", "pty", "ssl"}
REQUIRED_FUNCTIONS = ("keygen", "sign", "verify", "public_key_bytes")
OPTIONAL_FUNCTIONS = ("public_key_from_bytes", "private_key_from_bytes")
SECRET_PATTERNS = [re.compile(p) for p in (
    r"-----BEGIN (RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----", r"PuTTY-User-Key-File", r"\bsk-ant-[A-Za-z0-9_\-]{10,}",
    r"\bAKIA[0-9A-Z]{16}\b", r"\bghp_[A-Za-z0-9]{20,}", r"(?i)\bBEGIN PGP PRIVATE KEY BLOCK\b")]
MAX_SNAPSHOT_BYTES = 2_000_000


def scan_secrets(data: bytes) -> list[str]:
    text = data.decode("utf-8", errors="ignore")
    return [p.pattern for p in SECRET_PATTERNS if p.search(text)]


def extract_snapshot(data: bytes, filename: str) -> dict[str, bytes]:
    """Return {relative path: bytes}. Accepts a single .py file or a zip. Rejects traversal, symlinks and oversize."""
    if len(data) > MAX_SNAPSHOT_BYTES:
        raise ValueError(f"snapshot exceeds {MAX_SNAPSHOT_BYTES} bytes")
    if filename.endswith(".py"):
        return {"adapter.py": data}
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise ValueError("snapshot must be a .py file or a .zip archive")
    out, total = {}, 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            name = info.filename
            if name.endswith("/"):
                continue
            if name.startswith(("/", "\\")) or ".." in name.split("/") or ".." in name.split("\\"):
                raise ValueError(f"unsafe path in archive: {name}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"symlinks are not allowed: {name}")
            total += info.file_size
            if total > MAX_SNAPSHOT_BYTES:
                raise ValueError("archive contents exceed the size limit")
            out[name] = z.read(info)
    return out


def check_adapter_source(src: bytes) -> dict:
    """Static compatibility report for an adapter module."""
    report, problems, warnings = [], [], []
    try:
        tree = ast.parse(src.decode("utf-8"))
    except (SyntaxError, UnicodeDecodeError) as e:
        return {"status": "unsupported", "problems": [f"adapter.py is not valid Python: {e}"], "warnings": [], "functions": []}
    funcs = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for f in REQUIRED_FUNCTIONS:
        (report if f in funcs else problems).append(f"{'defines' if f in funcs else 'missing required function'} {f}()")
    for f in OPTIONAL_FUNCTIONS:
        if f not in funcs:
            warnings.append(f"optional {f}() not defined: official test vectors will be reported as unsupported")
    has_meta = any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ADAPTER" for t in n.targets) for n in tree.body)
    (report if has_meta else warnings).append("ADAPTER metadata " + ("present" if has_meta else "missing (name/version/algorithm/library will be unknown)"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for n in names:
                root = n.split(".")[0]
                if root in FORBIDDEN_MODULES:
                    problems.append(f"forbidden import: {n}")
                elif root not in ALLOWED_IMPORT_ROOTS:
                    problems.append(f"import outside the supported allowlist: {n} (supported roots: {', '.join(sorted(ALLOWED_IMPORT_ROOTS))})")
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in FORBIDDEN_CALLS:
                problems.append(f"forbidden call: {fn.id}()")
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id == "os" and fn.attr not in ALLOWED_OS_ATTRS:
                problems.append(f"forbidden call: os.{fn.attr}()")
    status = "compatible" if not problems else "unsupported"
    return {"status": status, "problems": problems, "warnings": warnings, "report": report, "functions": sorted(funcs),
            "note": "Static check only (AST). Execution happens solely inside the isolated runner."}


def check_snapshot(files: dict[str, bytes]) -> dict:
    secrets = {n: hits for n, hits in ((n, scan_secrets(b)) for n, b in files.items()) if hits}
    if secrets:
        raise ValueError("snapshot contains recognised private-key or credential material: " + ", ".join(secrets))
    if "adapter.py" not in files:
        return {"status": "unsupported", "problems": ["archive has no adapter.py at its root"], "warnings": [], "report": [],
                "files": sorted(files), "note": "Provide an adapter.py implementing the adapter interface, or import results instead."}
    rep = check_adapter_source(files["adapter.py"])
    rep["files"] = sorted(files)
    return rep
