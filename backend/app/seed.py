"""Seed demo users and the SAMPLE project, walking the full loop with real executions:
import 1.0.0 (seeded, labelled defect) -> sandbox run fails -> research source -> experiment proposed/approved/executed
-> recommendation -> import 1.1.0 -> retest passes -> customer-runner bundle imported (real runner, demo key).
Everything created here is flagged is_demo; fixture executions are real measurements on the seeding host."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from iel_tools import attest  # noqa: E402

from .config import SEED_DIR, DATA_DIR  # noqa: E402
from .db import SessionLocal, init_db  # noqa: E402
from .auth import hash_password  # noqa: E402
from .models import (User, Project, ProjectMember, Requirement, Implementation, TestDefinition, ResearchSource, AttackAssessment, TrustedKey,  # noqa: E402
                     Finding, ExperimentProposal, ProtocolVersion, Approval, Recommendation, Run, utcnow)
from . import services, audit, signing, compat  # noqa: E402
from . import artifacts as artstore  # noqa: E402
from .research import review_source, propose_experiments  # noqa: E402
from .recommend import recommendation_for_finding  # noqa: E402
from runners import get_runner  # noqa: E402

DEMO_USERS = [("admin@isogeny.local", "Isogeny Admin", "admin-demo-password", True),
              ("engineer@customer.local", "Customer Engineer", "engineer-demo-password", False),
              ("reviewer@isogeny.local", "Isogeny Reviewer", "reviewer-demo-password", False)]


def default_test_definitions(project_id: str) -> list[TestDefinition]:
    return [TestDefinition(project_id=project_id, test_id="signature-library-core", version="1", name="Signature library: correctness, malformed input, vectors, performance",
                           fixture="signature_library", definition={"params": {"repeat_count": 100, "message_bytes": 1024, "seed": 1}},
                           acceptance_criteria=["valid signatures accepted (valid_signature, second_message)", "modified message / wrong key / random / corrupted / truncated / "
                                                "trailing / empty / zero signatures rejected", "official test vector verifies and reproduces where bundled",
                                                "project requirements with applies_to in (all, measured)"],
                           resource_limits={"timeout_s": 300, "memory_mb": 1024, "cpu_s": 240},
                           description="Library-level digital-signature test. Not a firmware-update or payment-protocol validation."),
            TestDefinition(project_id=project_id, test_id="malformed-input-sweep", version="1", name="Experiment: malformed-signature encoding sweep",
                           fixture="malformed_input_sweep", definition={"params": {"max_extra_bytes": 64, "seed": 3}},
                           acceptance_criteria=["per approved experiment protocol"], resource_limits={"timeout_s": 120, "memory_mb": 512, "cpu_s": 90},
                           description="Allowlisted experiment fixture used by the autoresearcher; runs only with an approved protocol.")]


def _import(db, project, manifest_path, adapter_path, user, parent=None, recommendation=None, seeded_defect=""):
    m = json.loads(Path(manifest_path).read_text())
    data = Path(adapter_path).read_bytes()
    files = compat.extract_snapshot(data, "adapter.py")
    report = compat.check_snapshot(files)
    art = artstore.store(db, project.id, "source_snapshot", Path(adapter_path).name, data, "text/x-python", label=f"source snapshot {m['name']} {m['version']}")
    impl = Implementation(project_id=project.id, created_by=user.id, status="imported", manifest=m, is_demo=True, seeded_defect=seeded_defect,
                          source_snapshot_artifact_id=art.id, source_digest=art.sha256, compatibility=report, parent_id=parent.id if parent else None,
                          recommendation_id=recommendation.id if recommendation else None,
                          **{k: m[k] for k in ("name", "version", "purpose", "algorithm", "parameters", "library", "library_version", "dependencies", "configuration",
                                               "runtime_environment", "source_revision", "build_identity", "intended_use", "threat_assumptions", "adapter_kind", "notes") if k in m},
                          change_report=m.get("change_report", ""))
    db.add(impl)
    db.flush()
    from .models import InventoryItem
    db.add_all([InventoryItem(project_id=project.id, implementation_id=impl.id, category="algorithm", name=impl.algorithm, purpose="signatures", parameters=impl.parameters,
                              provenance="user_reported", provenance_detail="declared in the import manifest"),
                InventoryItem(project_id=project.id, implementation_id=impl.id, category="library", name=impl.library, version=impl.library_version, purpose="signatures",
                              provenance="user_reported", provenance_detail="declared in the import manifest"),
                InventoryItem(project_id=project.id, implementation_id=impl.id, category="key_handling", name="Signing keys held in KMS; verifiers hold public keys", purpose="signatures",
                              provenance="user_reported", provenance_detail="manifest threat_assumptions")])
    if parent:
        parent.status = "superseded"
    db.flush()
    audit.record(db, user.id, "implementation.imported", "implementation", impl.id, project.id, {"version": impl.version, "compatibility": report["status"]})
    return impl


def _run(db, project, test, impl, user):
    run = services.create_run_record(db, project.id, test.id, impl.id, "platform_sandbox", "platform_sandbox", "measured", user.id)
    res = get_runner("platform_sandbox").run(services.build_run_request(db, test, impl))
    services.persist_result(db, run, res, user.id)
    db.commit()
    return run


def _customer_bundle(project_id: str, impl_name: str, impl_version: str, adapter_path: str, key_path: Path) -> dict:
    out = Path(tempfile.mkdtemp(prefix="iel-seed-")) / "bundle.json"
    subprocess.run([sys.executable, str(ROOT / "iel_tools" / "runner.py"), "run", "--project", project_id, "--impl-name", impl_name, "--impl-version", impl_version,
                    "--adapter", adapter_path, "--key", str(key_path), "--out", str(out), "--params", json.dumps({"repeat_count": 60}), "--fixture-dir", str(ROOT / "backend" / "fixtures"),
                    "--source-revision", "git 7a1f2c9 (sample)"], check=True, capture_output=True, timeout=600)
    return json.loads(out.read_text())


def _tool(db, project, impl, actor, tool_id, params=None, name="", control=None):
    """Record and execute one bounded tool (or generated control) when that tool's optional runner is connected."""
    from runners.suite_tools import TOOLS
    from . import controls, jobs
    from .routers.toolkit import create_tool_run
    if not get_runner(TOOLS[controls.GENERATED[control][0] if control else tool_id].runner).available()[0]:
        return None
    note = None
    if control:
        tool_id, params, note = controls.generate(control)
    _, run = create_tool_run(db, project, impl, actor, tool_id, params or {}, name, note)
    jobs.process_pending()
    db.expire_all()
    return run


