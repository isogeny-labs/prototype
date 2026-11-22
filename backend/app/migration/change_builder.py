"""A change, ready to apply (phase 4b): built from a system's plan (the user's choice, or the recommendation until they
choose) and its settings. Pure: the same inputs always give the same change, with the same fingerprint, so a change is
worked out again on every read and only stored when a person acts on it (a try, an approval, an Apply).

A change says what it changes (settings before and after, when the settings are known), the exact lines for nginx,
Apache and an application (each saying on which real software it was checked, or that it was not), the test ML-DSA
certificate where one is needed, the warnings, and what it promises track by track, which "Try on a test copy" and the
measurement after Apply are held to. Where it can be tried and applied is decided by the caller (`target`)."""

from __future__ import annotations

from app.servers import lab_servers
from app.migration import rules
from app.canonical import sha256_hex

# What each kind of line was checked on (phase 4a and 4b, in containers on the build machine; see docs/LIMITS.md).
NGINX = "nginx 1.31.8 with OpenSSL 3.5.9"
APACHE = "Apache 2.4.71 with OpenSSL 3.5.9"
OPENSSL = "OpenSSL 3.5.9"
CHECKED = {
    ("nginx", "hybrid"): NGINX,
    ("nginx", "full_pq"): NGINX,
    ("nginx", "tls13"): NGINX,
    ("apache", "hybrid"): APACHE,
    ("apache", "full_pq"): APACHE,
    ("apache", "tls13"): APACHE,
    ("openssl", "mldsa_request"): OPENSSL,
}
NOT_CHECKED = "Not checked on real software."
PQ_PREFIXES = ("X25519MLKEM768", "SecP256r1MLKEM768", "SecP384r1MLKEM1024", "MLKEM")
MLDSA_REQUEST = (
    "openssl genpkey -algorithm ML-DSA-65 -out server-mldsa65.key\n"
    'openssl req -new -key server-mldsa65.key -subj "/CN=www.example.com" -out server-mldsa65.csr'
)


def _lead(place: str, kind: str, tried: bool = False) -> str:
    where = CHECKED.get((place, kind))
    if not where:
        return NOT_CHECKED
    return f"Checked on {where}" + (", and again in your try:" if tried else ":")


def settings_after(option: str, before: dict | None) -> dict | None:
    """The settings a change puts in force. None for an option that changes no setting here."""
    base = lab_servers.normal(
        before or {"groups": "X25519:P-256", "versions": ["TLS 1.2", "TLS 1.3"], "certificate": "ecdsa-p256"}
    )
    if option == "hybrid":
        classical = [g for g in base["groups"].split(":") if g and not g.startswith(PQ_PREFIXES)] or ["X25519", "P-256"]
        versions = sorted(set(base["versions"]) | {"TLS 1.3"}, key=lab_servers.VERSION_ORDER.index)
        return lab_servers.normal(
            {
                "groups": ":".join(["X25519MLKEM768", *classical]),
                "versions": versions,
                "certificate": base["certificate"],
            }
        )
    if option == "full_pq":
        return lab_servers.normal({"groups": "MLKEM768", "versions": ["TLS 1.3"], "certificate": "mldsa-65"})
    if option == "tls13":
        return lab_servers.normal({**base, "versions": ["TLS 1.3"]})
    return None


def _table(before: dict | None, after: dict, seen_only: bool = False) -> dict:
    """`seen_only`: `before` is what a measurement saw of a server this app can't read the settings of (its TLS
    versions, the classical group it chose and its certificate), not its settings."""

    def plain(s: dict, key: str) -> str:
        return {
            "groups": lab_servers.groups_words(s),
            "versions": lab_servers.versions_words(s),
            "certificate": lab_servers.CERTIFICATE_WORDS.get(s["certificate"], s["certificate"]),
        }[key]

    def now(key: str) -> str:
        if before is None:
            return "Not known: this app can't read this server's settings"
        return plain(before, key) + (
            {
                "groups": " (the one it chose, measured; this app can't see the rest of its list)",
                "versions": " (measured)",
                "certificate": " (measured)",
            }[key]
            if seen_only
            else ""
        )

    def changed(key: str) -> str:
        text = plain(after, key)
        return text + (" (no change)" if before is not None and plain(before, key) == text else "")

    return {
        "columns": ["Setting", "Now", "With the change"],
        "rows": [
            ["Key-exchange groups", now("groups"), changed("groups")],
            ["TLS versions", now("versions"), changed("versions")],
            ["Certificate", now("certificate"), changed("certificate")],
        ],
    }


