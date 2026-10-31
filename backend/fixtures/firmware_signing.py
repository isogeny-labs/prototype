#!/usr/bin/env python3
"""Firmware-signing / update-verification fixture.

Builds a synthetic firmware update package (manifest + signature + image), verifies it with a
reference bootloader-style verifier, and exercises acceptance and rejection scenarios.

Params (JSON on stdin):
  scheme            profile id from sigschemes (e.g. rsa2048_pkcs1v15_sha256, ml_dsa_65)
  image_bytes       size of synthetic firmware image (default 262144)
  repeat_count      verify repeats for timing (default 50)
  installed_version version already on device for anti-rollback test (default 4)
  update_version    version carried by the new package (default 5)
  seed              deterministic RNG seed for image contents (default 1)

All measurements are host-side interpreter measurements; see metric_definitions.
"""
import hashlib
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import environment, summarize_ms, timed, peak_alloc_kb, read_params, emit, MEMORY_DEFINITION, TIME_DEFINITION  # noqa: E402
from sigschemes import get_scheme  # noqa: E402

FIXTURE_VERSION = "1.0.0"
MAGIC = b"IELFW1"


def build_manifest(scheme_name, image, version):
    return json.dumps({
        "format": "iel-fw-manifest/1",
        "scheme": scheme_name,
        "version": version,
        "image_len": len(image),
        "image_sha256": hashlib.sha256(image).hexdigest(),
    }, sort_keys=True, separators=(",", ":")).encode()


def package(manifest, sig, image):
    # MAGIC | u16 manifest_len | u16 sig_len | manifest | sig | image
    return MAGIC + len(manifest).to_bytes(2, "big") + len(sig).to_bytes(2, "big") + manifest + sig + image


class Verifier:
    """Reference bootloader verification policy: parse, check signature over manifest, check hash, anti-rollback."""

    def __init__(self, scheme, pk, installed_version):
        self.scheme, self.pk, self.installed_version = scheme, pk, installed_version

    def accept(self, pkg) -> bool:
        try:
            if pkg[:6] != MAGIC:
                return False
            mlen = int.from_bytes(pkg[6:8], "big")
            slen = int.from_bytes(pkg[8:10], "big")
            manifest = pkg[10:10 + mlen]
            sig = pkg[10 + mlen:10 + mlen + slen]
            image = pkg[10 + mlen + slen:]
            if len(manifest) != mlen or len(sig) != slen or slen == 0:
                return False
            if not self.scheme.verify(self.pk, manifest, sig):
                return False
            m = json.loads(manifest.decode())
            if m.get("format") != "iel-fw-manifest/1" or m.get("scheme") != self.scheme.name:
                return False
            if not isinstance(m.get("version"), int) or m["version"] <= self.installed_version:
                return False  # anti-rollback
            if m.get("image_len") != len(image):
                return False
            if hashlib.sha256(image).hexdigest() != m.get("image_sha256"):
                return False
            return True
        except Exception:
            return False