def _tool_preset(db, project, impl, actor, tool_id, index, name=""):
    """Run the static control preset `index` of a tool (when that tool's runner is connected)."""
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


def seed_toolkit_controls(db, admin, eng, rev):
    """Demonstration project exercising every suite tool family once with its controls. Created only when `crax` is connected."""
    if not get_runner("cryptanalysis_suite").available()[0]:
        return None
    p = Project(name="Cryptanalysis toolkit controls (demonstration)", workflow="signature_library", is_demo=True, created_by=admin.id,
                description="Exercises every bounded crax tool family with its negative and positive controls, so the detectors can be seen working. Not a customer system.",
                intended_use="Research-facing demonstration only.", threat_assumptions="Every target is public, synthetic or a toy instance.",
                runtime_environment={"deployment": "seeding host"})
    db.add(p)
    db.flush()
    db.add_all([ProjectMember(project_id=p.id, user_id=eng.id, role="editor"), ProjectMember(project_id=p.id, user_id=rev.id, role="reviewer")])
    db.add_all(default_test_definitions(p.id))
    suite = Implementation(project_id=p.id, name="crax cryptanalysis suite", version="pinned build", status="imported", adapter_kind="results_only",
                           algorithm="Isogeny Labs cryptanalysis toolkit (Rust suite)", library="isogeny-labs/cryptanalysis suite/",
                           library_version="see each run's suite_version and binary SHA-256", source_revision="pinned in .github/workflows/pages.yml",
                           build_identity={"cargo": "--release --locked"}, is_demo=True, created_by=eng.id,
                           compatibility={"status": "unsupported", "report": ["subject of toolkit runs only; no adapter"], "problems": [], "warnings": []},
                           notes="Subject record for toolkit control runs; each run records the exact binary hash.")
    db.add(suite)
    db.flush()
    _tool_preset(db, p, suite, eng, "suite_curve_audit", 0)
    _tool(db, p, suite, eng, "suite_curve_audit", {"curve": "secp256k1"}, "Curve parameter audit: secp256k1")
    _tool_preset(db, p, suite, eng, "suite_curve_estimate", 0)
    _tool_preset(db, p, suite, eng, "suite_weak_curve", 1)
    _tool_preset(db, p, suite, eng, "suite_weak_curve", 3)
    _tool_preset(db, p, suite, eng, "suite_mlwe_estimate", 1)
    _tool(db, p, suite, eng, "suite_mlwe_estimate", {"scheme": "ml-kem-768", "model": "gate-count", "tours": True}, "ML-KEM-768 lattice estimate")
    _tool_preset(db, p, suite, eng, "suite_generic_rho", 0, "Pollard rho, generic-26 toy curve, seed 1")
    _tool(db, p, suite, eng, "suite_generic_rho", {"curve": "generic-26", "secret": "123456", "negation": False, "seed": 1}, "Pollard rho, generic-26 toy curve, no negation map")
    _tool_preset(db, p, suite, eng, "suite_factor_toy", 0)
    _tool_preset(db, p, suite, eng, "suite_aes_reduced", 0)
    _tool_preset(db, p, suite, eng, "suite_aes_reduced", 1)
    _tool_preset(db, p, suite, eng, "suite_hash_kat", 0)
    db.commit()
    return p


