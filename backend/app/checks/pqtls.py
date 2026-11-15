"""Real TLS with post-quantum key exchange, in this process, using the copy of OpenSSL inside the `cryptography`
library (phase 4a).

Python's own `ssl` module uses the computer's OpenSSL, which may be too old for post-quantum key exchange. The
`cryptography` library ships its own, newer OpenSSL and exposes its TLS functions through its low-level binding.
This module uses that binding to run:
  - a client that makes ONE full handshake offering exactly the key-exchange groups asked for, and records every
    handshake message and its size (for "how much bigger is the handshake" questions), and
  - small local test servers that complete the handshake and close (they serve no data).

Rule: if this part of the library ever stops working (a function missing in a later release, a build without
ML-KEM, anything), nothing crashes and nothing guesses. `available()` returns (False, plain reason) and every other
entry point raises `PqTlsUnavailable(plain reason)`, which callers show as "Couldn't check". Importing this module
never fails: the binding is loaded lazily.

Test keys only. A private key is never written to disk here: certificates and keys are loaded from memory.
"""
from __future__ import annotations

import datetime
import errno as errno_codes
import socket
import struct
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from app.config import BIND_HOST
# TLS SignatureScheme numbers and their names (pure data, so the reviewer can read them too)
from app.checks.tls_names import POST_QUANTUM_SCHEMES, SIGNATURE_SCHEMES, scheme_family  # noqa: F401

# ---------------------------------------------------------------------------------------------- names and numbers

HRR_RANDOM = bytes.fromhex("CF21AD74E59A6111BE1D8C021E65B891C2A211167ABB8C5E079E09E2C8A8339C")

# TLS group ids (IANA) -> our spelling
GROUP_IDS = {
    0x11EC: "X25519MLKEM768", 0x11EB: "SecP256r1MLKEM768", 0x11ED: "SecP384r1MLKEM1024",
    0x0200: "MLKEM512", 0x0201: "MLKEM768", 0x0202: "MLKEM1024",
    0x001D: "X25519", 0x001E: "X448", 0x0017: "P-256", 0x0018: "P-384", 0x0019: "P-521",
}
# OpenSSL's names (lower case) -> our spelling
_OPENSSL_GROUP_NAMES = {
    "x25519mlkem768": "X25519MLKEM768", "secp256r1mlkem768": "SecP256r1MLKEM768",
    "secp384r1mlkem1024": "SecP384r1MLKEM1024", "mlkem512": "MLKEM512", "mlkem768": "MLKEM768",
    "mlkem1024": "MLKEM1024", "x25519": "X25519", "x448": "X448",
    "secp256r1": "P-256", "prime256v1": "P-256", "p-256": "P-256",
    "secp384r1": "P-384", "p-384": "P-384", "secp521r1": "P-521", "p-521": "P-521",
}
# our spelling -> OpenSSL's, for group lists we are given
_TO_OPENSSL = {"P-256": "prime256v1", "P-384": "secp384r1", "P-521": "secp521r1"}

_MESSAGE_TYPES = {
    0: "HelloRequest", 1: "ClientHello", 2: "ServerHello", 4: "NewSessionTicket", 5: "EndOfEarlyData",
    8: "EncryptedExtensions", 11: "Certificate", 12: "ServerKeyExchange", 13: "CertificateRequest",
    14: "ServerHelloDone", 15: "CertificateVerify", 16: "ClientKeyExchange", 20: "Finished",
    24: "KeyUpdate", 25: "CompressedCertificate", 254: "MessageHash",
}
_ALERTS = {
    0: "close_notify", 10: "unexpected_message", 20: "bad_record_mac", 22: "record_overflow",
    40: "handshake_failure", 42: "bad_certificate", 43: "unsupported_certificate", 44: "certificate_revoked",
    45: "certificate_expired", 46: "certificate_unknown", 47: "illegal_parameter", 48: "unknown_ca",
    49: "access_denied", 50: "decode_error", 51: "decrypt_error", 70: "protocol_version",
    71: "insufficient_security", 80: "internal_error", 86: "inappropriate_fallback", 90: "user_canceled",
    109: "missing_extension", 110: "unsupported_extension", 112: "unrecognized_name",
    116: "certificate_required", 120: "no_application_protocol",
}
REFUSAL_ALERTS = (40, 70, 71)  # handshake_failure, protocol_version, insufficient_security

