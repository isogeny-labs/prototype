"""Seed users and two demonstration projects. Everything created here is flagged is_demo where it is not a real
measurement. Fixture runs executed during seeding ARE real measurements on the seeding host (provenance=measured);
hardware figures are imported from seeds/hw_*.json and labelled illustrative."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runners import get_runner, RunRequest  # noqa: E402

from .config import SEED_DIR  # noqa: E402
from .db import SessionLocal, init_db  # noqa: E402
from .auth import hash_password  # noqa: E402
from .models import (User, Project, ProjectMember, InventoryItem, Requirement, Implementation, Experiment, ResearchSource,  # noqa: E402
                     AttackAssessment, SandboxExperiment, Task, Approval)
from . import services, audit, catalog  # noqa: E402
from .research import review_source  # noqa: E402
import hashlib  # noqa: E402

DEMO_USERS = [
    ("admin@isogeny.local", "Isogeny Admin", "admin-demo-password", True),
    ("engineer@customer.local", "Customer Engineer", "engineer-demo-password", False),
    ("reviewer@isogeny.local", "Isogeny Reviewer", "reviewer-demo-password", False),
]


def _load(name):
    return json.loads((SEED_DIR / name).read_text())


def _import_inventory(db, project, doc):
    for raw in doc["items"]:
        raw = dict(raw)
        db.add(InventoryItem(project_id=project.id, **raw))
    reqs = [Requirement(project_id=project.id, **r) for r in doc["requirements"]]
    db.add_all(reqs)
    project.platform = doc["platform"]
    db.flush()
    return reqs


def _run_fixture(db, project, exp, impl, actor, extra=None):
    run = services.create_run_record(db, project.id, exp.id, impl.id, "local_fixture", "measured", actor.id)
    result = get_runner("local_fixture").run(services.build_run_request(db, exp, impl, extra))
    services.persist_result(db, run, result, actor.id)
    db.commit()
    return run


def _run_suite(db, project, exp, impl, actor):
    """Run one bounded crax operation when the optional suite binary is connected."""
    runner = get_runner("cryptanalysis_suite")
    available, _ = runner.available()
    if not available:
        return None
    run = services.create_run_record(db, project.id, exp.id, impl.id, runner.kind, runner.provenance, actor.id)
    result = runner.run(services.build_run_request(db, exp, impl))
    services.persist_result(db, run, result, actor.id)
    db.commit()
    return run


def _tool(db, project, impl, actor, tool_id, params=None, name="", control=None):
    """Record and execute one bounded suite tool (or generated control) when the optional suite binary is connected."""
    from runners.suite_tools import TOOLS
    from . import controls, jobs
    from .routers.toolkit import create_tool_run
    runner_kind = TOOLS[controls.GENERATED[control][0] if control else tool_id].runner
    if not get_runner(runner_kind).available()[0]:
        return None
    note = None
    if control:
        tool_id, params, note = controls.generate(control)
    _, run = create_tool_run(db, project, impl, actor, tool_id, params or {}, name, note)
    jobs.process_pending()
    db.expire_all()
    return run


def _tool_preset(db, project, impl, actor, tool_id, index, name=""):
    """Run the static control preset `index` of a suite tool."""
    from runners.suite_tools import TOOLS
    from . import jobs
    from .routers.toolkit import create_tool_run
    if not get_runner(TOOLS[tool_id].runner).available()[0]:
        return None
    c = TOOLS[tool_id].controls[index]
    note = {"control": f"{tool_id}:{index}", "kind": c["kind"], "name": c["name"], "source": "static preset in runners/suite_tools.py"}
    _, run = create_tool_run(db, project, impl, actor, tool_id, c["params"], name, note)
    jobs.process_pending()
    db.expire_all()
    return run


def _import_run(db, project, exp, impl, actor, doc, illustrative=True):
    run = services.create_run_record(db, project.id, exp.id, impl.id, "import", "imported", actor.id)
    doc = dict(doc)
    doc.setdefault("environment", {})["imported_by"] = actor.email
    result = get_runner("import").run(RunRequest(fixture=exp.fixture, params={"document": doc, "illustrative": illustrative}, implementation={}, experiment={}))
    services.persist_result(db, run, result, actor.id)
    db.commit()
    return run


def _source(db, project, actor, title, path):
    text = (SEED_DIR / "research_docs" / path).read_text()
    src = ResearchSource(project_id=project.id, title=title, content=text, content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                         source_type="document", is_demo=True, submitted_by=actor.id)
    db.add(src)
    db.flush()
    f = review_source(db, src)
    db.commit()
    return src, f


def seed_iot(db, admin, engineer, reviewer):
    doc = _load("iot_inventory.json")
    p = Project(name="FG-200 Field Gateway — firmware signing", kind="iot", is_demo=True, created_by=admin.id,
                business_purpose="Industrial LTE-M gateway; firmware updates must be authenticated for the whole 12-year support period.",
                deployment_environment="Field-deployed, unattended, OTA updates over LTE-M; devices shipped since 2024.",
                support_period_end="2038-12-31",
                data_protection_requirements="Telemetry confidentiality; firmware integrity and authenticity; no customer PII on device.",
                update_process="Release engineering signs images with an offline HSM; OTA via MQTT; A/B slot with rollback protection.")
    db.add(p)
    db.flush()
    db.add_all([ProjectMember(project_id=p.id, user_id=engineer.id, role="editor"), ProjectMember(project_id=p.id, user_id=reviewer.id, role="reviewer")])
    _import_inventory(db, p, doc)
    base = Implementation(project_id=p.id, name="Bootloader verifier", version="2.3.0", role="baseline", status="approved",
                          profile_id="rsa2048_pkcs1v15_sha256", algorithm=catalog.profile("rsa2048_pkcs1v15_sha256")["label"],
                          library="mbedTLS", library_version="2.16.12", source_revision="fw-2.3.0 @ a1b2c3d",
                          configuration={"manifest_format": "iel-fw-manifest/1"}, target_environment={"board": "FG-200 EVT2", "mcu": "STM32F407"},
                          build_identity={"toolchain": "arm-none-eabi-gcc 12.3"}, delivery_mode="customer_lab", created_by=engineer.id,
                          notes="Current production verifier.")
    cand = Implementation(project_id=p.id, name="Bootloader verifier", version="3.0.0-rc1", role="candidate", status="approved",
                          profile_id="ml_dsa_65", algorithm=catalog.profile("ml_dsa_65")["label"], library="pqm4", library_version="2025-03 snapshot",
                          source_revision="fw-3.0.0-rc1 @ 9f8e7d6", configuration={"manifest_format": "iel-fw-manifest/1"},
                          target_environment={"board": "FG-200 EVT2", "mcu": "STM32F407"}, build_identity={"toolchain": "arm-none-eabi-gcc 12.3"},
                          delivery_mode="customer_lab", parent_id=None, created_by=engineer.id,
                          notes="First post-quantum candidate. Approved for lab evaluation only.")
    db.add_all([base, cand])
    db.flush()
    from .routers.implementations import compute_warnings
    for i in (base, cand):
        i.compatibility_warnings = compute_warnings(p, i)
    cand.parent_id = base.id
    db.add_all([Task(project_id=p.id, implementation_id=cand.id, title="Port pqm4 ML-DSA-65 verify into bootloader", owner="engineer@customer.local", status="done"),
                Task(project_id=p.id, implementation_id=cand.id, title="Measure verify stack high-water mark on EVT2", owner="lab@customer.local", status="done"),
                Task(project_id=p.id, implementation_id=cand.id, title="Decide manifest slot layout for >2.5 KB signatures", owner="engineer@customer.local", status="blocked")])
    fx = Experiment(project_id=p.id, name="Firmware update acceptance & rejection (reference fixture)", fixture="firmware_signing",
                    definition={"params": {"image_bytes": 262144, "repeat_count": 30, "installed_version": 4, "update_version": 5},
                                "scenarios": "valid, tampered image, wrong key, truncated/empty/corrupted signature, rollback, manifest swap, malformed manifest, bad header, length mismatch"},
                    acceptance_criteria=["all scenarios observe expected result", "project requirements with applies_to in (all, measured)"],
                    description="Host-side reference verifier. Produces real correctness evidence and host timing; device timing must be imported.")
    hw = Experiment(project_id=p.id, name="Device-lab measurements (imported)", fixture="external",
                    definition={"protocol": "device-lab-protocol/0.3", "board": "FG-200 EVT2"},
                    acceptance_criteria=["project requirements with applies_to in (all, imported)"],
                    description="Import of externally produced on-device results. Seeded numbers are ILLUSTRATIVE.")
    db.add_all([fx, hw])
    db.flush()
    r1 = _run_fixture(db, p, fx, base, engineer)
    r2 = _run_fixture(db, p, fx, cand, engineer)          # fails: signature 3309 B > 2560 B slot -> opens measurement finding
    r3 = _import_run(db, p, hw, base, engineer, _load("hw_baseline_rsa2048.json"))
    r4 = _import_run(db, p, hw, cand, engineer, _load("hw_candidate_mldsa65.json"))  # also fails stack + slot
    # --- cryptanalysis-suite toolkit (only when crax is connected): key hygiene, lattice margins, digest cross-check
    _tool(db, p, base, engineer, None, name="Fleet signing-key hygiene: RSA-2048 public keys (negative control)", control="rsa_real_keys")
    _tool(db, p, base, engineer, None, name="Control: planted shared-prime and close-prime moduli (positive)", control="rsa_weak_moduli")
    _tool(db, p, base, engineer, None, name="Control: planted small private exponent (positive, Wiener)", control="rsa_wiener")
    _tool(db, p, cand, engineer, "suite_mlwe_estimate", {"scheme": "ml-dsa-65", "model": "gate-count", "tours": True},
          name="ML-DSA-65 lattice key-recovery estimate (gate-count + BKZ tours)")
    _tool(db, p, cand, engineer, "suite_mlwe_estimate", {"scheme": "ml-dsa-44", "model": "gate-count", "tours": True},
          name="ML-DSA-44 lattice key-recovery estimate (smaller-signature alternative)")
    _tool(db, p, cand, engineer, None, name="Manifest digest cross-check: suite SHA-256 vs build hashlib", control="firmware_digest")
    _source(db, p, engineer, "Draft PQC transition timeline (paraphrase, demonstration)", "pqc_transition_guidance.txt")
    _source(db, p, engineer, "PKCS#1 v1.5 lenient-parser class of bugs (paraphrase, demonstration)", "pkcs1v15_parser_bugs.txt")
    # --- attack-cost view (classical/quantum separated; C = published, D = unknown)
    db.add_all([
        AttackAssessment(project_id=p.id, category="C", attack_model="classical", target="RSA-2048 (firmware signing key)",
                         target_parameters={"modulus_bits": 2048}, objective="Recover the private key by factoring the modulus.",
                         attacker_capabilities="Nation-state-scale classical compute.", method="General Number Field Sieve (GNFS).",
                         source="Public factoring record: RSA-250 (829-bit), Boudot et al., Feb 2020, reported ~2700 core-years (2.1 GHz Xeon Gold 6130). No public factorisation of any 2048-bit RSA modulus.",
                         hardware_assumptions="Commodity x86 cores as in the published record.",
                         expected_work={"value": None, "unit": "", "log2": None, "estimation_method": "Published record + GNFS asymptotic L[1/3, 1.923]; absolute effort for 2048 bits is not defensibly quantified here."},
                         uncertainty="GNFS constants are not known precisely for 2048-bit inputs; any single number would be fabricated.",
                         applicability_limits="Says that classical factoring of RSA-2048 is far beyond the public record; does not provide a cost figure.", is_demo=True),
        AttackAssessment(project_id=p.id, category="C", attack_model="quantum", target="RSA-2048 (firmware signing key)",
                         target_parameters={"modulus_bits": 2048}, objective="Recover the private key with Shor's algorithm.",
                         attacker_capabilities="Hypothetical large fault-tolerant quantum computer.", method="Shor's algorithm with surface-code error correction.",
                         source="Gidney & Ekerå (2019/2021): ~20 million noisy qubits, ~8 hours. Gidney (2025): under one million noisy qubits, under one week, assuming 0.1% gate error. Published estimates; not demonstrated.",
                         hardware_assumptions="Physical qubit counts and error rates far beyond any publicly reported device.",
                         expected_work={"value": None, "unit": "", "log2": None, "estimation_method": "Published resource estimates (qubits x time); no calendar date is asserted."},
                         uncertainty="Estimates have moved by >10x in six years; hardware progress is not predictable here.",
                         applicability_limits="Classical and quantum models are separate; this record says nothing about classical cost.", is_demo=True),
        AttackAssessment(project_id=p.id, category="C", attack_model="classical", target="ML-DSA-65 (candidate firmware signing)",
                         target_parameters={"parameter_set": "ML-DSA-65"}, objective="Forge a signature or recover the key.",
                         attacker_capabilities="Best known lattice attacks (BKZ/sieving).", method="Core-SVP lattice reduction estimates.",
                         source="FIPS 204 security category 3 (comparable to exhaustive search of AES-192) per NIST's categorisation; underlying estimates in the Dilithium specification.",
                         hardware_assumptions="Idealised sieving cost model.",
                         expected_work={"value": None, "unit": "", "log2": None, "estimation_method": "Published category claim only."},
                         uncertainty="Lattice cost models remain under active research; the category is a design target, not a measurement.",
                         applicability_limits="Does not address implementation attacks (side channels, fault injection) on the device.", is_demo=True),
        AttackAssessment(project_id=p.id, category="D", attack_model="quantum", target="ML-DSA-65 (candidate firmware signing)",
                         target_parameters={"parameter_set": "ML-DSA-65"}, objective="Quantum key recovery / forgery.",
                         attacker_capabilities="Hypothetical quantum adversary.", method="No known quantum attack materially better than classical lattice attacks.",
                         source="No defensible quantitative estimate available beyond the FIPS 204 category claim.",
                         expected_work=None, uncertainty="Unknown.", applicability_limits="Displayed as 'No defensible estimate available'.", is_demo=True),
        AttackAssessment(project_id=p.id, category="D", attack_model="classical", target="mbedTLS 2.16.12 RSA PKCS#1 v1.5 verifier (implementation)",
                         target_parameters={"library": "mbedTLS", "version": "2.16.12"}, objective="Accept a forged signature via lenient parsing.",
                         attacker_capabilities="Can submit arbitrary update packages.", method="Malformed-padding forgery class; requires a specific parser bug.",
                         source="Research finding in inbox (demonstration). No measured or published estimate for this exact build.",
                         expected_work=None, uncertainty="Depends entirely on whether the specific build has a parser bug; test with the fixture's malformed-input scenarios.",
                         applicability_limits="Not an algorithm weakness; an implementation question.", is_demo=True),
    ])
    sx = SandboxExperiment(project_id=p.id, title="Toy Pollard-rho factoring run (workflow demonstration)", kind="hypothesis",
                           hypothesis="Measured iteration counts follow the sqrt(pi*p/2) birthday heuristic for small synthetic semiprimes.",
                           method="Run the allowlisted toy_factoring fixture on 44-bit synthetic moduli, 5 trials.",
                           allowlisted_fixture="toy_factoring", parameters={"modulus_bits": 44, "trials": 5, "max_iterations": 2000000, "seed": 11},
                           target_class="synthetic", resource_limits={"timeout_s": 60, "memory_mb": 256, "cpu_s": 45}, proposed_by="auto-researcher (seeded)")
    db.add_all([sx,
                SandboxExperiment(project_id=p.id, title="Reproduce published PKCS#1 v1.5 lenient-parser forgery against the baseline verifier build", kind="reproduction",
                                  hypothesis="The mbedTLS 2.16.12 build in fw-2.3.0 rejects all malformed-padding forgeries.",
                                  method="Requires the customer's actual verifier binary and a harness; no allowlisted fixture exists, so this is a proposal only.",
                                  allowlisted_fixture=None, parameters={}, target_class="owned", proposed_by="auto-researcher (seeded)")])
    db.commit()
    # Execute the approved toy experiment synchronously so the attack-cost view has a measured (category A) entry.
    db.add(Approval(project_id=p.id, subject_type="sandbox_experiment", subject_id=sx.id, decision="approved", reviewer_id=reviewer.id,
                    note="Seeded approval of the bounded toy experiment."))
    sx.status = "approved"
    impl = Implementation(project_id=p.id, name="Sandbox synthetic target", version="n/a", role="candidate", status="retired",
                          algorithm="synthetic toy parameters", notes="Placeholder target for research-only sandbox runs.", created_by=admin.id)
    exp = Experiment(project_id=p.id, name="Sandbox: toy Pollard-rho factoring (research only)", fixture="toy_factoring", definition={"sandbox": True},
                     description="Research-only sandbox experiment; not part of product assurance.")
    db.add_all([impl, exp])
    db.flush()
    run = services.create_run_record(db, p.id, exp.id, impl.id, "local_fixture", "measured", admin.id)
    db.commit()
    services._job_sandbox_execute(db, {"sandbox_id": sx.id, "run_id": run.id, "actor_id": admin.id})
    return p


def seed_app(db, admin, engineer, reviewer):
    doc = _load("app_inventory.json")
    p = Project(name="Payments token-service (containerised)", kind="application", is_demo=True, created_by=admin.id,
                business_purpose="Issues short-lived API tokens for a payments platform.",
                deployment_environment="Kubernetes, 6 replicas, python:3.13-slim image.", support_period_end="2032-06-30",
                data_protection_requirements="PCI-DSS scope; tokens must not be forgeable; p95 latency SLO 2 ms for verify.",
                update_process="CI builds image; Helm staged rollout; crypto configuration changes require change-board approval.")
    db.add(p)
    db.flush()
    db.add_all([ProjectMember(project_id=p.id, user_id=engineer.id, role="editor"), ProjectMember(project_id=p.id, user_id=reviewer.id, role="reviewer")])
    _import_inventory(db, p, doc)
    base = Implementation(project_id=p.id, name="token-service", version="1.4.2", role="baseline", status="approved", profile_id="jws_rs256",
                          algorithm=catalog.profile("jws_rs256")["label"], library="PyJWT + cryptography", library_version="2.8.0 / 42.0.5",
                          source_revision="git 4c0ffee", configuration={"alg": "RS256", "fixture_params": {"payload_bytes": 256}},
                          target_environment={"image": "python:3.13-slim", "cpu": "x86-64"}, build_identity={"image_digest": "sha256:(recorded at build)"},
                          delivery_mode="container", created_by=engineer.id)
    curve_candidate = Implementation(
        project_id=p.id,
        name="token-service",
        version="2.0.0-es256-analysis",
        role="candidate",
        status="draft",
        profile_id="jws_es256",
        algorithm=catalog.profile("jws_es256")["label"],
        library="target library not yet selected",
        source_revision="design-stage curve review",
        configuration={"alg": "ES256", "suite_curve": "p256"},
        target_environment={"image": "python:3.13-slim", "cpu": "x86-64"},
        build_identity={"status": "not built; suite analysis only"},
        delivery_mode="container",
        parent_id=None,
        created_by=engineer.id,
        notes="Design-stage candidate used to demonstrate the bounded cryptanalysis-suite integration. No deployment is implied.",
    )
    db.add_all([base, curve_candidate])
    db.flush()
    curve_candidate.parent_id = base.id
    fx = Experiment(project_id=p.id, name="Token signing correctness & performance regression (container fixture)", fixture="app_service_crypto",
                    definition={"params": {"repeat_count": 150, "payload_bytes": 256}},
                    acceptance_criteria=["all scenarios pass", "project requirements"],
                    description="Runs app_service_crypto in the process-isolated runner (or Docker runner when a daemon is available).")
    suite_audit = Experiment(
        project_id=p.id,
        name="Suite audit: P-256 catalog parameters",
        fixture="suite_curve_audit",
        definition={"params": {"curve": "p256"}, "contract": "crax --json icx inspect"},
        acceptance_criteria=["every suite parameter check passes", "suite_verified == 1"],
        description="Runs the cryptanalysis suite's bounded, machine-readable curve inspection. This checks catalog parameters, not application code.",
    )
    suite_estimate = Experiment(
        project_id=p.id,
        name="Suite estimate: P-256 generic and index-calculus picture",
        fixture="suite_curve_estimate",
        definition={"params": {"curve": "p256", "envelope_bits": 64}, "contract": "crax --json icx estimate"},
        acceptance_criteria=["suite report completes", "result remains labelled as an operation-count model"],
        description="Records the suite's generic Pollard-rho and index-calculus classification. It is not a wall-clock forecast or practical-break claim.",
    )
    db.add_all([fx, suite_audit, suite_estimate])
    db.flush()
    _run_fixture(db, p, fx, base, engineer)  # RS256 sign throughput typically < 2000/s -> requirement failure -> finding
    _run_suite(db, p, suite_audit, curve_candidate, engineer)
    _run_suite(db, p, suite_estimate, curve_candidate, engineer)
    _tool_preset(db, p, curve_candidate, engineer, "suite_weak_curve", 0, "P-256 structural weak-curve analysis (negative control)")
    _tool_preset(db, p, curve_candidate, engineer, "suite_weak_curve", 2, "Control: anomalous toy curve, Smart attack (positive)")
    _tool(db, p, curve_candidate, engineer, None, name="ES256 signature-transcript audit: 32 real signatures, full lattice sweep", control="es256_transcript")
    _tool_preset(db, p, curve_candidate, engineer, "suite_ecdsa_audit", 0, "Control: planted 192-bit nonce bias (positive)")
    _source(db, p, engineer, "JWS algorithm guidance for RS256 deployments (paraphrase, demonstration)", "jws_alg_guidance.txt")
    db.add(AttackAssessment(project_id=p.id, category="D", attack_model="classical", target="RS256 token forgery via algorithm confusion (implementation)",
                            target_parameters={"library": "PyJWT", "version": "2.8.0"}, objective="Have the verifier accept a token under an unintended algorithm.",
                            attacker_capabilities="Can present arbitrary tokens.", method="alg header confusion; only possible if the verifier does not pin algorithms.",
                            source="Research inbox (demonstration).", expected_work=None,
                            uncertainty="Configuration-dependent; verify by code review and the fixture's rejection scenarios.",
                            applicability_limits="Not a cryptanalytic cost; an integration check.", is_demo=True))
    db.commit()
    return p


def seed_ct_audit(db, p, engineer):
    """Side-channel evidence for the crypto crate: the frozen run of isogeny-labs/crypto #3296 imported (always), plus
    live controls and two targets when the ct_dynamic_audit binary and Valgrind are available."""
    from runners.ct_audit_runner import METRIC_DEFINITIONS, map_entry
    from runners.suite_tools import TOOLS
    snap = _load("ct_audit_snapshot.json")
    src = snap["source"]
    impl = Implementation(project_id=p.id, name="crypto crate: secret-handling paths", version=src["run_commit"][:9], role="baseline",
                          status="approved", algorithm="ECDSA, SM2, Ed25519, X25519 and scalar multiplication (isogeny-labs/crypto)",
                          library="isogeny-labs/crypto crypto_lib", library_version=src["run_commit"],
                          source_revision=f"{src['repository']}@{src['run_commit'][:12]}", configuration={},
                          target_environment={"build": "release, line tables", "instrument": "Valgrind 3.22"},
                          build_identity={"card": src["card_id"]}, delivery_mode="container", created_by=engineer.id,
                          notes="Audited with the dynamic constant-time harness of crypto PR #3296; results also imported from that run.")
    db.add(impl)
    db.flush()
    tool = TOOLS["sidechannel_ct_audit"]
    for e in snap["targets"]:
        expect = "leak_detected" if e["target"] == "ctrl_pos_branch" else "clean"
        mapped = map_entry(e, "both", expect)
        exp = Experiment(project_id=p.id, name=f"Side-channel audit: {e['target']} (imported, crypto #3296)", fixture="sidechannel_ct_audit",
                         definition={"params": {"target": e["target"], "instrument": "both", "expect": expect}, "tool": tool.id,
                                     "contract": tool.operation, "imported_from": src},
                         acceptance_criteria=tool.acceptance, description=e.get("description", tool.question))
        db.add(exp)
        db.flush()
        _import_run(db, p, exp, impl, engineer, {
            "fixture": "sidechannel_ct_audit", "fixture_version": f"ct_dynamic_audit@{src['run_commit'][:12]}", "status": "completed",
            "metrics": mapped["metrics"], "metric_definitions": METRIC_DEFINITIONS, "scenarios": mapped["scenarios"],
            "environment": {"measured_by": f"{src['repository']} task card {src['card_id']}", "summary_sha256": src["summary_sha256"],
                            "receipt_sha256": src["receipt_sha256"], "report": src["report"], "pull_request": src["pull_request"]},
            "limitations": snap["limitations"], "repeat_count": 1, "raw_summary_entry": e}, illustrative=False)
    if get_runner("ct_audit").available()[0]:
        _tool_preset(db, p, impl, engineer, "sidechannel_ct_audit", 0)
        _tool_preset(db, p, impl, engineer, "sidechannel_ct_audit", 1)
        _tool(db, p, impl, engineer, "sidechannel_ct_audit", {"target": "x25519"}, "Side-channel audit (live): x25519")
        _tool(db, p, impl, engineer, "sidechannel_ct_audit", {"target": "inv_euclid", "instrument": "taint"},
              "Side-channel audit (live): SM2 private-key inverse, taint only")


def seed_showcase(db, admin, engineer, reviewer):
    """A research-facing project that exercises every suite tool family once, with its controls."""
    p = Project(name="Isogeny Labs cryptanalysis suite — showcase", kind="application", is_demo=True, created_by=admin.id,
                business_purpose="Demonstrates the bounded crax toolkit end to end: every tool family, its controls, and the evidence each run leaves.",
                deployment_environment="Research workstation; no customer system is involved.", support_period_end="2030-12-31",
                data_protection_requirements="None: every target here is public, synthetic or a toy instance.",
                update_process="Suite revision pinned in .github/workflows/pages.yml; bumping it is a reviewed source change.")
    db.add(p)
    db.flush()
    db.add_all([ProjectMember(project_id=p.id, user_id=engineer.id, role="editor"), ProjectMember(project_id=p.id, user_id=reviewer.id, role="reviewer")])
    suite = Implementation(project_id=p.id, name="crax cryptanalysis suite", version="pinned build", role="baseline", status="approved",
                           algorithm="Isogeny Labs cryptanalysis toolkit (Rust suite)", library="isogeny-labs/cryptanalysis suite/",
                           library_version="see each run's suite_version and binary SHA-256", source_revision="pinned in .github/workflows/pages.yml",
                           configuration={}, target_environment={"host": "seeding host"}, build_identity={"cargo": "--release --locked"},
                           delivery_mode="container", created_by=engineer.id,
                           notes="Each run records the exact binary hash; the static demo pins the suite revision.")
    db.add(suite)
    db.flush()
    _tool_preset(db, p, suite, engineer, "suite_curve_audit", 0)
    _tool(db, p, suite, engineer, "suite_curve_audit", {"curve": "secp256k1"}, "Curve parameter audit: secp256k1")
    _tool_preset(db, p, suite, engineer, "suite_curve_estimate", 0)
    _tool_preset(db, p, suite, engineer, "suite_weak_curve", 1)
    _tool_preset(db, p, suite, engineer, "suite_weak_curve", 3)
    _tool_preset(db, p, suite, engineer, "suite_mlwe_estimate", 1)
    _tool(db, p, suite, engineer, "suite_mlwe_estimate", {"scheme": "ml-kem-768", "model": "gate-count", "tours": True}, "ML-KEM-768 lattice estimate")
    _tool_preset(db, p, suite, engineer, "suite_generic_rho", 0, "Pollard rho, generic-26 toy curve, seed 1")
    _tool(db, p, suite, engineer, "suite_generic_rho", {"curve": "generic-26", "secret": "123456", "negation": True, "seed": 2},
          "Pollard rho, generic-26 toy curve, seed 2")
    _tool(db, p, suite, engineer, "suite_generic_rho", {"curve": "generic-26", "secret": "123456", "negation": False, "seed": 1},
          "Pollard rho, generic-26 toy curve, no negation map")
    _tool_preset(db, p, suite, engineer, "suite_factor_toy", 0)
    _tool_preset(db, p, suite, engineer, "suite_aes_reduced", 0)
    _tool_preset(db, p, suite, engineer, "suite_aes_reduced", 1)
    _tool_preset(db, p, suite, engineer, "suite_hash_kat", 0)
    seed_ct_audit(db, p, engineer)
    db.commit()
    return p


def ensure_seed():
    init_db()
    if os.environ.get("IEL_SKIP_SEED") == "1":
        return
    with SessionLocal() as db:
        if db.scalar(select(User)):
            return
        users = {}
        for email, name, pw, admin in DEMO_USERS:
            u = User(email=email, name=name, password_hash=hash_password(pw), is_admin=admin)
            db.add(u)
            users[email] = u
        db.flush()
        admin, eng, rev = users["admin@isogeny.local"], users["engineer@customer.local"], users["reviewer@isogeny.local"]
        p1 = seed_iot(db, admin, eng, rev)
        p2 = seed_app(db, admin, eng, rev)
        p3 = seed_showcase(db, admin, eng, rev)
        audit.record(db, admin.id, "seed.completed", "system", None, None, {"projects": [p1.id, p2.id, p3.id]}, commit=True)
        print(f"seeded demo projects: {p1.name} | {p2.name} | {p3.name}")


if __name__ == "__main__":
    ensure_seed()
