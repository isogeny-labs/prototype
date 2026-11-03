"""Signature scheme adapters used by fixtures. Every scheme is an established, published algorithm.

Implementations:
* RSA / ECDSA / Ed25519 via `cryptography` (OpenSSL-backed, production-grade library).
* ML-DSA (FIPS 204) via `dilithium-py`, a pure-Python REFERENCE implementation. Its timings are
  not representative of optimised C implementations and it is not hardened against side channels.
"""
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec, ed25519, padding, utils

SCHEMES = {}


def register(name):
    def deco(cls):
        SCHEMES[name] = cls
        cls.name = name
        return cls
    return deco


class Scheme:
    purpose = "signature"
    library = ""
    production_grade = True
    notes = ""

    def keygen(self):
        raise NotImplementedError

    def sign(self, sk, msg):
        raise NotImplementedError

    def verify(self, pk, msg, sig):
        """Return True/False. Must never raise for malformed input."""
        raise NotImplementedError

    def pk_bytes(self, pk):
        raise NotImplementedError

    def pk_from_bytes(self, b):
        raise NotImplementedError("no raw public-key format for this scheme")

    def sk_from_bytes(self, b):
        raise NotImplementedError("no raw private-key format for this scheme")


class _RSA(Scheme):
    bits = 2048
    library = "cryptography/OpenSSL"
    pss = False

    def keygen(self):
        sk = rsa.generate_private_key(public_exponent=65537, key_size=self.bits)
        return sk.public_key(), sk

    def _pad(self):
        if self.pss:
            return padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)
        return padding.PKCS1v15()

    def sign(self, sk, msg):
        return sk.sign(msg, self._pad(), hashes.SHA256())

    def verify(self, pk, msg, sig):
        try:
            pk.verify(sig, msg, self._pad(), hashes.SHA256())
            return True
        except Exception:
            return False

    def pk_bytes(self, pk):
        return pk.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


@register("rsa2048_pkcs1v15_sha256")
class RSA2048(_RSA):
    bits = 2048


@register("rsa3072_pkcs1v15_sha256")
class RSA3072(_RSA):
    bits = 3072


@register("rsa3072_pss_sha256")
class RSA3072PSS(_RSA):
    bits = 3072
    pss = True


@register("ecdsa_p256_sha256")
class ECDSAP256(Scheme):
    library = "cryptography/OpenSSL"

    def keygen(self):
        sk = ec.generate_private_key(ec.SECP256R1())
        return sk.public_key(), sk

    def sign(self, sk, msg):
        der = sk.sign(msg, ec.ECDSA(hashes.SHA256()))
        r, s = utils.decode_dss_signature(der)
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")  # fixed-size raw r||s

    def verify(self, pk, msg, sig):
        try:
            if len(sig) != 64:
                return False
            der = utils.encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"))
            pk.verify(der, msg, ec.ECDSA(hashes.SHA256()))
            return True
        except Exception:
            return False

    def pk_bytes(self, pk):
        return pk.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


@register("ed25519")
class Ed25519(Scheme):
    library = "cryptography/OpenSSL"

    def keygen(self):
        sk = ed25519.Ed25519PrivateKey.generate()
        return sk.public_key(), sk

    def sign(self, sk, msg):
        return sk.sign(msg)

    def verify(self, pk, msg, sig):
        try:
            pk.verify(sig, msg)
            return True
        except Exception:
            return False

    def pk_bytes(self, pk):
        return pk.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    def pk_from_bytes(self, b):
        return ed25519.Ed25519PublicKey.from_public_bytes(b)

    def sk_from_bytes(self, b):
        return ed25519.Ed25519PrivateKey.from_private_bytes(b)


class _MLDSA(Scheme):
    library = "dilithium-py (pure-Python reference)"
    production_grade = False
    notes = "Reference implementation; timing not representative of optimised implementations; not side-channel hardened."
    level = "ML_DSA_65"

    def _impl(self):
        from dilithium_py import ml_dsa
        return getattr(ml_dsa, self.level)

    def keygen(self):
        pk, sk = self._impl().keygen()
        return pk, sk

    def sign(self, sk, msg):
        return self._impl().sign(sk, msg)

    def verify(self, pk, msg, sig):
        try:
            return bool(self._impl().verify(pk, msg, sig))
        except Exception:
            return False

    def pk_bytes(self, pk):
        return pk

    def pk_from_bytes(self, b):
        return bytes(b)


@register("ml_dsa_44")
class MLDSA44(_MLDSA):
    level = "ML_DSA_44"


@register("ml_dsa_65")
class MLDSA65(_MLDSA):
    level = "ML_DSA_65"


@register("ml_dsa_87")
class MLDSA87(_MLDSA):
    level = "ML_DSA_87"


def get_scheme(name):
    if name not in SCHEMES:
        raise KeyError(f"unknown signature scheme profile: {name}")
    return SCHEMES[name]()