_VERSION_NAMES = {"TLSv1.3": "TLS 1.3", "TLSv1.2": "TLS 1.2", "TLSv1.1": "TLS 1.1", "TLSv1": "TLS 1.0"}

SERVER_TIMEOUT = 5.0  # seconds a test server waits for a client during one handshake
HYBRID_GROUPS = "X25519MLKEM768:X25519:prime256v1"
CLASSICAL_GROUPS = "X25519:prime256v1"
TEST_CERTIFICATE_ORG = "Evidence Lab test server (test certificate)"

# Every function and constant this module uses on the binding's `lib`. available() checks them all.
_REQUIRED = (
    "SSL_CTX_new", "SSL_CTX_free", "TLS_server_method", "TLS_client_method", "SSL_new", "SSL_free", "SSL_set_fd",
    "SSL_set_connect_state", "SSL_set_accept_state", "SSL_do_handshake", "SSL_shutdown", "SSL_get_error",
    "SSL_CTX_set1_curves_list", "SSL_get0_group_name", "SSL_get_version", "SSL_CTX_set_min_proto_version",
    "SSL_CTX_set_max_proto_version", "SSL_CTX_use_certificate", "SSL_CTX_use_PrivateKey",
    "SSL_CTX_check_private_key", "SSL_CTX_set_verify", "SSL_CTX_set_msg_callback", "SSL_set_tlsext_host_name",
    "PEM_read_bio_X509", "PEM_read_bio_PrivateKey", "BIO_new_mem_buf", "BIO_free", "X509_free", "EVP_PKEY_free",
    "ERR_get_error", "ERR_clear_error", "ERR_reason_error_string", "OpenSSL_version",
    "TLS1_2_VERSION", "TLS1_3_VERSION", "SSL_VERIFY_NONE", "SSL_ERROR_SYSCALL", "SSL_ERROR_ZERO_RETURN",
)


class PqTlsUnavailable(Exception):
    """Post-quantum TLS can't be run here. The message is one plain sentence saying why."""


# ---------------------------------------------------------------------------------------------- availability

_state_lock = threading.Lock()
_state: tuple[bool, str, object, object] | None = None  # (usable, text, ffi, lib), worked out once


def _load_binding():
    """The `cryptography` library's binding to its own OpenSSL: (ffi, lib)."""
    from cryptography.hazmat.bindings.openssl.binding import Binding
    binding = Binding()
    return binding.ffi, binding.lib


def _library_text(ffi, lib) -> str:
    try:
        import cryptography
        version = cryptography.__version__
    except Exception:
        version = "unknown version"
    return f"{ffi.string(lib.OpenSSL_version(0)).decode('ascii', 'replace')} (inside cryptography {version})"


def _work_out() -> tuple[bool, str, object, object]:
    try:
        ffi, lib = _load_binding()
    except Exception:
        return False, "The copy of OpenSSL inside the cryptography library could not be loaded.", None, None
    try:
        for name in _REQUIRED:
            if not hasattr(lib, name):
                return (False, f"The copy of OpenSSL inside the cryptography library does not offer {name}, "
                               "which these checks need.", None, None)
        ctx = lib.SSL_CTX_new(lib.TLS_client_method())
        if ctx == ffi.NULL:
            return False, "The copy of OpenSSL inside the cryptography library could not set up TLS.", None, None
        try:
            if lib.SSL_CTX_set1_curves_list(ctx, b"X25519MLKEM768:X25519") != 1:
                return (False, "The copy of OpenSSL inside the cryptography library does not offer the hybrid "
                               "post-quantum key exchange X25519MLKEM768.", None, None)
        finally:
            lib.SSL_CTX_free(ctx)
            lib.ERR_clear_error()
        if not _self_test(ffi, lib):
            return (False, "A trial post-quantum handshake inside this app did not complete, so ML-KEM can't be "
                           "used with this copy of the cryptography library.", None, None)
        return True, _library_text(ffi, lib), ffi, lib
    except Exception:
        return (False, "The copy of OpenSSL inside the cryptography library did not work as expected for "
                       "post-quantum TLS.", None, None)