def build(
    *,
    key: str,
    kind: str,
    option: str,
    system_key: str,
    address: str | None,
    name: str,
    before: dict | None,
    before_auth: str | None,
    target: str | None,
    target_words: str | None,
    no_target: str | None,
    extra: dict | None = None,
) -> dict:
    """One change. kind: "migration" (a system's post-quantum plan) or "tls" (the Acme Pay server's TLS fix, SPEC 7c).
    option: hybrid | full_pq | keep | wrap (migration), tls13 (tls), or sign_both | mldsa_only (a signing program).
    target: where it can be tried and applied ("demo_test_server" | "lab_nginx" | "demo_server") or None, with
    target_words / no_target saying so in plain words."""
    extra = extra or {}
    after = settings_after(option, before) if option in ("hybrid", "full_pq", "tls13") else None
    change: dict = {
        "key": key,
        "kind": kind,
        "option": option,
        "system_key": system_key,
        "address": address,
        "name": name,
        "settings_before": lab_servers.normal(before) if before else None,
        "settings_after": after,
        "target": target,
        "target_words": target_words,
        "no_target": no_target,
        "lines": [],
        "certificate": None,
        "warnings": [],
        "promise": {},
        "table": None,
        "text": [],
        "recheck": [],
        "review_date": extra.get("review_date"),
    }
    if after is not None:
        line_kind = option
        cert_files = option == "full_pq"
        only = option == "tls13"  # the TLS fix changes the versions line only (SPEC 7c: "TLS 1.3 only")
        change["table"] = _table(change["settings_before"], after, extra.get("seen_only"))
        change["lines"] = [
            {
                "place": "nginx",
                "kind": line_kind,
                "lead": _lead("nginx", line_kind),
                "code": lab_servers.nginx_lines(after, cert_files, only),
            },
            {
                "place": "Apache",
                "kind": line_kind,
                "lead": _lead("apache", line_kind),
                "code": lab_servers.apache_lines(after, cert_files, only),
            },
            {
                "place": "Your own application",
                "kind": line_kind,
                "lead": NOT_CHECKED + (" For example:" if only else " With OpenSSL 3.5 or newer, for example:"),
                "code": lab_servers.application_lines(after, only),
            },
        ]
        change["promise"] = {"tls": "passed"} if option == "tls13" else rules.track_promise(option, before_auth)
    if option == "hybrid":
        change["warnings"] = [
            "It needs a TLS library that knows ML-KEM, such as OpenSSL 3.5 or newer. On an older library the nginx line stops nginx "
            "from starting (checked on nginx 1.24.0 with OpenSSL 3.0.13: the configuration test fails).",
            "Clients that can't do hybrid keep connecting with the classical key exchange, which stays in the list.",
            "The client's key share grows from 32 to 1,216 bytes (published: FIPS 203 + X25519), so the first handshake message no longer "
            "fits in one network packet. A few old network devices drop such a message, so test from where your clients connect.",
        ]
        if before and "TLS 1.3" not in before.get("versions", []):
            change["warnings"].insert(0, "It also turns TLS 1.3 on: hybrid key exchange exists in TLS 1.3 only.")
        if extra.get("seen_only"):
            change["warnings"].insert(
                0,
                "This app can't read this server's settings: the lines are built from what it measured. Keep "
                "any other key-exchange groups your server lists today, after X25519MLKEM768.",
            )
    elif option == "full_pq":
        change["certificate"] = {
            "kind": "mldsa-65",
            "lead": _lead("openssl", "mldsa_request"),
            "code": MLDSA_REQUEST,
            "note": (
                "Make your own ML-DSA-65 key and certificate request like this, and have your certificate "
                "authority sign it. A try in the lab uses a throwaway test certificate instead; its test key is "
                "never shown, stored or exported."
            ),
        }
        change["warnings"] = [
            "Clients that can't do ML-KEM key exchange, or can't check an ML-DSA certificate, can no longer connect. There is no classical "
            "fallback, and this app can't see your clients.",
            "The certificate's public key grows to 1,952 bytes and the handshake signature to 3,309 bytes (published: FIPS 204), so the "
            "certificate message grows by several thousand bytes.",
        ]
    elif option == "tls13":
        change["warnings"] = [
            "Older clients and partner systems that can't use TLS 1.3 will no longer be able to connect."
        ]
    elif option == "keep":
        change["text"] = [
            "Keep classical for now: nothing changes on the server. Measure it again by the review date and decide again."
        ]
        change["recheck"] = [
            "Measure this system again (Measure again) and read both tracks.",
            "Check the data lifespan and exposure settings are still right.",
            "Check whether your TLS library now supports ML-KEM (OpenSSL 3.5 or newer does).",
            "NIST deprecates today's public-key algorithms after 2030 and disallows them after 2035 (NIST IR 8547): "
            "the review date can't be later than 31 December 2030.",
        ]
    elif option == "wrap":
        change["text"] = [
            "A gateway (or a network encryptor) in front of this server does the post-quantum part, because the server "
            "itself can't be changed. No product is named here."
        ]
        change["recheck"] = [
            "Accept hybrid key exchange from clients (X25519MLKEM768 next to the classical ones), with TLS 1.3.",
            "Present its own certificate to clients.",
            "Pass each connection on to this server over what the server accepts today"
            + (f" ({extra['versions_words']}, measured)" if extra.get("versions_words") else "")
            + ", and keep that inner link inside your own network, where it can't be recorded from outside.",
            "Measure the gateway's address with this app afterwards: its key exchange should read Hybrid.",
            "It protects the connection only, not cryptography inside the application (for example signing).",
        ]
    elif option in ("sign_both", "mldsa_only"):
        change["text"] = [
            "This change is to the program and its signing library, made by whoever looks after it. It can't be tried or "
            "applied in the lab in this version: the lab runs signing libraries and tests them, but it does not hold your program that "
            "calls one, so it has nothing to change."
        ]
    change["fingerprint"] = sha256_hex({k: v for k, v in change.items() if k != "fingerprint"})
    return change