def seed_ct_audit(db, admin, eng, rev):
    """Side-channel evidence for the isogeny-labs/crypto crate. The frozen run of crypto PR #3296 is always imported
    (unsigned, provenance `imported`); when the ct_dynamic_audit binary and Valgrind are connected, both controls and
    two targets are also run live as measured platform runs."""
    from runners.ct_audit_runner import METRIC_DEFINITIONS, map_entry
    from runners.suite_tools import TOOLS
    from .routers.tests import _import_results_doc
    from .routers.toolkit import tool_test_definition
    snap = json.loads((SEED_DIR / "ct_audit_snapshot.json").read_text())
    src = snap["source"]
    p = Project(name="Side-channel audit: crypto crate (demonstration)", workflow="signature_library", is_demo=True, created_by=admin.id,
                description="Dynamic constant-time audit (Valgrind taint and instruction counts) of the secret-handling paths in the "
                            "isogeny-labs/crypto crate, imported from the frozen run of crypto PR #3296. Not a customer system.",
                intended_use="Research-facing demonstration of the side-channel tool and its evidence.",
                threat_assumptions="Timing and secret-dependent control flow or memory access only; power, EM and fault channels are out of scope.",
                runtime_environment={"instrument": "Valgrind (Memcheck taint, Callgrind)"})
    db.add(p)
    db.flush()
    db.add_all([ProjectMember(project_id=p.id, user_id=eng.id, role="editor"), ProjectMember(project_id=p.id, user_id=rev.id, role="reviewer")])
    impl = Implementation(project_id=p.id, name="crypto crate: secret-handling paths", version=src["run_commit"][:9], status="imported", adapter_kind="results_only",
                          algorithm="ECDSA, SM2, Ed25519, X25519 and scalar multiplication (isogeny-labs/crypto)", library="isogeny-labs/crypto crypto_lib",
                          library_version=src["run_commit"], source_revision=f"{src['repository']}@{src['run_commit'][:12]}",
                          build_identity={"build": "release, line tables", "card": src["card_id"]}, is_demo=True, created_by=eng.id,
                          compatibility={"status": "unsupported", "report": ["subject of side-channel tool runs only; no adapter"], "problems": [], "warnings": []},
                          notes="Audited with the dynamic constant-time harness of crypto PR #3296.")
    db.add(impl)
    db.flush()
    tool = TOOLS["sidechannel_ct_audit"]
    test = tool_test_definition(db, p, tool)
    for e in snap["targets"]:
        expect = "leak_detected" if e["target"] == "ctrl_pos_branch" else "clean"
        mapped = map_entry(e, "both", expect)
        run = _import_results_doc(db, p, impl, {
            "fixture": tool.id, "fixture_version": f"ct_dynamic_audit@{src['run_commit'][:12]}", "status": "completed",
            "metrics": mapped["metrics"], "metric_definitions": METRIC_DEFINITIONS, "scenarios": mapped["scenarios"],
            "environment": {"measured_by": f"{src['repository']} task card {src['card_id']}", "summary_sha256": src["summary_sha256"],
                            "receipt_sha256": src["receipt_sha256"], "report": src["report"], "pull_request": src["pull_request"]},
            "limitations": snap["limitations"], "repeat_count": 1, "raw_summary_entry": e}, eng, test=test)
        run.inputs = {**(run.inputs or {}), "tool": tool.id, "params": {"target": e["target"], "instrument": "both", "expect": expect},
                      "record_name": f"Side-channel audit: {e['target']} (imported, crypto #3296)"}
    db.commit()
    if get_runner("ct_audit").available()[0]:
        _tool_preset(db, p, impl, eng, "sidechannel_ct_audit", 0)
        _tool_preset(db, p, impl, eng, "sidechannel_ct_audit", 1)
        _tool(db, p, impl, eng, "sidechannel_ct_audit", {"target": "x25519"}, "Side-channel audit (live): x25519")
        _tool(db, p, impl, eng, "sidechannel_ct_audit", {"target": "inv_euclid", "instrument": "taint"},
              "Side-channel audit (live): SM2 private-key inverse, taint only")
    db.commit()
    return p