def _self_test(ffi, lib) -> bool:
    """One real X25519MLKEM768 handshake between two ends of a local socket pair, inside this process."""
    cert_pem, key_pem, _ = test_certificate("ecdsa-p256", "evidence-lab-self-test")
    ctx = _server_context(ffi, lib, b"X25519MLKEM768:X25519", cert_pem, key_pem, lib.TLS1_3_VERSION, lib.TLS1_3_VERSION)
    a, b = socket.socketpair()
    try:
        for s in (a, b):
            _set_socket_timeouts(s, SERVER_TIMEOUT)
        server = threading.Thread(target=_serve_one, args=(ffi, lib, lambda: lib.SSL_new(ctx), a), daemon=True)
        server.start()
        result = _client_handshake(ffi, lib, b, None, b"X25519MLKEM768", lib.TLS1_3_VERSION, lib.TLS1_3_VERSION)
        b.close()
        server.join(SERVER_TIMEOUT + 1)
        return result["outcome"] == "completed" and result["group"] == "X25519MLKEM768"
    finally:
        for s in (a, b):
            try:
                s.close()
            except OSError:
                pass
        lib.SSL_CTX_free(ctx)


def available() -> tuple[bool, str]:
    """(usable?, text). Usable: the library text, e.g. "OpenSSL 4.0.3 ... (inside cryptography 50.0.2)". Not
    usable: one plain sentence saying why. Worked out once (cached). Never raises."""
    global _state
    try:
        with _state_lock:
            if _state is None:
                _state = _work_out()
            usable, text = _state[0], _state[1]
        return usable, text
    except Exception:
        return False, "The copy of OpenSSL inside the cryptography library did not work as expected for post-quantum TLS."


def _reset() -> None:
    """Forget the cached answer (for tests)."""
    global _state
    with _state_lock:
        _state = None


def _require():
    usable, text = available()
    state = _state
    if not usable or state is None or state[2] is None:
        raise PqTlsUnavailable(text)
    return state[2], state[3]


# ---------------------------------------------------------------------------------------------- helpers

def _version_number(lib, name: str) -> int:
    if name == "TLS 1.3":
        return lib.TLS1_3_VERSION
    if name == "TLS 1.2":
        return lib.TLS1_2_VERSION
    raise ValueError(f"TLS version must be 'TLS 1.2' or 'TLS 1.3', not {name!r}")


def _group_list(groups: str) -> bytes:
    parts = [p.strip() for p in groups.split(":") if p.strip()]
    if not parts:
        raise ValueError("the group list is empty")
    return ":".join(_TO_OPENSSL.get(p, p) for p in parts).encode("ascii")


def group_name(openssl_name: str | None) -> str | None:
    """OpenSSL's name for a group in our spelling ("secp256r1" -> "P-256"); unknown names pass through."""
    if not openssl_name:
        return None
    return _OPENSSL_GROUP_NAMES.get(openssl_name.lower(), openssl_name)


def _set_socket_timeouts(sock: socket.socket, seconds: float) -> None:
    """Time limits for a BLOCKING socket handed to OpenSSL. (A Python socket timeout would make the descriptor
    non-blocking, which OpenSSL's blocking handshake can't use.)"""
    sec = int(seconds)
    usec = int((seconds - sec) * 1_000_000)
    value = struct.pack("ll", sec, usec)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO, value)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDTIMEO, value)


def _last_error_reason(ffi, lib) -> str | None:
    code = lib.ERR_get_error()
    lib.ERR_clear_error()
    if not code:
        return None
    text = lib.ERR_reason_error_string(code)
    return ffi.string(text).decode("ascii", "replace") if text != ffi.NULL else None


