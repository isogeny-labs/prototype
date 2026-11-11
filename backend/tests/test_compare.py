import pytest

from app.compare import COULDNT, FALSE, TRUE, certificate_matches, compare_only_claim
from app.names import normalize_algorithm, normalize_tls_version, same_algorithm

A, R, U = "accepted", "refused", "unknown"


def obs(v10, v11, v12, v13):
    return {"TLS 1.0": v10, "TLS 1.1": v11, "TLS 1.2": v12, "TLS 1.3": v13}


def test_true_only_when_claimed_accepted_and_everything_else_refused():
    assert compare_only_claim(["TLS 1.3"], obs(R, R, R, A)).result == TRUE
    assert compare_only_claim(["TLS 1.2", "TLS 1.3"], obs(R, R, A, A)).result == TRUE


def test_false_as_soon_as_something_outside_the_claim_is_accepted():
    v = compare_only_claim(["TLS 1.3"], obs(R, R, A, A))
    assert v.result == FALSE and v.outside_accepted == ["TLS 1.2"]


def test_false_wins_even_if_other_versions_could_not_be_tested():
    v = compare_only_claim(["TLS 1.3"], obs(U, U, A, A))
    assert v.result == FALSE and v.outside_accepted == ["TLS 1.2"]
    assert compare_only_claim(["TLS 1.3"], obs(U, U, A, U)).result == FALSE


def test_unknown_never_becomes_true():
    v = compare_only_claim(["TLS 1.3"], obs(U, R, R, A))
    assert v.result == COULDNT and v.unknown == ["TLS 1.0"]
    assert compare_only_claim(["TLS 1.3"], obs(R, R, R, U)).result == COULDNT
    assert compare_only_claim(["TLS 1.3"], obs(U, U, U, U)).result == COULDNT
    assert compare_only_claim(["TLS 1.3"], {}).result == COULDNT
    assert compare_only_claim(["TLS 1.3"], {"TLS 1.3": A}).result == TRUE  # nothing else was in scope


def test_claimed_item_positively_refused_is_false():
    v = compare_only_claim(["TLS 1.2", "TLS 1.3"], obs(R, R, R, A))
    assert v.result == FALSE and v.claimed_refused == ["TLS 1.2"]


def test_empty_claim_or_odd_status_is_couldnt_check():
    assert compare_only_claim([], obs(R, R, R, R)).result == COULDNT
    assert compare_only_claim(["TLS 1.3"], obs(R, R, "refused?", A)).result == COULDNT


def test_works_for_groups_too():
    seen = {"X25519": R, "P-256": A, "P-384": R}
    assert compare_only_claim(["P-256"], seen).result == TRUE
    assert compare_only_claim(["X25519"], seen).result == FALSE
    assert compare_only_claim(["P-256", "X448"], seen).result == COULDNT


EC256 = {"key_type": "EC", "curve": "secp256r1", "key_size": 256}


@pytest.mark.parametrize("claimed,cert,want", [
    ("ECDSA P-256", EC256, True),
    ("ECDSA P-384", EC256, False),
    ("ECDSA P-256", {"key_type": "EC", "curve": "secp256k1", "key_size": 256}, False),
    ("ECDSA P-256", {"key_type": "RSA", "curve": None, "key_size": 2048}, False),
    ("RSA 2048", {"key_type": "RSA", "curve": None, "key_size": 2048}, True),
    ("RSA 2048", {"key_type": "RSA", "curve": None, "key_size": 4096}, False),
    ("RSA 2048", EC256, False),
    ("Ed25519", {"key_type": "Ed25519", "key_size": 256}, True),
    ("ML-DSA-65", EC256, None),
])
def test_certificate_rule(claimed, cert, want):
    assert certificate_matches(claimed, cert) is want


@pytest.mark.parametrize("name,curve,size,want", [
    ("ECDSA-P256", None, None, "ECDSA P-256"),
    ("ecdsa", "secp256r1", "256", "ECDSA P-256"),
    ("SHA256withECDSA", "prime256v1", None, "ECDSA P-256"),
    ("ECDSA P-384", None, None, "ECDSA P-384"),
    ("ECDSA", None, "256", None),
    ("RSA-2048", None, None, "RSA 2048"),
    ("SHA256withRSA", None, 3072, "RSA 3072"),
    ("SHA256withRSA", None, None, None),
    ("Ed25519", None, None, "Ed25519"),
    ("ML-DSA-65", None, None, None),
    ("", None, None, None),
])
def test_algorithm_names(name, curve, size, want):
    assert normalize_algorithm(name, curve, size) == want


def test_same_algorithm_is_exact_after_normalising():
    assert same_algorithm("ECDSA P-256", "ecdsa-p256")
    assert not same_algorithm("ECDSA P-256", "ECDSA P-384")
    assert not same_algorithm("ECDSA P-256", "Ed25519")
    assert same_algorithm("ML-DSA-65", "ml_dsa 65")
    assert not same_algorithm("ML-DSA-65", "ML-DSA-87")
    assert not same_algorithm("", "")


@pytest.mark.parametrize("text,want", [("TLS1.3", "TLS 1.3"), ("TLSv1.2", "TLS 1.2"), ("1.3", "TLS 1.3"),
                                       ("tls 1.0", "TLS 1.0"), ("TLSv1_1", "TLS 1.1"), ("TLSv1", "TLS 1.0"),
                                       ("SSL3", None), ("1.4", None), ("", None), ("TLS", None)])
def test_tls_version_names(text, want):
    assert normalize_tls_version(text) == want