def download_text(change: dict, generated_at: str) -> str:
    """The change as a plain text file a person can hand to whoever runs the server."""
    out = [
        f"Isogeny Evidence Lab: change for {change['name']}",
        f"Made {generated_at} (UTC). Change fingerprint (SHA-256): {change['fingerprint']}",
        "This file is text. Nothing in it has been applied to your systems by this app.",
        "",
    ]
    if change.get("table"):
        out.append("What it changes:")
        for row in change["table"]["rows"]:
            out.append(f"  {row[0]}: {row[1]}  ->  {row[2]}")
        out.append("")
    for line in change.get("lines") or []:
        out += [f"{line['place']}: {line['lead']}", *("    " + code for code in line["code"].splitlines()), ""]
    if change.get("certificate"):
        cert = change["certificate"]
        out += [
            f"Your own ML-DSA-65 key and certificate request: {cert['lead']}",
            *("    " + c for c in cert["code"].splitlines()),
            cert["note"],
            "",
        ]
    for title, items in (
        ("Before you change it:", change.get("warnings")),
        ("", change.get("text")),
        ("What to check" if change["option"] != "wrap" else "What the gateway must do:", change.get("recheck")),
    ):
        if items:
            if title:
                out.append(title)
            out += [f"  - {item}" for item in items]
            out.append("")
    if change.get("review_date"):
        out += [f"Review date: {change['review_date']}", ""]
    out.append("Afterwards, measure the system again in the app: step 6, Migration, then Measure again.")
    return "\n".join(out) + "\n"