def _server_context(ffi, lib, groups: bytes | None, certificate_pem: bytes, key_pem: bytes, low: int, high: int):
    """An SSL_CTX for a test server, certificate and key loaded from memory. Raises PqTlsUnavailable."""
    lib.ERR_clear_error()
    ctx = lib.SSL_CTX_new(lib.TLS_server_method())
    if ctx == ffi.NULL:
        raise PqTlsUnavailable("The copy of OpenSSL inside the cryptography library could not set up a TLS server.")
    try:
        if lib.SSL_CTX_set_min_proto_version(ctx, low) != 1 or lib.SSL_CTX_set_max_proto_version(ctx, high) != 1:
            raise PqTlsUnavailable("The copy of OpenSSL inside the cryptography library does not accept these TLS versions.")
        if groups is not None and lib.SSL_CTX_set1_curves_list(ctx, groups) != 1:
            raise PqTlsUnavailable(f"The copy of OpenSSL inside the cryptography library does not offer the "
                                   f"key-exchange groups {groups.decode('ascii', 'replace')}.")
        _use_certificate_and_key(ffi, lib, ctx, certificate_pem, key_pem)
        return ctx
    except BaseException:
        lib.SSL_CTX_free(ctx)
        lib.ERR_clear_error()
        raise


def _use_certificate_and_key(ffi, lib, ctx, certificate_pem: bytes, key_pem: bytes) -> None:
    cert = _read_pem(ffi, lib, certificate_pem, lib.PEM_read_bio_X509)
    if cert == ffi.NULL:
        raise PqTlsUnavailable("The copy of OpenSSL inside the cryptography library could not read the test certificate.")
    try:
        if lib.SSL_CTX_use_certificate(ctx, cert) != 1:  # takes its own reference
            raise PqTlsUnavailable("The copy of OpenSSL inside the cryptography library could not use the test certificate.")
    finally:
        lib.X509_free(cert)
    key = _read_pem(ffi, lib, key_pem, lib.PEM_read_bio_PrivateKey)
    if key == ffi.NULL:
        raise PqTlsUnavailable("The copy of OpenSSL inside the cryptography library could not read the test key.")
    try:
        if lib.SSL_CTX_use_PrivateKey(ctx, key) != 1 or lib.SSL_CTX_check_private_key(ctx) != 1:
            raise PqTlsUnavailable("The copy of OpenSSL inside the cryptography library could not use the test key.")
    finally:
        lib.EVP_PKEY_free(key)


def _read_pem(ffi, lib, pem: bytes, reader):
    buffer = ffi.new("char[]", pem)  # kept alive until the BIO is freed below
    bio = lib.BIO_new_mem_buf(buffer, len(pem))
    if bio == ffi.NULL:
        return ffi.NULL
    try:
        return reader(bio, ffi.NULL, ffi.NULL, ffi.NULL)
    finally:
        lib.BIO_free(bio)


def _serve_one(ffi, lib, new_ssl, conn: socket.socket) -> None:
    """Complete one handshake as the server on this (blocking) socket, then close cleanly. `new_ssl()` makes the
    SSL object (NULL = don't serve). Never raises."""
    ssl_ = ffi.NULL
    try:
        lib.ERR_clear_error()
        ssl_ = new_ssl()  # an SSL object holds its own reference on its SSL_CTX
        if ssl_ == ffi.NULL:
            return
        lib.SSL_set_fd(ssl_, conn.fileno())
        lib.SSL_set_accept_state(ssl_)
        if lib.SSL_do_handshake(ssl_) == 1:
            lib.SSL_shutdown(ssl_)
    except Exception:
        pass
    finally:
        if ssl_ != ffi.NULL:
            lib.SSL_free(ssl_)
        lib.ERR_clear_error()


# ---------------------------------------------------------------------------------------------- the client

@dataclass
class Handshake:
    outcome: str                 # "completed" | "refused" (server alert 40, 70 or 71) | "unknown"
    tls_version: str | None = None
    group: str | None = None
    alert: int | None = None
    detail: str = ""
    duration_ms: float = 0.0
    messages: list[dict] = field(default_factory=list)
    client_hello_bytes: int | None = None
    client_share_bytes: int | None = None
    server_share_bytes: int | None = None
    certificate_der: bytes | None = None
    certificate_message_bytes: int | None = None
    signature_bytes: int | None = None
    signature_scheme: int | None = None   # phase 4b: the server's handshake signature algorithm (TLS SignatureScheme number)


