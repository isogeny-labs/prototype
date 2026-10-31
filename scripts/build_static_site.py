#!/usr/bin/env python3
"""Build a READ-ONLY static demo of the UI for GitHub Pages.

GitHub Pages cannot run the FastAPI backend, fixtures or job queue. This script:
  1. boots the real application in-process against a throw-away database (seeds + real fixture runs),
  2. calls the real API as the demo engineer, also generating catalog recommendations and one remediation proposal,
  3. snapshots every GET response the UI can request into site/snapshot.json (plus artifact/export downloads),
  4. copies the frontend with relative asset paths and static-demo mode switched on.

Everything shown is real output of the app at build time; nothing can be changed in the hosted demo.
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
os.environ.update({"IEL_DATA_DIR": tmp, "IEL_DATABASE_URL": f"sqlite:///{tmp}/s.sqlite3", "IEL_ARTIFACT_DIR": f"{tmp}/artifacts",
                   "IEL_WORKER": "external"})
os.environ.pop("IEL_SKIP_SEED", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

snap = {"get": {}, "files": {}}
files_dir = OUT / "data" / "files"


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    files_dir.mkdir(parents=True)
    with TestClient(app) as c:
        tok = c.post("/api/auth/login", json={"email": "engineer@customer.local", "password": "engineer-demo-password"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}

        def get(path, store=True):
            r = c.get(path, headers=H)
            if r.status_code != 200:
                print("  skip", path, r.status_code)
                return None
            if store:
                snap["get"][path] = r.json()
            return r.json()

        def post(path, body=None):
            r = c.post(path, json=body, headers=H)
            assert r.status_code == 200, (path, r.status_code, r.text)
            return r.json()

        projects = get("/api/projects")
        for p in projects:  # real API calls so the Recommendation screens have real content
            post(f"/api/projects/{p['id']}/recommendations/generate")
            if p["kind"] == "iot":
                f = next(x for x in get(f"/api/projects/{p['id']}/findings", False) if x["origin"] == "measurement" and "slot" in x["title"].lower())
                post(f"/api/projects/{p['id']}/recommendations/from-finding/{f['id']}")
        for path in ("/api/projects", "/api/auth/me", "/api/catalog", "/api/runners", "/api/jobs"):
            get(path)
        for p in projects:
            b = f"/api/projects/{p['id']}"
            for sub in ("", "/overview", "/inventory", "/requirements", "/implementations", "/runs", "/experiments", "/recommendations",
                        "/findings", "/research/sources", "/research/status", "/attack-assessments", "/sandbox", "/sandbox/allowlist",
                        "/revalidation", "/audit", "/artifacts"):
                get(b + sub)
            for kind, ids in (("implementations", [i["id"] for i in snap["get"][b + "/implementations"]]),
                              ("runs", [r["id"] for r in snap["get"][b + "/runs"]]),
                              ("recommendations", [r["id"] for r in snap["get"][b + "/recommendations"]]),
                              ("findings", [f["id"] for f in snap["get"][b + "/findings"]])):
                for i in ids:
                    get(f"{b}/{kind}/{i}")
            done = [r["id"] for r in snap["get"][b + "/runs"] if r["status"] == "completed"]
            for x, y in itertools.permutations(done, 2):
                get(f"{b}/compare?baseline_run_id={x}&candidate_run_id={y}")
            for a in snap["get"][b + "/artifacts"]:
                r = c.get(f"{b}/artifacts/{a['id']}/download", headers=H)
                (files_dir / a["id"]).write_bytes(r.content)
                snap["files"][f"{b}/artifacts/{a['id']}/download"] = f"data/files/{a['id']}"
            r = c.get(f"{b}/export", headers=H)
            (files_dir / f"export_{p['id']}.zip").write_bytes(r.content)
            snap["files"][f"{b}/export"] = f"data/files/export_{p['id']}.zip"
    print(f"snapshot: {len(snap['get'])} responses, {len(snap['files'])} files")

    for name in ("index.html", "styles.css", "app.js"):
        s = (ROOT / "frontend" / name).read_text()
        if name == "index.html":
            s = s.replace('href="/static/styles.css"', 'href="styles.css"').replace('src="/static/app.js"', 'src="snapshot.js"></script>\n<script src="app.js"')
            s = s.replace("<main", '<div id="demobanner">Static read-only demo: a snapshot of real output from the seeded app (fixtures were executed at build time). '
                          'Writes are disabled. Run the app locally to use the full workflow &mdash; see the README.</div>\n<main', 1)
        (OUT / name).write_text(s)
    (OUT / "snapshot.js").write_text("window.IEL_STATIC = " + json.dumps(snap, separators=(",", ":")) + ";\n")
    (OUT / ".nojekyll").write_text("")
    with open(OUT / "styles.css", "a") as f:
        f.write("\n#demobanner{background:#fff4e0;color:#7a4b00;border-bottom:1px solid #f0d9a8;padding:6px 18px;font-size:12.5px;text-align:center}\n")
    print("site written to", OUT, f"({sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())//1024} KB)")


main()
shutil.rmtree(tmp, ignore_errors=True)
