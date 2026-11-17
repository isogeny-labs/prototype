"""Declarative registry of bounded cryptanalysis-suite (`crax`) tools.

Each tool is one allowlisted fixture of the ``cryptanalysis_suite`` runner. A tool declares:

* typed, bounded parameters (validated before any process starts; unknown keys are ignored),
* how to build the fixed argv for one or more ``crax --json ...`` invocations from validated values only,
* how to read the suite's JSON into metrics (with definitions), pass/fail scenarios and failures,
* its limitations, and named positive / negative controls so a reviewer can see the detector work.

Callers never supply an executable, subcommand, flag or arbitrary argv. Integers are decimal strings of bounded bit
length; curve and scheme names are choices; lists are length-capped.

Secrets recovered from a target that is *not* a declared synthetic control (an ECDSA private key, RSA factors) are
redacted from the stored raw output and metrics, and the redaction is recorded as an exclusion: the platform reports
that a key was recoverable without retaining the key.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

# --------------------------------------------------------------------------- parameter validation

DEC = re.compile(r"[0-9]{1,1300}\Z")
HEX = re.compile(r"(?:[0-9a-fA-F]{2}){0,65536}\Z")
CURVE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+\-]{0,63}\Z")
NAMED_ECDLP_CURVES = ("p256", "secp256k1", "sm2", "eccp131")
ECDSA_CURVES = ("p256", "secp256k1", "sm2")
TOY_REGISTRY_CURVES = ("generic-26", "glv-j0-26", "glv-j1728-26", "glv-j0-32", "glv-j1728-32", "pf-generic-b7",
                       "pf-ssj0-b7", "pf-ssj1728-b7", "pf-mov-b15", "pf-twist-smooth-b19", "pf-j0-twist-b27")
MLWE_SCHEMES = ("ml-dsa-44", "ml-dsa-65", "ml-dsa-87", "ml-kem-512", "ml-kem-768", "ml-kem-1024")
MLWE_MODELS = ("core-svp-classical", "core-svp-quantum", "gate-count", "sieve-memory", "enumeration")
HASH_ALGS = ("sha256", "sha384", "sha512", "sha3-256", "sha3-512", "blake2b", "blake2s", "blake3", "sha1", "md5", "sm3")


class ParamError(ValueError):
    pass


@dataclass
class Param:
    name: str
    kind: str                      # choice | int | uint | point | uint_list | signatures | bool | ident | text | hex
    label: str
    default: Any = None
    required: bool = False
    choices: tuple = ()
    min: int | None = None
    max: int | None = None         # int bounds, or max bits for uint, or max items for lists, or max bytes for text/hex
    help: str = ""
    when: dict | None = None       # only read when another param has one of these values, e.g. {"curve": ["custom"]}

    def spec(self) -> dict:
        return {k: v for k, v in {"name": self.name, "kind": self.kind, "label": self.label, "default": self.default,
                                  "required": self.required, "choices": list(self.choices) or None, "min": self.min,
                                  "max": self.max, "help": self.help, "when": self.when}.items() if v is not None}


def _uint(value: Any, name: str, max_bits: int) -> int:
    if isinstance(value, bool):
        raise ParamError(f"{name} must be a non-negative decimal integer")
    if isinstance(value, int):
        n = value
    elif isinstance(value, str) and DEC.fullmatch(value.strip()):
        n = int(value.strip())
    else:
        raise ParamError(f"{name} must be a non-negative decimal integer")
    if n < 0 or n.bit_length() > max_bits:
        raise ParamError(f"{name} must be a non-negative integer of at most {max_bits} bits")
    return n


def _point(value: Any, name: str, max_bits: int) -> tuple[int, int]:
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    elif isinstance(value, dict):
        parts = [value.get("x"), value.get("y")]
    else:
        raise ParamError(f"{name} must be a point x,y")
    if len(parts) != 2:
        raise ParamError(f"{name} must be a point x,y")
    return _uint(parts[0], f"{name}.x", max_bits), _uint(parts[1], f"{name}.y", max_bits)


def validate(params: list[Param], raw: dict) -> dict:
    out: dict[str, Any] = {}
    for p in params:
        if p.when and not all(out.get(k) in v for k, v in p.when.items()):
            continue
        v = raw.get(p.name, p.default)
        if v is None or v == "" or v == []:
            if p.required:
                raise ParamError(f"{p.name} is required")
            continue
        if p.kind == "choice":
            if v not in p.choices:
                raise ParamError(f"{p.name} must be one of {', '.join(map(str, p.choices))}")
            out[p.name] = v
        elif p.kind == "int":
            if not isinstance(v, int) or isinstance(v, bool) or not (p.min <= v <= p.max):
                raise ParamError(f"{p.name} must be an integer from {p.min} through {p.max}")
            out[p.name] = v
        elif p.kind == "bool":
            if not isinstance(v, bool):
                raise ParamError(f"{p.name} must be true or false")
            out[p.name] = v
        elif p.kind == "uint":
            n = _uint(v, p.name, p.max)
            if p.min is not None and n < p.min:
                raise ParamError(f"{p.name} must be at least {p.min}")
            out[p.name] = n
        elif p.kind == "point":
            out[p.name] = _point(v, p.name, p.max)
        elif p.kind == "uint_list":
            items = v.replace(",", " ").split() if isinstance(v, str) else v
            if not isinstance(items, list) or not 1 <= len(items) <= p.max:
                raise ParamError(f"{p.name} must list 1 to {p.max} integers")
            out[p.name] = [_uint(x, f"{p.name}[{i}]", 4096) for i, x in enumerate(items)]
        elif p.kind == "signatures":
            if not isinstance(v, list) or not 1 <= len(v) <= p.max:
                raise ParamError(f"{p.name} must be a list of 1 to {p.max} signatures {{r, s, z}}")
            sigs = []
            for i, s in enumerate(v):
                if isinstance(s, str):
                    s = dict(zip("rsz", s.split(",")))
                if not isinstance(s, dict):
                    raise ParamError(f"{p.name}[{i}] must be {{r, s, z}}")
                sigs.append(tuple(_uint(s.get(k), f"{p.name}[{i}].{k}", 576) for k in "rsz"))
            out[p.name] = sigs
        elif p.kind == "ident":
            if not isinstance(v, str) or not CURVE_ID.fullmatch(v.strip()):
                raise ParamError(f"{p.name} must be a 1-64 character suite identifier beginning with a letter or digit")
            out[p.name] = v.strip()
        elif p.kind == "text":
            if not isinstance(v, str) or len(v.encode()) > p.max:
                raise ParamError(f"{p.name} must be text of at most {p.max} bytes")
            out[p.name] = v
        elif p.kind == "hex":
            if not isinstance(v, str) or not HEX.fullmatch(v) or len(v) // 2 > p.max:
                raise ParamError(f"{p.name} must be even-length hex of at most {p.max} bytes")
            out[p.name] = v.lower()
        else:  # pragma: no cover - registry bug
            raise ParamError(f"unknown parameter kind {p.kind}")
    return out


# --------------------------------------------------------------------------- tool model

@dataclass
class Parsed:
    metrics: dict = field(default_factory=dict)
    definitions: dict = field(default_factory=dict)
    scenarios: list = field(default_factory=list)
    failures: list = field(default_factory=list)
    exclusions: list = field(default_factory=list)
    raw: Any = None                 # what is stored as raw output (the suite JSON, possibly redacted)


@dataclass
class Tool:
    id: str
    family: str
    title: str
    question: str                   # the customer-facing question this tool answers
    operation: str                  # short contract label, e.g. "crax --json ecdsa audit"
    params: list[Param]
    build: Callable[[dict], list[list[str]]]          # validated params -> list of argv tails (after "crax --json")
    parse: Callable[[dict, list[tuple[int, Any]]], Parsed]  # (validated params, [(exit, json)]) -> Parsed
    limitations: list[str]
    controls: list[dict] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    nonzero_exit_ok: bool = False   # True when exit 1 + JSON means "attack found nothing" (a negative result)
    min_crax: str = "0.1.0"
    runner: str = "cryptanalysis_suite"  # runner kind that executes this tool

    def describe(self) -> dict:
        return {"id": self.id, "family": self.family, "title": self.title, "question": self.question, "runner": self.runner,
                "operation": self.operation, "params": [p.spec() for p in self.params], "limitations": self.limitations,
                "controls": self.controls, "acceptance": self.acceptance}

    def validate(self, raw: dict) -> dict:
        return validate(self.params, raw or {})


COMMON_LIMITS = [
    "The cryptanalysis suite is an attack and research toolkit; it is not constant-time, audited, or a production cryptographic implementation.",
    "This run records only the named suite operation. It is not proof that the target implementation is secure.",
]


def _scen(id_, name, expected, observed, ok, detail=""):
    return {"id": id_, "name": name, "expected": str(expected), "observed": str(observed), "pass": bool(ok), "detail": detail}


def _redact(value: Any) -> str:
    return "[redacted sha256:" + hashlib.sha256(str(value).encode()).hexdigest()[:16] + "]"


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _status_failures(rep: dict, ok_status: tuple[str, ...]) -> list[str]:
    if not isinstance(rep, dict):
        return ["suite JSON root is not an object"]
    if rep.get("status") not in ok_status:
        return [str(rep.get("error") or rep.get("message") or f"suite status was {rep.get('status')!r}")]
    return []


# --------------------------------------------------------------------------- 1, 2: curve audit and estimate (icx)

def _icx_audit_parse(p, results):
    code, rep = results[0]
    out = Parsed(raw=rep)
    out.failures = []
    if rep.get("schema_version") != 1:
        out.failures.append(f"unsupported suite schema_version: {rep.get('schema_version')!r}")
    if rep.get("operation") != "inspect":
        out.failures.append(f"suite returned operation {rep.get('operation')!r}; expected 'inspect'")
    if rep.get("status") != "checks_passed":
        out.failures.append(str(rep.get("message") or f"suite status was {rep.get('status')!r}"))
    if rep.get("verified") is not True:
        out.failures.append("suite did not verify every curve parameter check")
    curve = rep.get("curve") if isinstance(rep.get("curve"), dict) else {}
    fld = curve.get("field") if isinstance(curve.get("field"), dict) else {}
    for i, c in enumerate(rep.get("checks") or []):
        if isinstance(c, dict):
            name = str(c.get("name", f"check_{i + 1}"))
            obs = str(c.get("status", "unknown"))
            out.scenarios.append(_scen("suite_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"), name, "pass", obs,
                                       obs == "pass", str(c.get("detail", ""))))
    m = {"suite_verified": 1 if rep.get("verified") is True else 0,
         "suite_checks_passed": sum(1 for s in out.scenarios if s["pass"]), "suite_checks_total": len(out.scenarios),
         "field_bits": fld.get("bits"), "subgroup_order_bits": curve.get("order_bits"),
         "rho_security_bits": _num(curve.get("rho_security_bits"))}
    try:
        m["cofactor"] = int(curve.get("cofactor"))
    except (TypeError, ValueError):
        pass
    out.metrics = {k: v for k, v in m.items() if v is not None}
    out.definitions = {
        "suite_verified": "1 only when every parameter check in the suite's icx inspect report passed.",
        "suite_checks_passed": "Count of icx parameter checks whose reported status is pass.",
        "suite_checks_total": "Total parameter checks returned by icx inspect.",
        "field_bits": "Bit length of the catalog field reported by icx inspect.",
        "subgroup_order_bits": "Bit length of the catalog subgroup order reported by icx inspect.",
        "rho_security_bits": "Suite estimate of generic Pollard-rho security in bits for the named subgroup; an operation-count model, not elapsed time.",
        "cofactor": "Catalog curve group cofactor parsed from the suite report.",
    }
    return out


def _icx_estimate_parse(p, results):
    code, rep = results[0]
    out = Parsed(raw=rep)
    if rep.get("schema_version") != 1:
        out.failures.append(f"unsupported suite schema_version: {rep.get('schema_version')!r}")
    if rep.get("operation") != "estimate":
        out.failures.append(f"suite returned operation {rep.get('operation')!r}; expected 'estimate'")
    status = str(rep.get("status", "unknown"))
    if status != "complete":
        out.failures.append(str(rep.get("message") or f"suite status was {status!r}"))
    g = rep.get("generic_attack") if isinstance(rep.get("generic_attack"), dict) else {}
    ic = rep.get("index_calculus") if isinstance(rep.get("index_calculus"), dict) else {}
    m = {"field_bits": rep.get("field_bits"), "subgroup_order_bits": rep.get("order_bits"),
         "rho_security_bits": _num(g.get("security_bits")), "rho_log2_operations": _num(g.get("log2_operations")),
         "index_calculus_relevant": 1 if ic.get("relevant") is True else 0}
    out.metrics = {k: v for k, v in m.items() if v is not None}
    out.definitions = {
        "field_bits": "Bit length of the catalog field used by the suite estimate.",
        "subgroup_order_bits": "Bit length of the catalog subgroup order used by the suite estimate.",
        "rho_security_bits": "Generic Pollard-rho security estimate in bits from icx; not a wall-clock prediction.",
        "rho_log2_operations": "Base-2 logarithm of the suite's generic Pollard-rho operation-count estimate.",
        "index_calculus_relevant": "1 when the suite classifies index calculus as relevant for the named curve family and configured envelope; 0 otherwise.",
    }
    out.scenarios = [_scen("suite_estimate_generated", "Machine-readable suite estimate generated", "complete", status,
                           status == "complete", "This validates report completion only; it does not validate practical attack feasibility.")]
    return out


CURVE_AUDIT = Tool(
    id="suite_curve_audit", family="Curves & parameters", title="Curve parameter audit",
    question="Are the standardized curve parameters we rely on the ones in the catalog, and do the basic group checks hold?",
    operation="crax --json icx inspect CURVE",
    params=[Param("curve", "ident", "Suite curve identifier", "p256", True, help="e.g. p256, secp256k1, p384, curve25519")],
    build=lambda p: [["icx", "inspect", p["curve"]]],
    parse=_icx_audit_parse,
    limitations=COMMON_LIMITS + ["Curve inspection verifies catalog parameters and group checks; it does not inspect application code, key generation, protocol use, side channels, or fault resistance."],
    acceptance=["every suite parameter check passes", "suite_verified == 1"],
    controls=[{"name": "P-256 (negative control: expected clean)", "kind": "negative", "params": {"curve": "p256"}}],
)

CURVE_ESTIMATE = Tool(
    id="suite_curve_estimate", family="Curves & parameters", title="Attack-cost model (rho / index calculus)",
    question="What does the suite's operation-count model say about generic and index-calculus attacks on this curve?",
    operation="crax --json icx estimate CURVE --envelope N",
    params=[Param("curve", "ident", "Suite curve identifier", "p256", True),
            Param("envelope_bits", "int", "Index-calculus envelope bits", 64, min=8, max=512)],
    build=lambda p: [["icx", "estimate", p["curve"], "--envelope", str(p.get("envelope_bits", 64))]],
    parse=_icx_estimate_parse,
    limitations=COMMON_LIMITS + ["The attack-cost result is a named operation-count model, not a wall-clock prediction, exploit demonstration, or claim of practical breakability."],
    acceptance=["suite report completes", "result remains labelled as an operation-count model"],
    controls=[{"name": "P-256, 64-bit envelope", "kind": "negative", "params": {"curve": "p256", "envelope_bits": 64}}],
)


# --------------------------------------------------------------------------- 3: structural weak-curve analysis

def _weak_build(p):
    if p["curve"] != "custom":
        return [["ecdlp", "--curve", p["curve"], "--analyze-only", "--x", "1"]]
    for k in ("p", "a", "b", "g", "order"):
        if k not in p:
            raise ParamError(f"{k} is required for a custom curve")
    argv = ["ecdlp", "--p", str(p["p"]), "--a", str(p["a"]), "--b", str(p["b"]), "--g", "%d,%d" % p["g"],
            "--order", str(p["order"]), "--max-log2-ops", "34"]
    if "plant_secret" in p:
        argv += ["--x", str(p["plant_secret"])]
    else:
        argv += ["--analyze-only", "--x", "1"]
    return [argv]


def _weak_parse(p, results):
    code, rep = results[0]
    out = Parsed(raw=rep, failures=_status_failures(rep, ("analysed", "ok")))
    an = rep.get("analysis") if isinstance(rep.get("analysis"), dict) else {}
    checks = [c for c in an.get("checks") or [] if isinstance(c, dict)]
    applicable = [c for c in checks if c.get("applicable") is True]
    expect = p.get("expect", "no_structural_weakness")
    for c in checks:
        meth = str(c.get("method"))
        obs = "applies" if c.get("applicable") else "does not apply"
        exp = "does not apply" if expect == "no_structural_weakness" else "(either)"
        ok = (not c.get("applicable")) if expect == "no_structural_weakness" else True
        out.scenarios.append(_scen(f"weak_{meth.lower()}", f"{meth} attack", exp, obs, ok, str(c.get("explanation", ""))))
    if expect == "weakness_detected":
        out.scenarios.append(_scen("weak_detected", "Detector flags a structural weakness", "≥ 1 applies",
                                   f"{len(applicable)} apply", len(applicable) > 0, f"recommended: {an.get('recommended')}"))
    if "plant_secret" in p:
        rec = rep.get("verified") is True and rep.get("matches_planted") is True
        out.scenarios.append(_scen("weak_planted_recovered", "Planted discrete log recovered and verified",
                                   "recovered", "recovered" if rec else "not recovered", rec,
                                   f"method {rep.get('method')}; Q = x·G recomputed by the suite"))
    ph = next((c for c in checks if c.get("method") == "PohligHellman"), {})
    m = {"p_bits": an.get("p_bits"), "structural_attacks_applicable": len(applicable), "checks_evaluated": len(checks),
         "pohlig_hellman_log2_ops": _num(ph.get("estimated_log2_ops")), "embedding_degree": an.get("embedding_degree"),
         "analysis_ms": _num(an.get("analysis_ms"))}
    if "plant_secret" in p:
        m["planted_secret_recovered"] = 1 if rep.get("matches_planted") else 0
        m["attack_ms"] = _num(rep.get("attack_ms"))
    out.metrics = {k: v for k, v in m.items() if v is not None}
    out.definitions = {
        "p_bits": "Bit length of the field prime.",
        "structural_attacks_applicable": "Number of structural ECDLP shortcuts (singular, Smart anomalous, Pohlig–Hellman within budget, MOV/Frey–Rück with embedding degree ≤ 12) the suite found applicable.",
        "checks_evaluated": "Number of structural checks the suite evaluated.",
        "pohlig_hellman_log2_ops": "log2 of the suite's Pohlig–Hellman group-operation estimate for the largest prime factor of the order; a model output.",
        "embedding_degree": "Embedding degree reported by the suite when it computed one (MOV relevance).",
        "analysis_ms": "Suite-reported wall time of the structural analysis on this host, in milliseconds.",
        "planted_secret_recovered": "1 when the suite recovered the planted discrete log and verified Q = x·G (synthetic control only).",
        "attack_ms": "Suite-reported wall time of the structural attack on this host, in milliseconds (toy-sized control).",
    }
    return out


WEAK_CURVE = Tool(
    id="suite_weak_curve", family="Curves & parameters", title="Structural weak-curve analysis",
    question="Does this curve admit a structural ECDLP shortcut — singular, anomalous (Smart), smooth order (Pohlig–Hellman) or low embedding degree (MOV)?",
    operation="crax --json ecdlp --analyze-only",
    params=[
        Param("curve", "choice", "Curve", "p256", True, choices=NAMED_ECDLP_CURVES + ("custom",),
              help="A named curve, or custom short-Weierstrass parameters (e.g. a vendor or legacy curve)."),
        Param("p", "uint", "Field prime p", max=521, when={"curve": ["custom"]}),
        Param("a", "uint", "a", max=521, when={"curve": ["custom"]}),
        Param("b", "uint", "b", max=521, when={"curve": ["custom"]}),
        Param("g", "point", "Base point G (x,y)", max=521, when={"curve": ["custom"]}),
        Param("order", "uint", "Order of G", max=522, when={"curve": ["custom"]}),
        Param("plant_secret", "uint", "Plant a secret x and attack Q = x·G (controls only)", max=64, when={"curve": ["custom"]},
              help="Runs the cheapest applicable structural attack within 2^34 operations."),
        Param("expect", "choice", "Expected outcome", "no_structural_weakness",
              choices=("no_structural_weakness", "weakness_detected")),
    ],
    build=_weak_build, parse=_weak_parse,
    limitations=COMMON_LIMITS + [
        "Absence of a structural shortcut leaves generic attacks (Pollard rho) as the best known; it is not proof of hardness.",
        "Pohlig–Hellman and MOV checks are bounded by the suite's 2^34 operation budget and embedding degree ≤ 12.",
    ],
    acceptance=["every structural check matches the stated expectation"],
    controls=[
        {"name": "P-256 (negative control)", "kind": "negative", "params": {"curve": "p256"}},
        {"name": "secp256k1 (negative control)", "kind": "negative", "params": {"curve": "secp256k1"}},
        {"name": "Anomalous toy curve, #E = p = 757 (positive control: Smart)", "kind": "positive",
         "params": {"curve": "custom", "p": "757", "a": "537", "b": "465", "g": "1,130", "order": "757",
                    "plant_secret": "123", "expect": "weakness_detected"}},
        {"name": "Pairing-friendly toy curve, k = 2 (positive control: MOV / Pohlig–Hellman)", "kind": "positive",
         "params": {"curve": "custom", "p": "41609", "a": "0", "b": "1", "g": "1,19800", "order": "41610",
                    "plant_secret": "99", "expect": "weakness_detected"}},
    ],
)


# --------------------------------------------------------------------------- 4: ECDSA transcript audit

def _ecdsa_build(p):
    if p.get("mode") == "planted_bias_control":
        return [["ecdsa", "audit", "--curve", p["curve"], "--demo", "--demo-sigs", str(p.get("demo_sigs", 8)),
                 "--demo-k-bits", str(p.get("demo_k_bits", 192)), "--seed", str(p.get("seed", 1))]]
    if "public_key" not in p or "signatures" not in p:
        raise ParamError("public_key and signatures are required for a transcript audit")
    argv = ["ecdsa", "audit", "--curve", p["curve"], "--q", "%d,%d" % p["public_key"]]
    if p.get("full_sweep"):
        argv.append("--no-prefilter")
    for r, s, z in p["signatures"]:
        argv += ["--sig", f"{r},{s},{z}"]
    return [argv]


def _ecdsa_parse(p, results):
    code, rep = results[0]
    out = Parsed(raw=dict(rep) if isinstance(rep, dict) else rep, failures=_status_failures(rep, ("ok",)))
    synthetic = p.get("mode") == "planted_bias_control"
    expect = p.get("expect", "no_bias" if not synthetic else "key_recovered")
    verdict = str(rep.get("verdict", "unknown"))
    recovered = verdict == "key_recovered" and rep.get("verified") is True
    if recovered and not synthetic and isinstance(out.raw, dict) and "d" in out.raw:
        out.raw["d"] = _redact(out.raw["d"])
        out.exclusions.append("Recovered private scalar d redacted from stored evidence (target is not a synthetic control); "
                              "its SHA-256 prefix is retained for later confirmation.")
    out.scenarios = [_scen("ecdsa_verdict", "Transcript verdict", expect, verdict, verdict == expect,
                           "no_bias: no lattice key recovery within the swept k-bit range; key_recovered: d·G == Q verified by the suite.")]
    if recovered:
        out.scenarios.append(_scen("ecdsa_key_verified", "Recovered key independently verified (d·G == Q)", "verified" if expect == "key_recovered" else "not recoverable",
                                   "verified", expect == "key_recovered", f"assumed nonce bound k < 2^{rep.get('k_bits')}"))
    out.metrics = {"signatures_audited": rep.get("signatures"), "bias_score": _num(rep.get("bias_score")),
                   "key_recovered": 1 if recovered else 0}
    if rep.get("k_bits") is not None:
        out.metrics["recovered_with_k_bits"] = rep.get("k_bits")
    out.metrics = {k: v for k, v in out.metrics.items() if v is not None}
    out.definitions = {
        "signatures_audited": "Number of (r, s, z) samples in the audited transcript.",
        "bias_score": "Suite statistical nonce-bias score over the transcript (higher is more suspicious); a heuristic, not a probability.",
        "key_recovered": "1 when the suite's hidden-number-problem lattice attack recovered the signing key and verified d·G == Q.",
        "recovered_with_k_bits": "The nonce bit-bound k < 2^k_bits under which recovery succeeded.",
    }
    return out


ECDSA_AUDIT = Tool(
    id="suite_ecdsa_audit", family="Signatures & keys", title="ECDSA signature-transcript audit",
    question="Do the signatures our service actually emits leak the signing key through biased or reused nonces?",
    operation="crax --json ecdsa audit",
    params=[
        Param("curve", "choice", "Curve", "p256", True, choices=ECDSA_CURVES),
        Param("mode", "choice", "Mode", "transcript", choices=("transcript", "planted_bias_control"),
              help="transcript: audit supplied signatures. planted_bias_control: the suite signs with a deliberately biased nonce and must recover the key."),
        Param("public_key", "point", "Public key Q (x,y)", max=576, when={"mode": ["transcript"]}),
        Param("signatures", "signatures", "Signatures [{r, s, z}] (z = hash as integer)", max=512, when={"mode": ["transcript"]}),
        Param("full_sweep", "bool", "Full lattice sweep (skip the statistical prefilter; ~20 s for 32 signatures)", False, when={"mode": ["transcript"]}),
        Param("demo_sigs", "int", "Planted signatures", 8, min=4, max=64, when={"mode": ["planted_bias_control"]}),
        Param("demo_k_bits", "int", "Planted nonce bound (bits)", 192, min=64, max=248, when={"mode": ["planted_bias_control"]}),
        Param("seed", "int", "Seed", 1, min=0, max=2**32 - 1, when={"mode": ["planted_bias_control"]}),
        Param("expect", "choice", "Expected verdict", "no_bias", choices=("no_bias", "key_recovered")),
    ],
    build=_ecdsa_build, parse=_ecdsa_parse,
    limitations=COMMON_LIMITS + [
        "Without full_sweep, a statistical prefilter can end the audit before any lattice attack runs; the run's argv shows which mode was used.",
        "A no_bias verdict means this lattice attack did not recover the key over the swept nonce bounds from these samples; small or unbiased-looking transcripts can hide subtler leakage.",
        "Timing, cache and fault side channels are out of scope; only the emitted (r, s, z) values are analysed.",
        "Recovered keys from non-synthetic transcripts are redacted from stored evidence.",
    ],
    acceptance=["verdict equals the stated expectation"],
    controls=[
        {"name": "Planted 192-bit nonces, 8 signatures (positive control)", "kind": "positive",
         "params": {"curve": "p256", "mode": "planted_bias_control", "demo_sigs": 8, "demo_k_bits": 192, "seed": 1, "expect": "key_recovered"}},
    ],
)


# --------------------------------------------------------------------------- 5: RSA public-key hygiene audit

def _rsa_build(p):
    ns = p["moduli"]
    e = str(p.get("public_exponent", 65537))
    it = str(p.get("fermat_iterations", 100000))
    cmds = [["rsa", "batch-gcd", *map(str, ns)]] if len(ns) > 1 else []
    for n in ns:
        cmds.append(["rsa", "fermat", str(n), "--iterations", it])
        cmds.append(["rsa", "wiener", str(n), "--e", e])
    return cmds


def _rsa_parse(p, results):
    ns = p["moduli"]
    synthetic = p.get("synthetic", False)
    out = Parsed()
    redacted = False

    def scrub(rep):
        nonlocal redacted
        if synthetic or not isinstance(rep, dict):
            return rep
        rep = json.loads(json.dumps(rep))
        for k in ("p", "q", "d"):
            if rep.get(k) not in (None, ""):
                rep[k] = _redact(rep[k]); redacted = True
        for f in rep.get("factored") or []:
            for k in ("p", "q"):
                if k in f:
                    f[k] = _redact(f[k]); redacted = True
        return rep

    stored = []
    shared = set()
    i = 0
    if len(ns) > 1:
        code, rep = results[0]
        i = 1
        if not isinstance(rep, dict) or "moduli" not in rep:
            out.failures.append(f"batch-gcd did not return a report: {rep!r}"[:300])
        else:
            shared = {int(f.get("index")) for f in rep.get("factored") or [] if isinstance(f, dict)}
            shared |= {int(x) for d in rep.get("duplicates") or [] for x in (d if isinstance(d, list) else [d]) if str(x).isdigit()}
        stored.append({"attack": "batch-gcd", "exit": code, "report": scrub(rep)})
    fermat_hits, wiener_hits = set(), set()
    for idx, n in enumerate(ns):
        for attack, hits in (("fermat", fermat_hits), ("wiener", wiener_hits)):
            code, rep = results[i]; i += 1
            if not isinstance(rep, dict) or rep.get("attack") != attack:
                out.failures.append(f"{attack} on modulus #{idx} returned no report (exit {code})")
            elif rep.get("verified") is True:
                hits.add(idx)
            stored.append({"attack": attack, "modulus_index": idx, "exit": code, "report": scrub(rep)})
    expect = p.get("expect", "no_weakness")
    weak = shared | fermat_hits | wiener_hits
    for idx, n in enumerate(ns):
        why = [w for w, s in (("shares a prime with another key (batch GCD)", shared), ("primes too close (Fermat)", fermat_hits),
                              ("small private exponent (Wiener)", wiener_hits)) if idx in s]
        obs = "; ".join(why) if why else "no weakness found"
        exp = "no weakness found" if expect == "no_weakness" else "(either)"
        out.scenarios.append(_scen(f"rsa_modulus_{idx}", f"Modulus #{idx} ({n.bit_length()} bits)", exp, obs,
                                   (not why) if expect == "no_weakness" else True))
    if expect == "weakness_detected":
        out.scenarios.append(_scen("rsa_detected", "Detector flags at least one weak modulus", "≥ 1", len(weak), len(weak) > 0))
    if redacted:
        out.exclusions.append("Recovered RSA factors / private exponents redacted from stored evidence (keys are not synthetic controls).")
    out.raw = {"tool": "suite_rsa_key_audit", "synthetic": synthetic, "reports": stored}
    out.metrics = {"moduli_audited": len(ns), "weak_moduli": len(weak), "shared_prime_moduli": len(shared),
                   "fermat_factored": len(fermat_hits), "wiener_factored": len(wiener_hits),
                   "min_modulus_bits": min(n.bit_length() for n in ns)}
    out.definitions = {
        "moduli_audited": "Number of RSA public moduli submitted.",
        "weak_moduli": "Moduli factored by at least one of batch GCD, Fermat (close primes) or Wiener (small d).",
        "shared_prime_moduli": "Moduli sharing a prime factor with another submitted modulus (batch GCD), the classic weak-RNG failure.",
        "fermat_factored": "Moduli factored by Fermat's method within the configured iterations (|p − q| small).",
        "wiener_factored": "Moduli whose private exponent the Wiener continued-fraction attack recovered (d < N^0.25 / 3).",
        "min_modulus_bits": "Smallest modulus size in the batch, in bits.",
    }
    return out


RSA_AUDIT = Tool(
    id="suite_rsa_key_audit", family="Signatures & keys", title="RSA public-key hygiene audit",
    question="Are any of our deployed RSA public keys factorable from public data alone (shared primes, close primes, small d)?",
    operation="crax --json rsa batch-gcd | fermat | wiener",
    params=[
        Param("moduli", "uint_list", "Public moduli N (decimal)", required=True, max=32),
        Param("public_exponent", "uint", "Public exponent e (for Wiener)", 65537, max=4096),
        Param("fermat_iterations", "int", "Fermat iterations per modulus", 100000, min=1, max=1000000),
        Param("synthetic", "bool", "Synthetic control keys (retain recovered factors)", False),
        Param("expect", "choice", "Expected outcome", "no_weakness", choices=("no_weakness", "weakness_detected")),
    ],
    build=_rsa_build, parse=_rsa_parse, nonzero_exit_ok=True,
    limitations=COMMON_LIMITS + [
        "Only three public-data attacks run. Passing them says nothing about padding (PKCS#1 v1.5 parsing), key storage, side channels or entropy beyond shared primes within this batch.",
        "Batch GCD only finds primes shared within the submitted batch; larger corpora find more.",
        "Fermat is bounded by the configured iteration count.",
    ],
    acceptance=["no modulus is factored (or, for controls, the planted weakness is found)"],
    controls=[],  # filled by the seed with freshly generated weak moduli (see app/seed.py)
)


# --------------------------------------------------------------------------- 6: ML-KEM / ML-DSA lattice estimate

_MLWE_LINE = re.compile(r"^\s{2}(?P<name>[a-z][a-z\-]*(?: \([^)]*\))?)\s+.*?log2 cost =\s+(?P<cost>[0-9.]+)", re.M)
_MLWE_CHEAP = re.compile(r"cheapest believable:\s*(?P<name>.+?) at 2\^(?P<cost>[0-9.]+)")
_MLWE_FLOOR = re.compile(r"NIST category (?P<cat>\d) floor:\s*2\^(?P<floor>[0-9.]+)")


def _mlwe_parse(p, results):
    code, rep = results[0]
    out = Parsed(raw=rep)
    text = rep.get("report_text", "") if isinstance(rep, dict) else ""
    if not isinstance(rep, dict) or rep.get("exit_code") != 0 or not text:
        out.failures.append("mlwe estimate did not complete: " + str((rep or {}).get("diagnostics_text", ""))[:300])
        return out
    attacks = {m["name"]: float(m["cost"]) for m in _MLWE_LINE.finditer(text)}
    cheap = _MLWE_CHEAP.search(text)
    floor = _MLWE_FLOOR.search(text)
    out.metrics = {f"log2_cost_{re.sub(r'[^a-z0-9]+', '_', k.lower()).strip('_')}": v for k, v in attacks.items()}
    if cheap:
        out.metrics["cheapest_log2_cost"] = float(cheap["cost"])
    if floor:
        out.metrics["nist_category"] = int(floor["cat"])
        out.metrics["nist_floor_log2_gates"] = float(floor["floor"])
        if p.get("model") == "gate-count" and p.get("tours") and cheap:
            out.metrics["margin_vs_nist_floor_bits"] = round(float(cheap["cost"]) - float(floor["floor"]), 2)
    out.definitions = {
        "log2_cost_*": "log2 cost of the named lattice attack under the selected SVP cost model (suite closed-form estimate).",
        "cheapest_log2_cost": "log2 cost of the cheapest attack the suite considers believable under the selected model.",
        "nist_category": "NIST security category of the parameter set.",
        "nist_floor_log2_gates": "log2 of the NIST category floor in classical gates. Comparable only to the gate-count model with BKZ tours.",
        "margin_vs_nist_floor_bits": "cheapest_log2_cost − NIST floor, reported only for gate-count + tours (the comparable convention). Model-dependent; not a pass/fail gate.",
    }
    out.scenarios = [_scen("mlwe_estimate", "Lattice estimate produced", "complete", "complete" if cheap else "partial", bool(cheap),
                           (f"cheapest: {cheap['name']}" if cheap else "no cheapest-attack line found"))]
    return out


MLWE = Tool(
    id="suite_mlwe_estimate", family="Post-quantum", title="ML-KEM / ML-DSA lattice-attack estimate",
    question="Under named cost models, how much lattice-attack work separates our ML-KEM / ML-DSA parameter set from key recovery?",
    operation="crax --json mlwe estimate --scheme S --model M",
    params=[Param("scheme", "choice", "Parameter set", "ml-dsa-44", True, choices=MLWE_SCHEMES),
            Param("model", "choice", "SVP cost model", "gate-count", choices=MLWE_MODELS),
            Param("tours", "bool", "Charge BKZ tours (needed to compare with NIST floors)", True)],
    build=lambda p: [["mlwe", "estimate", "--scheme", p["scheme"], "--model", p.get("model", "gate-count"), "--color", "never"]
                     + (["--tours"] if p.get("tours") else [])],
    parse=_mlwe_parse,
    limitations=COMMON_LIMITS + [
        "Closed-form lattice estimates under named models; different models differ by tens of bits. Quote the model with any number.",
        "Covers only the key-recovery (MLWE) side; implementation attacks (decapsulation leakage, mask leakage, faults) are separate.",
        "This is not a FIPS 203/204 conformance test.",
    ],
    acceptance=["estimate produced; values reported with their model"],
    controls=[{"name": "ML-DSA-44, gate-count + tours", "kind": "negative", "params": {"scheme": "ml-dsa-44", "model": "gate-count", "tours": True}},
              {"name": "ML-KEM-512, gate-count + tours (known thin margin)", "kind": "reference", "params": {"scheme": "ml-kem-512", "model": "gate-count", "tours": True}}],
)


# --------------------------------------------------------------------------- 7: generic rho on a toy curve (research demo)

def _rho_parse(p, results):
    code, rep = results[0]
    out = Parsed(raw=rep, failures=_status_failures(rep, ("ok",)))
    st = rep.get("stats") if isinstance(rep.get("stats"), dict) else {}
    grp = rep.get("group") if isinstance(rep.get("group"), dict) else {}
    ok = rep.get("verified") is True and rep.get("matches_planted") is True
    out.scenarios = [_scen("rho_recovered", "Planted discrete log recovered and verified", "recovered",
                           "recovered" if ok else "not recovered", ok, "h = x·g recomputed by the suite")]
    try:
        order_bits = int(grp.get("order")).bit_length()
    except (TypeError, ValueError):
        order_bits = None
    out.metrics = {k: v for k, v in {"group_ops": st.get("group_ops"), "ops_per_sqrt_order": _num(st.get("ops_per_sqrt_width")),
                                      "collisions": st.get("collisions"), "seconds": _num(st.get("seconds")),
                                      "order_bits": order_bits, "bytes_peak": st.get("bytes_peak")}.items() if v is not None}
    out.definitions = {
        "group_ops": "Group operations counted by the suite's rho walk (the counted unit).",
        "ops_per_sqrt_order": "The suite's group_ops / √(order) ratio for this one walk, including table set-up; a single random-walk sample, so compare constants only across repeated seeds.",
        "collisions": "Distinguished-point collisions observed.",
        "seconds": "Suite-reported wall time on this host; one sample, not a benchmark.",
        "order_bits": "Bit length of the subgroup order.",
        "bytes_peak": "Peak distinguished-point table memory reported by the suite.",
    }
    return out


RHO = Tool(
    id="suite_generic_rho", family="Research demos", title="Pollard rho on a toy curve",
    question="What does the generic attack — the reference every index-calculus result is measured against — actually cost on a small curve?",
    operation="crax --json rho --curve TOY --x SECRET",
    params=[Param("curve", "choice", "Toy registry curve", "generic-26", True, choices=TOY_REGISTRY_CURVES),
            Param("secret", "uint", "Planted secret x", "123456", True, max=40),
            Param("negation", "bool", "Use the negation map", True),
            Param("seed", "int", "Walk seed", 1, min=0, max=2**32 - 1)],
    build=lambda p: [["rho", "--curve", p["curve"], "--x", str(p["secret"]), "--seed", str(p.get("seed", 1)), "--max-ops", "268435456"]
                     + ([] if p.get("negation", True) else ["--no-negation"])],
    parse=_rho_parse,
    limitations=COMMON_LIMITS + ["Toy-sized group (≤ 32-bit order). One run is one sample of a random walk; use repeated seeds for a constant.",
                                 "Says nothing about any deployed curve."],
    acceptance=["planted secret recovered and verified"],
    controls=[{"name": "generic-26, negation map", "kind": "positive", "params": {"curve": "generic-26", "secret": "123456", "negation": True, "seed": 1}}],
)


# --------------------------------------------------------------------------- 8: integer factoring (toy)

def _factor_parse(p, results):
    code, rep = results[0]
    out = Parsed(raw=rep)
    if not isinstance(rep, dict) or "factors" not in rep:
        out.failures.append(str((rep or {}).get("error", "factor did not return a report")))
        return out
    ok = rep.get("complete") is True and rep.get("verified") is True
    out.scenarios = [_scen("factor_complete", "Complete, verified factorisation", "complete", "complete" if ok else "incomplete", ok,
                           ", ".join(f"{f.get('prime')}^{f.get('exponent')} via {f.get('method')}" for f in rep.get("factors", [])))]
    out.metrics = {"n_bits": p["n"].bit_length(), "prime_factors": len(rep.get("factors", [])),
                   "total_seconds": _num(rep.get("total_seconds")), "complete": 1 if ok else 0}
    out.definitions = {"n_bits": "Bit length of the toy integer.", "prime_factors": "Distinct prime factors found.",
                       "total_seconds": "Suite-reported wall time on this host (one sample).", "complete": "1 when factorisation is complete and verified by multiplication."}
    return out


FACTOR = Tool(
    id="suite_factor_toy", family="Research demos", title="Integer factoring (toy sizes)",
    question="How quickly do the suite's trial division / rho / p−1 / ECM / SIQS pipeline factor small integers?",
    operation="crax --json factor N",
    params=[Param("n", "uint", "Integer N (≤ 128 bits)", "1000000016000000063", True, min=4, max=128)],
    build=lambda p: [["factor", str(p["n"])]],
    parse=_factor_parse,
    limitations=COMMON_LIMITS + ["Bounded to 128-bit inputs; says nothing about RSA-2048 or larger moduli."],
    acceptance=["complete verified factorisation"],
    controls=[{"name": "60-bit semiprime (10^9+7)(10^9+9)", "kind": "positive", "params": {"n": "1000000016000000063"}}],
)


# --------------------------------------------------------------------------- 9: reduced-round AES key recovery

def _aes_parse(p, results):
    code, rep = results[0]
    out = Parsed(raw=rep)
    if not isinstance(rep, dict) or "status" not in rep:
        out.failures.append("aes-attack did not return a report")
        return out
    ok = rep.get("status") == "solved" and rep.get("verified") is True
    out.scenarios = [_scen("aes_solved", f"{p['technique']} key recovery on reduced-round AES", "solved", rep.get("status"), ok,
                           f"{rep.get('rounds')} round(s); scope {rep.get('recovery_scope', 'master key')}")]
    out.metrics = {k: v for k, v in {"rounds": rep.get("rounds"), "pairs_used": rep.get("pairs_used"), "trials": rep.get("trials"),
                                      "verified": 1 if rep.get("verified") else 0}.items() if v is not None}
    out.definitions = {"rounds": "AES rounds in the attacked reduced-round instance.", "pairs_used": "Plaintext/ciphertext pairs consumed.",
                       "trials": "Key-candidate trials the suite reports.", "verified": "1 when the recovered key material is verified by the suite."}
    return out


AES = Tool(
    id="suite_aes_reduced", family="Symmetric & hash", title="Reduced-round AES key recovery",
    question="Can the suite's differential / linear machinery recover keys on deliberately weakened (1–2 round) AES?",
    operation="crax --json aes-attack --technique T --samples N",
    params=[Param("technique", "choice", "Technique", "differential", True, choices=("differential", "linear")),
            Param("samples", "int", "Pairs", 4096, min=256, max=65536)],
    build=lambda p: [["aes-attack", "--technique", p["technique"], "--samples", str(p.get("samples", 4096))]],
    parse=_aes_parse,
    limitations=COMMON_LIMITS + ["Attacks a 1–2 round toy instance generated by the suite. Full 10/12/14-round AES is not affected and nothing here is a claim about it."],
    acceptance=["key material recovered and verified"],
    controls=[{"name": "2-round differential", "kind": "positive", "params": {"technique": "differential", "samples": 4096}},
              {"name": "1-round linear", "kind": "positive", "params": {"technique": "linear", "samples": 4096}}],
)


# --------------------------------------------------------------------------- 10: hash known-answer test

def _hash_build(p):
    argv = ["hash", "--algorithm", p["algorithm"]]
    if "hex" in p:
        argv += ["--hex", p["hex"]]
    else:
        argv += ["--text", p.get("text", "")]
    return [argv]


def _hash_parse(p, results):
    code, rep = results[0]
    out = Parsed(raw=rep, failures=_status_failures(rep, ("ok",)))
    dig = str(rep.get("digest_hex", ""))
    exp = p.get("expected_hex")
    if exp:
        out.scenarios = [_scen("hash_kat", f"{p['algorithm']} known-answer test", exp, dig, dig == exp)]
    else:
        out.scenarios = [_scen("hash_computed", f"{p['algorithm']} digest computed", "digest", dig, bool(dig))]
    out.metrics = {"input_bytes": rep.get("input_bytes"), "output_bytes": rep.get("output_bytes"), "kat_match": 1 if exp and dig == exp else 0}
    out.definitions = {"input_bytes": "Bytes hashed.", "output_bytes": "Digest length in bytes.",
                       "kat_match": "1 when the suite digest equals the supplied expected value (an independent implementation cross-check)."}
    return out


HASH = Tool(
    id="suite_hash_kat", family="Symmetric & hash", title="Digest known-answer cross-check",
    question="Does an independent implementation reproduce the digest our pipeline computed (e.g. a firmware manifest hash)?",
    operation="crax --json hash --algorithm A",
    params=[Param("algorithm", "choice", "Algorithm", "sha256", True, choices=HASH_ALGS),
            Param("text", "text", "Input text", "abc", max=65536),
            Param("hex", "hex", "…or input hex (overrides text)", max=65536),
            Param("expected_hex", "hex", "Expected digest (hex)", max=128)],
    build=_hash_build, parse=_hash_parse,
    limitations=COMMON_LIMITS + ["A digest match is an integrity cross-check between two implementations, not evidence of collision resistance."],
    acceptance=["digest equals the expected value"],
    controls=[{"name": "SHA-256('abc') FIPS 180-2 vector", "kind": "positive",
               "params": {"algorithm": "sha256", "text": "abc", "expected_hex": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"}}],
)


# --------------------------------------------------------------------------- 11: dynamic constant-time audit (runner: ct_audit)

CT_TARGETS = ("ctrl_pos_branch", "ctrl_neg_masked", "x25519", "smul_p256", "smul_secp256k1", "smul_sm2_generic",
              "inv_prime_ct", "inv_euclid", "ed25519_sign", "ecdsa_p256_sign", "sm2_sign")

CT_AUDIT = Tool(
    id="sidechannel_ct_audit", family="Side channels", title="Dynamic constant-time audit (Valgrind)",
    question="Does this secret-handling code branch on, index memory by, or vary its instruction count with the secret?",
    operation="valgrind memcheck|callgrind ct_dynamic_audit taint|ir TARGET",
    params=[Param("target", "choice", "Secret-handling path", "x25519", True, choices=CT_TARGETS,
                  help="Entry points of the crypto crate audited in isogeny-labs/crypto PR #3296; ctrl_* are the controls."),
            Param("instrument", "choice", "Instrument", "both", choices=("both", "taint", "ir"),
                  help="taint: Memcheck with the secret marked undefined. ir: Callgrind instruction count per call over four secret classes."),
            Param("expect", "choice", "Expected outcome", "clean", choices=("clean", "leak_detected"))],
    build=lambda p: [], parse=lambda p, r: Parsed(),  # executed by runners/ct_audit_runner.py, not by crax
    runner="ct_audit",
    limitations=[
        "Taint covers one build, 4 calls with independent secrets and Memcheck's model: it does not see conditional moves, cache-line or port effects.",
        "The instruction-count verdict is 'not applicable' when repeating one secret already varies the count (randomness, allocator state).",
        "A clean result is not proof of constant-time behaviour, and no wall-clock timing is measured.",
        "Sites in the harness itself (BigUint conversion of the secret) are reported separately from library sites.",
    ],
    acceptance=["no secret-dependent site and no instruction-count dependence (or, for the positive control, both detected)"],
    controls=[{"name": "Positive control: secret-dependent trip count + secret-indexed load", "kind": "positive",
               "params": {"target": "ctrl_pos_branch", "instrument": "both", "expect": "leak_detected"}},
              {"name": "Negative control: masked fixed-trip arithmetic", "kind": "negative",
               "params": {"target": "ctrl_neg_masked", "instrument": "both", "expect": "clean"}}],
)

TOOLS: dict[str, Tool] = {t.id: t for t in (CURVE_AUDIT, CURVE_ESTIMATE, WEAK_CURVE, ECDSA_AUDIT, RSA_AUDIT, MLWE, RHO, FACTOR, AES, HASH, CT_AUDIT)}
FAMILIES = ("Curves & parameters", "Signatures & keys", "Side channels", "Post-quantum", "Symmetric & hash", "Research demos")


def catalog() -> list[dict]:
    return [t.describe() for t in TOOLS.values()]
