#!/usr/bin/env python3
"""Build a READ-ONLY static demo of the UI (GitHub Pages / single file).

GitHub Pages cannot run the backend. This script boots the real app against a throw-away database (seeding the sample
project with real sandbox executions, a real customer-runner bundle and real signed bundles), snapshots every GET
response the UI uses, and copies the frontend with static-demo mode on. Writes are disabled in the result.
Usage: python3 scripts/build_static_site.py [outdir]   (default: site/)
"""
import base64
import itertools
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "site"
tmp = tempfile.mkdtemp(prefix="iel-static-")
os.environ.update({"IEL_DATA_DIR": tmp, "IEL_DATABASE_URL": f"sqlite:///{tmp}/s.sqlite3", "IEL_ARTIFACT_DIR": f"{tmp}/artifacts", "IEL_WORKER": "external",
                   "IEL_PLATFORM_KEY_PATH": f"{tmp}/keys/platform.pem"})
os.environ.pop("IEL_SKIP_SEED", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

snap = {"get": {}, "filedata": {}}


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    with TestClient(app) as c:
        tok = c.post("/api/auth/login", json={"email": "engineer@customer.local", "password": "engineer-demo-password"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}

        def get(path):
            r = c.get(path, headers=H)
            if r.status_code != 200:
                print("  skip", path, r.status_code); return None
            snap["get"][path] = r.json(); return r.json()

        def post_json(path, body):
            r = c.post(path, json=body, headers=H)
            if r.status_code == 200:
                snap["get"]["POST " + path] = r.json()
            return r

        projects = get("/api/projects")
        for path in ("/api/auth/me", "/api/catalog", "/api/runners", "/api/jobs", "/api/platform-key", "/api/toolkit", "/api/research/portfolio"):
            get(path)
        for p in projects:
            b = f"/api/projects/{p['id']}"
            for sub in ("", "/overview", "/inventory", "/requirements", "/implementations", "/tests", "/runs", "/research/status", "/research/sources",
                        "/experiments", "/experiments/allowlist", "/attack-assessments", "/findings", "/recommendations", "/bundles", "/trusted-keys",
                        "/audit", "/artifacts", "/export/handoff", "/toolkit/runs"):
                get(b + sub)
            for kind in ("implementations", "runs", "experiments", "findings", "recommendations", "bundles"):
                for it in snap["get"][b + "/" + kind]:
                    get(f"{b}/{kind}/{it['id']}")
                    if kind == "implementations" and it.get("source_snapshot_artifact_id"):
                        get(f"{b}/implementations/{it['id']}/snapshot")
            tests = snap["get"][b + "/tests"]
            for t in tests:
                for i in snap["get"][b + "/implementations"]:
                    get(f"{b}/tests/{t['id']}/preflight?implementation_id={i['id']}&execution_mode=platform_sandbox")
            # like-for-like comparisons only (same test definition); cross-tool pairs are not meaningful and grow quadratically.
            # The side-channel tool also keys on the audited target: two different code paths are not comparable.
            def like_for_like(r):
                inp = r.get("inputs") or {}
                return (r["test_definition_id"], (inp.get("params") or {}).get("target") if inp.get("tool") == "sidechannel_ct_audit" else None)
            done = [r for r in snap["get"][b + "/runs"] if r["status"] == "completed"]
            for rx, ry in itertools.permutations(done, 2):
                if like_for_like(rx) != like_for_like(ry):
                    continue
                get(f"{b}/compare?baseline_run_id={rx['id']}&candidate_run_id={ry['id']}")
            post_json(f"{b}/export/compliance", {"applicability": {}, "format": "json"})
            for a in snap["get"][b + "/artifacts"]:
                r = c.get(f"{b}/artifacts/{a['id']}/download", headers=H)
                snap["filedata"][f"{b}/artifacts/{a['id']}/download"] = {"name": a["filename"], "b64": base64.b64encode(r.content).decode()}
            for name, path, fname in (("package", f"{b}/export/package", "evidence_package.zip"), ("handoff", f"{b}/export/handoff?format=html", "engineering_handoff.html")):
                r = c.get(path, headers=H)
                snap["filedata"][path] = {"name": fname, "b64": base64.b64encode(r.content).decode()}
            r = c.post(f"{b}/export/compliance", json={"applicability": {}, "format": "html"}, headers=H)
            snap["filedata"][f"POST {b}/export/compliance?format=html"] = {"name": "compliance_evidence.html", "b64": base64.b64encode(r.content).decode()}
    print(f"snapshot: {len(snap['get'])} responses, {len(snap['filedata'])} files")
    for name in ("index.html", "styles.css", "app.js"):
        s = (ROOT / "frontend" / name).read_text()
        if name == "index.html":
            s = s.replace('<script src="app.js"></script>', '<script src="snapshot.js"></script>\n<script src="app.js"></script>')
            s = s.replace("<main", '<div id="demobanner">Static read-only demo: a snapshot of real output from the seeded sample project (sandbox runs, signed bundles and the customer-runner bundle were produced at build time). Writes are disabled; run the app locally for the full workflow.</div>\n<main', 1)
        (OUT / name).write_text(s)
    shutil.copytree(ROOT / "frontend" / "assets", OUT / "assets")
    (OUT / "snapshot.js").write_text("window.IEL_STATIC = " + json.dumps(snap, separators=(",", ":")) + ";\n")
    (OUT / ".nojekyll").write_text("")
    # single self-contained file (assets inlined as data URIs)
    idx = (OUT / "index.html").read_text()
    idx = idx.replace('<link rel="stylesheet" href="styles.css">', "<style>\n" + (OUT / "styles.css").read_text() + "\n</style>")
    for a in sorted((OUT / "assets").iterdir()):
        if a.suffix == ".png":
            idx = idx.replace(f"assets/{a.name}", "data:image/png;base64," + base64.b64encode(a.read_bytes()).decode())
    idx = idx.replace('<script src="snapshot.js"></script>', "<script>\n" + (OUT / "snapshot.js").read_text() + "</script>")
    idx = idx.replace('<script src="app.js"></script>', "<script>\n" + (OUT / "app.js").read_text() + "\n</script>")
    (OUT / "iel-demo.html").write_text(idx)
    print("site written to", OUT, f"({sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())//1024} KB)")


main()
shutil.rmtree(tmp, ignore_errors=True)