def _u16(data: bytes, at: int) -> int:
    return struct.unpack_from("!H", data, at)[0]


def _u24(data: bytes, at: int) -> int:
    return int.from_bytes(data[at:at + 3], "big")


def _extensions(data: bytes, at: int) -> dict[int, bytes]:
    """Extensions block starting at `at` (2-byte total length, then type/length/data entries)."""
    out: dict[int, bytes] = {}
    end = at + 2 + _u16(data, at)
    p = at + 2
    while p + 4 <= end:
        kind, length = _u16(data, p), _u16(data, p + 2)
        out[kind] = data[p + 4:p + 4 + length]
        p += 4 + length
    return out


def _client_hello_shares(msg: bytes) -> dict[int, int]:
    """group id -> key share size, from a ClientHello's key_share extension."""
    p = 4 + 2 + 32
    p += 1 + msg[p]               # session id
    p += 2 + _u16(msg, p)         # cipher suites
    p += 1 + msg[p]               # compression methods
    if p + 2 > len(msg):
        return {}
    share = _extensions(msg, p).get(51)
    shares: dict[int, int] = {}
    if share and len(share) >= 2:
        q, end = 2, 2 + _u16(share, 0)
        while q + 4 <= end:
            gid, length = _u16(share, q), _u16(share, q + 2)
            shares[gid] = length
            q += 4 + length
    return shares


def _server_hello(msg: bytes) -> dict:
    """random-is-HRR?, TLS 1.3?, group id and key share size from a ServerHello."""
    p = 4
    random = msg[p + 2:p + 34]
    p += 2 + 32
    p += 1 + msg[p]  # session id
    p += 2 + 1       # cipher suite, compression
    info = {"hrr": random == HRR_RANDOM, "tls13": False, "group": None, "share": None}
    if p + 2 > len(msg):
        return info
    exts = _extensions(msg, p)
    info["tls13"] = exts.get(43) == b"\x03\x04"
    share = exts.get(51)
    if share and len(share) >= 2:
        info["group"] = _u16(share, 0)
        if len(share) >= 4:  # a HelloRetryRequest names the group only
            info["share"] = _u16(share, 2)
    return info


def _first_certificate(msg: bytes, tls13: bool) -> bytes | None:
    p = 4
    if tls13:
        p += 1 + msg[p]  # certificate_request_context
    p += 3               # certificate_list length
    if p + 3 > len(msg):
        return None
    length = _u24(msg, p)
    der = msg[p + 3:p + 3 + length]
    return der if der and len(der) == length else None


def _summarise(raw: list[tuple[str, int, bytes]], result: Handshake) -> int | None:
    """Fill the message list and sizes from the handshake messages seen. Returns the negotiated group id."""
    tls13, group_id, client_shares, tls12_client_share = False, None, {}, None
    for direction, kind, msg in raw:
        name = _MESSAGE_TYPES.get(kind, f"type {kind}")
        try:
            if kind == 1 and direction == "sent":
                if result.client_hello_bytes is None:
                    result.client_hello_bytes = len(msg)
                client_shares = _client_hello_shares(msg)
            elif kind == 2 and direction == "received":
                info = _server_hello(msg)
                if info["hrr"]:
                    name = "HelloRetryRequest"
                else:
                    tls13 = info["tls13"]
                    if info["group"] is not None:
                        group_id, result.server_share_bytes = info["group"], info["share"]
            elif kind == 11 and direction == "received" and result.certificate_der is None:
                result.certificate_message_bytes = len(msg)
                result.certificate_der = _first_certificate(msg, tls13)
            elif kind == 15 and direction == "received" and result.signature_bytes is None:
                result.signature_bytes = len(msg) - 8
                result.signature_scheme = _u16(msg, 4)                     # CertificateVerify: the scheme comes first
            elif kind == 12 and direction == "received" and msg[4] == 3:  # TLS 1.2 ECDHE: named curve
                group_id, result.server_share_bytes = _u16(msg, 5), msg[7]
                at = 8 + msg[7]                                            # after the point: scheme, length, signature
                if result.signature_scheme is None and len(msg) >= at + 4:
                    result.signature_scheme = _u16(msg, at)
                    if result.signature_bytes is None:
                        result.signature_bytes = _u16(msg, at + 2)
            elif kind == 16 and direction == "sent" and len(msg) > 4:      # TLS 1.2 ECDHE client point
                tls12_client_share = msg[4]
        except (IndexError, struct.error):
            pass
        result.messages.append({"direction": direction, "type": name, "bytes": len(msg)})
    if group_id is not None:
        result.client_share_bytes = client_shares.get(group_id, tls12_client_share)
    return group_id