def seed_sample(db, admin, eng, rev):
    p = Project(name="Sample: acme-signer (demonstration)", workflow="signature_library", is_demo=True, created_by=admin.id,
                description="Sample project showing the full loop on a small Ed25519 wrapper with a clearly labelled seeded defect.",
                intended_use="Service-to-service API request signing.", threat_assumptions="Attacker submits arbitrary requests; keys in KMS; replay cache keyed on signature bytes.",
                runtime_environment={"deployment": "Linux x86-64 container", "hardware": "cloud VM"})
    db.add(p)
    db.flush()
    db.add_all([ProjectMember(project_id=p.id, user_id=eng.id, role="editor"), ProjectMember(project_id=p.id, user_id=rev.id, role="reviewer")])
    tests = default_test_definitions(p.id)
    db.add_all(tests)
    db.add_all([Requirement(project_id=p.id, name="Verify p95 latency", metric="verify_time_ms_p95", operator="<=", threshold=1.0, unit="ms", applies_to="measured",
                            rationale="Request verification budget per hop."),
                Requirement(project_id=p.id, name="Signing throughput", metric="sign_throughput_per_s", operator=">=", threshold=5000, unit="signatures/s per core", applies_to="measured",
                            rationale="Peak outbound request rate with headroom."),
                Requirement(project_id=p.id, name="Signature size", metric="signature_bytes", operator="<=", threshold=64, unit="bytes", rationale="Header size budget."),
                Requirement(project_id=p.id, name="All rejection scenarios pass", metric="rejection_scenarios_all_pass", operator="==", threshold=1, unit=""),
                Requirement(project_id=p.id, name="All functional scenarios pass", metric="functional_pass", operator="==", threshold=1, unit="")])
    db.flush()
    core, sweep = tests[0], tests[1]
    v10 = _import(db, p, SEED_DIR / "sample_manifest_v1_0.json", SEED_DIR / "adapters" / "acme_signer_v1_0.py", eng,
                  seeded_defect="SEEDED DEFECT (demonstration): verify() keeps only the first 64 signature bytes, so signatures with trailing data verify.")
    db.commit()
    r1 = _run(db, p, core, v10, eng)  # fails trailing_byte / trailing_garbage -> finding opened
    # customer-side runner bundle (real runner, demo key kept under data/keys, labelled)
    keys = DATA_DIR / "keys"
    keys.mkdir(parents=True, exist_ok=True)
    kp = keys / "demo_runner_key.pem"
    if not kp.exists():
        k = attest.generate_private_key()
        kp.write_bytes(attest.private_key_to_pem(k))
        os.chmod(kp, 0o600)
    rk = attest.private_key_from_pem(kp.read_bytes())
    db.add(TrustedKey(project_id=p.id, key_id=attest.key_id(rk.public_key()), name="demo customer runner key (seeded)", public_key_pem=attest.public_key_to_pem(rk.public_key()),
                      purpose="customer_runner", status="active", note="Generated by the seed for the sample project. Private key in data/keys (not an artifact).", added_by=admin.id))
    db.commit()
    bundle = _customer_bundle(p.id, "acme-signer", "1.0.0", str(SEED_DIR / "adapters" / "acme_signer_v1_0.py"), kp)
    run_b, b, info = services.import_bundle(db, p, bundle, eng.id, eng.email, core)  # second, customer-side evidence on 1.0.0
    db.commit()
    # research source (demonstration)
    text = (SEED_DIR / "research_docs" / "noncanonical_signature_encodings.txt").read_text()
    src = ResearchSource(project_id=p.id, title="Non-canonical signature encodings in Ed25519 wrappers (paraphrase, demonstration)", content=text,
                         content_sha256=hashlib.sha256(text.encode()).hexdigest(), is_demo=True, submitted_by=eng.id)
    db.add(src)
    db.flush()
    review_source(db, src)
    db.commit()
    # autoresearcher proposes; reviewer approves (protocol v1); platform executes
    findings = db.scalars(select(Finding).where(Finding.project_id == p.id)).all()
    props = propose_experiments(db, p, findings, [src])
    db.commit()
    prop = next(x for x in props if x.allowlisted_fixture == "malformed_input_sweep")
    from .routers.research import PROTOCOL_FIELDS
    proto = {k: getattr(prop, k) for k in PROTOCOL_FIELDS}
    db.add(Approval(project_id=p.id, subject_type="experiment_proposal", subject_id=prop.id, decision="approved", reviewer_id=rev.id, note="Bounded, synthetic inputs, allowlisted fixture."))
    db.add(ProtocolVersion(proposal_id=prop.id, version=1, protocol=proto, protocol_sha256=attest.sha256_hex(attest.canonical(proto)), approved_by=rev.id, note="v1"))
    prop.current_protocol_version, prop.status = 1, "approved"
    db.commit()
    erun = services.create_run_record(db, p.id, sweep.id, v10.id, "platform_sandbox", "platform_sandbox", "measured", eng.id, proposal_id=prop.id, protocol_version=1)
    db.commit()
    services._job_execute_experiment(db, {"proposal_id": prop.id, "run_id": erun.id, "actor_id": eng.id})
    db.add(Approval(project_id=p.id, subject_type="experiment_proposal", subject_id=prop.id, decision="reviewed", reviewer_id=rev.id, note="Result consistent with H1."))
    prop.status = "reviewed"
    # recommendation from the defect finding, reviewed + approved by the reviewer
    defect = next(f for f in findings if f.kind == "implementation_defect")
    d = recommendation_for_finding(db, defect, p)
    rec = Recommendation(project_id=p.id, generated_by="platform (rule-based)", created_by=eng.id, status="approved", **d)
    db.add(rec)
    db.flush()
    defect.recommendation_id = rec.id
    services.set_finding_status(db, defect, "recommendation_proposed", eng.id, f"recommendation {rec.id} drafted")
    db.add_all([Approval(project_id=p.id, subject_type="recommendation", subject_id=rec.id, decision="reviewed", reviewer_id=rev.id, note="Guidance matches RFC 8032 §5.1.7."),
                Approval(project_id=p.id, subject_type="recommendation", subject_id=rec.id, decision="approved", reviewer_id=rev.id, note="Approved for engineering handoff.")])
    db.commit()
    # customer implements externally; 1.1.0 imported and linked
    v11 = _import(db, p, SEED_DIR / "sample_manifest_v1_1.json", SEED_DIR / "adapters" / "acme_signer_v1_1.py", eng, parent=v10, recommendation=rec)
    rec.resulting_implementation_id = v11.id
    defect.revised_implementation_id = v11.id
    services.set_finding_status(db, defect, "external_change_reported", eng.id, v11.change_report)
    services.set_finding_status(db, defect, "awaiting_retest", eng.id, "awaiting retest of acme-signer 1.1.0")
    db.commit()
    r2 = _run(db, p, core, v11, eng)
    ev = services.evaluate_retest(db, defect, r2)
    defect.evidence_run_ids = defect.evidence_run_ids + [r2.id]
    services.set_finding_status(db, defect, ev["outcome"], eng.id, f"retest run #{r2.sequence}: {ev['reason']}")
    db.commit()
    # cryptanalysis toolkit (only when crax is connected): controls so a reviewer can see the detectors work
    _tool(db, p, v11, eng, None, name="Signing-key hygiene: fresh RSA-2048 public keys (negative control)", control="rsa_real_keys")
    _tool(db, p, v11, eng, None, name="Control: planted shared-prime and close-prime moduli (positive)", control="rsa_weak_moduli")
    _tool_preset(db, p, v11, eng, "suite_curve_audit", 0, "Curve parameter audit: P-256 (negative control)")
    _tool_preset(db, p, v11, eng, "suite_ecdsa_audit", 0, "Control: planted 192-bit ECDSA nonce bias (positive)")
    _tool(db, p, v11, eng, None, name="Digest cross-check: suite SHA-256 vs Python hashlib", control="firmware_digest")
    # attack assessments tied to the implementation
    db.add_all([
        AttackAssessment(project_id=p.id, implementation_id=v10.id, category="reproduced_weakness", attack_model="classical", target="acme-signer 1.0.0 verify() (adapter wrapper)",
                         target_version="1.0.0", target_parameters={"algorithm": "Ed25519", "signature_bytes": 64},
                         objective="Have a signature with appended data accepted, producing distinct signature bytes for the same message (replay-cache / ID confusion).",
                         attacker_capabilities="Can submit arbitrary requests to a verifying service.", method="Append bytes to a valid signature.",
                         source=f"Reproduced by platform runs #{r1.sequence} and #{erun.sequence}.", hardware_assumptions="None (deterministic input handling).",
                         measured_components={"accepted_malformed_cases": erun.metrics.get("accepted_count"), "run_id": erun.id},
                         expected_work={"value": 1, "unit": "request (deterministic)", "estimation_method": "directly reproduced; no search involved"},
                         uncertainty="None for the acceptance itself; impact depends on the surrounding protocol.",
                         applicability_limits="Not a forgery: the attacker still needs a valid signature. Impact exists only where signature bytes are used as identifiers.",
                         run_id=erun.id, finding_id=defect.id, review_date=utcnow().date().isoformat(), is_demo=True),
        AttackAssessment(project_id=p.id, implementation_id=v10.id, category="published_estimate", attack_model="classical", target="Ed25519 (scheme)", target_version="RFC 8032",
                         target_parameters={"curve": "Curve25519", "group_order_bits": 253}, objective="Recover the private key or forge a signature.",
                         attacker_capabilities="Best known classical algorithms (Pollard rho on the ~2^252 group).", method="Generic elliptic-curve discrete logarithm.",
                         source="Bernstein, Duif, Lange, Schwabe, Yang, 'High-speed high-security signatures' (2011); RFC 8032 design target ~128-bit security.",
                         hardware_assumptions="Not quantified here.", expected_work={"value": None, "unit": "", "log2_work": 126, "estimation_method": "published design-level estimate (~2^126 curve operations); not measured"},
                         uncertainty="Design-level; no practical attack is known.", applicability_limits="Says nothing about wrapper or implementation defects.",
                         review_date=utcnow().date().isoformat(), is_demo=True),
        AttackAssessment(project_id=p.id, implementation_id=v10.id, category="published_estimate", attack_model="quantum", target="Ed25519 (scheme)", target_version="RFC 8032",
                         target_parameters={"curve": "Curve25519"}, objective="Recover the private key with Shor's algorithm.",
                         attacker_capabilities="Hypothetical large fault-tolerant quantum computer.", method="Shor's algorithm for elliptic-curve discrete logarithms.",
                         source="Published logical-resource estimates exist for 256-bit-class curves (e.g. Roetteler, Naehrig, Svore, Lauter, ASIACRYPT 2017). No date is asserted.",
                         hardware_assumptions="Far beyond any publicly reported device.", expected_work=None,
                         uncertainty="Resource estimates have changed by large factors over time.", applicability_limits="Classical and quantum records are separate.",
                         review_date=utcnow().date().isoformat(), is_demo=True),
        AttackAssessment(project_id=p.id, implementation_id=v11.id, category="unknown", attack_model="classical", target="acme-signer 1.1.0 side-channel behaviour", target_version="1.1.0",
                         target_parameters={}, objective="Timing or memory side channel in verify().", attacker_capabilities="Co-located observer.",
                         method="Not measured; a timing harness is not allowlisted yet.", source="Experiment proposal (proposal only).", expected_work=None,
                         uncertainty="Unknown.", applicability_limits="No defensible estimate available.", review_date=utcnow().date().isoformat(), is_demo=True)])
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
        for email, name, pw, adm in DEMO_USERS:
            u = User(email=email, name=name, password_hash=hash_password(pw), is_admin=adm)
            db.add(u)
            users[email] = u
        db.flush()
        signing.ensure_platform_key_registered(db, users["admin@isogeny.local"].id)
        p = seed_sample(db, users["admin@isogeny.local"], users["engineer@customer.local"], users["reviewer@isogeny.local"])
        t = seed_toolkit_controls(db, users["admin@isogeny.local"], users["engineer@customer.local"], users["reviewer@isogeny.local"])
        sc = seed_ct_audit(db, users["admin@isogeny.local"], users["engineer@customer.local"], users["reviewer@isogeny.local"])
        audit.record(db, users["admin@isogeny.local"].id, "seed.completed", "system", None, None,
                     {"project": p.id, "toolkit_project": t.id if t else None, "sidechannel_project": sc.id}, commit=True)
        print(f"seeded sample project: {p.name}" + (f" | {t.name}" if t else " (crax not connected: toolkit control runs skipped)") + f" | {sc.name}")


if __name__ == "__main__":
    ensure_seed()