def main():
    p = read_params()
    scheme_name = p.get("scheme", "rsa2048_pkcs1v15_sha256")
    image_bytes = int(p.get("image_bytes", 262144))
    repeats = int(p.get("repeat_count", 50))
    installed = int(p.get("installed_version", 4))
    upd = int(p.get("update_version", 5))
    rng = random.Random(int(p.get("seed", 1)))
    failures, limitations = [], []

    try:
        scheme = get_scheme(scheme_name)
    except Exception as e:
        emit({"fixture": "firmware_signing", "fixture_version": FIXTURE_VERSION, "status": "failed",
              "failures": [f"scheme unavailable: {e}"], "environment": environment()})
        return 2

    image = bytes(rng.getrandbits(8) for _ in range(image_bytes))
    pk, sk = scheme.keygen()
    pk2, _ = scheme.keygen()
    manifest = build_manifest(scheme_name, image, upd)
    sig = scheme.sign(sk, manifest)
    good = package(manifest, sig, image)
    verifier = Verifier(scheme, pk, installed)

    # --- scenarios -------------------------------------------------------
    scen = []

    def case(cid, name, expected, pkg, detail=""):
        observed = "accept" if verifier.accept(pkg) else "reject"
        scen.append({"id": cid, "name": name, "expected": expected, "observed": observed,
                     "pass": observed == expected, "detail": detail})

    case("valid_update", "Valid signed update is accepted", "accept", good)
    tampered = bytearray(good)
    tampered[-1] ^= 0x01
    case("tampered_image", "Image with one flipped byte is rejected", "reject", bytes(tampered))
    case("wrong_key", "Package signed under a different key is rejected", "reject",
         package(manifest, scheme.sign(_sk2 := scheme.keygen()[1], manifest), image))
    case("truncated_signature", "Truncated signature is rejected", "reject", package(manifest, sig[:-1], image))
    case("empty_signature", "Empty signature is rejected", "reject", package(manifest, b"", image))
    case("corrupted_signature", "Signature with flipped bit is rejected", "reject",
         package(manifest, bytes([sig[0] ^ 0x80]) + sig[1:], image))
    old_manifest = build_manifest(scheme_name, image, installed)
    case("rollback", "Validly signed package with older version is rejected (anti-rollback)", "reject",
         package(old_manifest, scheme.sign(sk, old_manifest), image))
    case("manifest_swap", "Signature from another manifest is rejected", "reject",
         package(build_manifest(scheme_name, image, upd + 1), sig, image))
    case("malformed_manifest", "Malformed manifest bytes are rejected", "reject",
         package(b"{not json", scheme.sign(sk, b"{not json"), image))
    case("bad_magic", "Package with wrong header is rejected", "reject", b"XXXXXX" + good[6:])
    case("length_mismatch", "Manifest length field inconsistent with payload is rejected", "reject",
         good[:6] + (len(manifest) + 7).to_bytes(2, "big") + good[8:])
    del _sk2

    # --- timing ----------------------------------------------------------
    verifier.accept(good)  # warm-up
    verify_ms = timed(lambda: verifier.accept(good), repeats)
    sign_ms = timed(lambda: scheme.sign(sk, manifest), max(3, repeats // 5))
    peak_kb = peak_alloc_kb(lambda: verifier.accept(good))
    vstats, sstats = summarize_ms(verify_ms), summarize_ms(sign_ms)

    pkb = scheme.pk_bytes(pk)
    metrics = {
        "verify_time_ms_median": vstats["median"],
        "verify_time_ms_p95": vstats["p95"],
        "verify_time_ms_max": vstats["max"],
        "sign_time_ms_median": sstats["median"],
        "signature_bytes": len(sig),
        "public_key_bytes": len(pkb),
        "manifest_bytes": len(manifest),
        "update_overhead_bytes": len(good) - len(image),
        "update_package_bytes": len(good),
        "verify_peak_alloc_kb": round(peak_kb, 2),
        "verify_throughput_per_s": 1000.0 / vstats["mean"] if vstats["mean"] > 0 else None,
        "scenario_pass_count": sum(1 for s in scen if s["pass"]),
        "scenario_total": len(scen),
        "rejection_scenarios_all_pass": 1 if all(s["pass"] for s in scen if s["expected"] == "reject") else 0,
        "functional_pass": 1 if all(s["pass"] for s in scen) else 0,
    }
    if not scheme.production_grade:
        limitations.append(f"{scheme_name}: {scheme.notes}")
    limitations += [
        "Host-side Python measurements; device timing/memory must be imported from hardware runs.",
        "Synthetic firmware image and keys generated inside the fixture; no customer keys used.",
        "Passing all scenarios shows the reference verifier rejects these malformed inputs; it is not proof of security.",
    ]
    emit({
        "fixture": "firmware_signing",
        "fixture_version": FIXTURE_VERSION,
        "status": "completed",
        "scheme": scheme_name,
        "library": scheme.library,
        "environment": environment(),
        "repeat_count": repeats,
        "parameters": {"image_bytes": image_bytes, "installed_version": installed, "update_version": upd,
                       "seed": p.get("seed", 1)},
        "scenarios": scen,
        "metrics": metrics,
        "metric_definitions": {
            "verify_time_ms_*": TIME_DEFINITION + " Measures the full package verification (parse + signature + hash + policy).",
            "sign_time_ms_median": TIME_DEFINITION + " Signing of the manifest only.",
            "verify_peak_alloc_kb": MEMORY_DEFINITION,
            "signature_bytes": "Length of the raw signature stored in the package.",
            "public_key_bytes": "Encoded public key length (DER SPKI for RSA, X9.62 uncompressed for ECDSA, raw otherwise).",
            "update_overhead_bytes": "Package size minus image size (header + manifest + signature).",
            "verify_throughput_per_s": "1000 / mean verify ms.",
        },
        "raw": {"verify_times_ms": verify_ms, "sign_times_ms": sign_ms, "verify_stats": vstats, "sign_stats": sstats,
                "image_sha256": hashlib.sha256(image).hexdigest(), "package_sha256": hashlib.sha256(good).hexdigest()},
        "failures": failures,
        "limitations": limitations,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