def _client_handshake(ffi, lib, sock: socket.socket, server_name: str | None, groups: bytes, low: int, high: int) -> dict:
    """One handshake as the client on this connected, blocking socket. Returns a dict of Handshake fields."""
    raw: list[tuple[str, int, bytes]] = []
    alerts: list[int] = []

    @ffi.callback("void(int, int, int, const void *, size_t, SSL *, void *)")
    def on_message(write_p, version, content_type, buf, length, ssl_, arg):
        try:
            if content_type == 22 and length >= 4:
                data = bytes(ffi.buffer(buf, length))
                raw.append(("sent" if write_p else "received", data[0], data))
            elif content_type == 21 and length >= 2 and not write_p:
                alerts.append(bytes(ffi.buffer(buf, length))[1])
        except Exception:
            pass

    lib.ERR_clear_error()
    ctx = lib.SSL_CTX_new(lib.TLS_client_method())
    if ctx == ffi.NULL:
        raise PqTlsUnavailable("The copy of OpenSSL inside the cryptography library could not set up a TLS client.")
    ssl_ = ffi.NULL
    try:
        if lib.SSL_CTX_set_min_proto_version(ctx, low) != 1 or lib.SSL_CTX_set_max_proto_version(ctx, high) != 1:
            raise PqTlsUnavailable("The copy of OpenSSL inside the cryptography library does not accept these TLS versions.")
        if lib.SSL_CTX_set1_curves_list(ctx, groups) != 1:
            raise PqTlsUnavailable(f"The copy of OpenSSL inside the cryptography library does not offer the "
                                   f"key-exchange groups {groups.decode('ascii', 'replace')}.")
        lib.SSL_CTX_set_verify(ctx, lib.SSL_VERIFY_NONE, ffi.NULL)  # trust is not the question here
        lib.SSL_CTX_set_msg_callback(ctx, on_message)  # `on_message` stays referenced until ctx is freed below
        ssl_ = lib.SSL_new(ctx)
        if ssl_ == ffi.NULL:
            raise PqTlsUnavailable("The copy of OpenSSL inside the cryptography library could not set up a TLS client.")
        if server_name:
            try:
                name = server_name.encode("idna")
            except UnicodeError:
                name = None
            if name:
                lib.SSL_set_tlsext_host_name(ssl_, name)
        lib.SSL_set_fd(ssl_, sock.fileno())
        lib.SSL_set_connect_state(ssl_)
        rc = lib.SSL_do_handshake(ssl_)
        saved_errno = ffi.errno
        out: dict = {"raw": raw}
        if rc == 1:
            version = ffi.string(lib.SSL_get_version(ssl_)).decode("ascii", "replace")
            g = lib.SSL_get0_group_name(ssl_)
            out.update(outcome="completed", tls_version=_VERSION_NAMES.get(version, version),
                       group=group_name(ffi.string(g).decode("ascii", "replace")) if g != ffi.NULL else None)
            lib.SSL_shutdown(ssl_)
            lib.ERR_clear_error()
            return out
        error = lib.SSL_get_error(ssl_, rc)
        reason = _last_error_reason(ffi, lib)
        if alerts:
            alert = alerts[0]
            out.update(outcome="refused" if alert in REFUSAL_ALERTS else "unknown", alert=alert,
                       detail=f"server alert {alert} ({_ALERTS.get(alert, 'unknown alert')})")
        elif saved_errno in (errno_codes.EAGAIN, errno_codes.EWOULDBLOCK, errno_codes.ETIMEDOUT):
            out.update(outcome="unknown", detail="no answer before the time limit")
        elif saved_errno in (errno_codes.ECONNRESET, errno_codes.EPIPE):
            out.update(outcome="unknown", detail="the server reset the connection during the handshake")
        elif error in (lib.SSL_ERROR_SYSCALL, lib.SSL_ERROR_ZERO_RETURN) and not reason:
            out.update(outcome="unknown", detail="the server closed the connection before the handshake finished")
        else:
            out.update(outcome="unknown", detail=f"the handshake did not complete ({reason or 'no reason given'})")
        return out
    finally:
        if ssl_ != ffi.NULL:
            lib.SSL_free(ssl_)
        lib.SSL_CTX_free(ctx)
        lib.ERR_clear_error()


def handshake(ip: str, port: int, server_name: str | None, groups: str, *, timeout: float = 5.0,
              min_version: str = "TLS 1.3", max_version: str = "TLS 1.3") -> Handshake:
    """ONE full handshake as a client offering exactly this group list (e.g. "X25519MLKEM768" or
    "X25519:P-256:P-384"), no certificate verification, SNI = server_name when given, then a clean close.
    Handshake only: no application data. Raises PqTlsUnavailable only; every network or TLS failure comes back as
    outcome "refused" or "unknown"."""
    ffi, lib = _require()
    try:
        low, high = _version_number(lib, min_version), _version_number(lib, max_version)
        offered = _group_list(groups)
    except (ValueError, UnicodeError) as exc:
        raise PqTlsUnavailable(f"These handshake settings can't be used ({exc}).") from None
    started = time.perf_counter()
    try:
        sock = socket.create_connection((ip, port), timeout=timeout)
    except OSError as exc:
        elapsed = (time.perf_counter() - started) * 1000
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return Handshake("unknown", detail="no answer before the time limit", duration_ms=elapsed)
        return Handshake("unknown", detail=f"could not connect ({exc.strerror or exc.__class__.__name__})", duration_ms=elapsed)
    try:
        try:
            sock.settimeout(None)  # blocking again, for OpenSSL; the time limit is set on the socket itself
            _set_socket_timeouts(sock, timeout)
            out = _client_handshake(ffi, lib, sock, server_name, offered, low, high)
        except PqTlsUnavailable:
            raise
        except Exception as exc:
            return Handshake("unknown", detail=f"the handshake did not complete ({exc.__class__.__name__})",
                             duration_ms=(time.perf_counter() - started) * 1000)
    finally:
        try:
            sock.close()
        except OSError:
            pass
    elapsed = (time.perf_counter() - started) * 1000
    result = Handshake(out["outcome"], tls_version=out.get("tls_version"), group=out.get("group"),
                       alert=out.get("alert"), detail=out.get("detail", ""), duration_ms=elapsed)
    group_id = _summarise(out["raw"], result)
    if result.outcome == "completed":
        if result.group is None and group_id is not None:
            result.group = GROUP_IDS.get(group_id, f"group 0x{group_id:04x}")
        result.detail = f"handshake completed ({result.tls_version}, {result.group or 'no key-exchange group'})"
    else:
        result.tls_version = result.group = None
    return result


# ---------------------------------------------------------------------------------------------- the test servers

class Server:
    """A real TLS listener on 127.0.0.1: completes the handshake, then closes. It serves no data."""

    def __init__(self, *, groups: str | None, certificate_pem: bytes, key_pem: bytes, min_version: str = "TLS 1.2",
                 max_version: str = "TLS 1.3", port: int = 0):
        """groups None = the library's default list. Raises PqTlsUnavailable, or OSError when the port is taken."""
        ffi, lib = _require()
        try:
            low, high = _version_number(lib, min_version), _version_number(lib, max_version)
            wanted = _group_list(groups) if groups is not None else None
        except (ValueError, UnicodeError) as exc:
            raise PqTlsUnavailable(f"These server settings can't be used ({exc}).") from None
        self._ffi, self._lib = ffi, lib
        self._ctx = _server_context(ffi, lib, wanted, certificate_pem, key_pem, low, high)
        self._closed = False
        self._lock = threading.Lock()
        try:
            self._sock = socket.create_server((BIND_HOST, port))
            self._sock.listen(64)
        except BaseException:
            lib.SSL_CTX_free(self._ctx)
            self._closed = True
            raise
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._loop, name=f"pq-tls-server-{self.port}", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        try:
            conn.setblocking(True)
            _set_socket_timeouts(conn, SERVER_TIMEOUT)
            _serve_one(self._ffi, self._lib, self._new_ssl, conn)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _new_ssl(self):
        with self._lock:  # never after close() has freed the context
            return self._ffi.NULL if self._closed else self._lib.SSL_new(self._ctx)

    def close(self) -> None:
        for step in (lambda: self._sock.shutdown(socket.SHUT_RDWR), self._sock.close):
            try:
                step()  # shutdown first, so the waiting accept() wakes up and the port is really released
            except OSError:
                pass
        self._thread.join(timeout=2)
        with self._lock:
            if not self._closed:
                self._closed = True
                self._lib.SSL_CTX_free(self._ctx)  # connections still being served hold their own reference

    def __del__(self):
        try:
            if not getattr(self, "_closed", True):
                self.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------------------------- test certificates

def test_certificate(kind: str, common_name: str) -> tuple[bytes, bytes, bytes]:
    """A throwaway self-signed TEST certificate, valid a few days: (certificate PEM, key PEM, certificate DER).
    kind: "ecdsa-p256" | "rsa-2048" | "mldsa-65". Made with the `cryptography` public API (works even when
    post-quantum TLS is not available). Raises PqTlsUnavailable if "mldsa-65" can't be made here."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
    from cryptography.x509.oid import NameOID

    digest = hashes.SHA256()
    if kind == "ecdsa-p256":
        key = ec.generate_private_key(ec.SECP256R1())
    elif kind == "rsa-2048":
        key = rsa.generate_private_key(65537, 2048)
    elif kind == "mldsa-65":
        try:
            from cryptography.hazmat.primitives.asymmetric import mldsa
            key = mldsa.MLDSA65PrivateKey.generate()
        except Exception:
            raise PqTlsUnavailable("This copy of the cryptography library can't make ML-DSA-65 keys.") from None
        digest = None
    else:
        raise ValueError(f"unknown test certificate kind {kind!r}")
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, TEST_CERTIFICATE_ORG)])
    now = datetime.datetime.now(datetime.timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
               .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
               .not_valid_after(now + datetime.timedelta(days=3)))
    try:
        cert = builder.sign(key, digest)
    except Exception:
        if kind == "mldsa-65":
            raise PqTlsUnavailable("This copy of the cryptography library can't sign ML-DSA-65 certificates.") from None
        raise
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return cert.public_bytes(serialization.Encoding.PEM), key_pem, cert.public_bytes(serialization.Encoding.DER)


@contextmanager
def control_servers():
    """Two control servers for one status measurement, closed on exit. Yields {"hybrid": port, "classical": port}.
    hybrid offers X25519MLKEM768 (then X25519 and P-256); classical offers X25519 and P-256 only. Both accept
    TLS 1.2 to 1.3 with ECDSA P-256 test certificates. Raises PqTlsUnavailable."""
    _require()
    servers: dict[str, Server] = {}
    try:
        for role, groups in (("hybrid", HYBRID_GROUPS), ("classical", CLASSICAL_GROUPS)):
            cert_pem, key_pem, _ = test_certificate("ecdsa-p256", f"control-{role}")
            servers[role] = Server(groups=groups, certificate_pem=cert_pem, key_pem=key_pem)
        yield {role: server.port for role, server in servers.items()}
    finally:
        for server in servers.values():
            server.close()
