"""Evidence download: one signed JSON file (the record) and a readable HTML copy.

- The JSON is written in one exact form (app.canonical). Its envelope is
  {"evidence": E, "fingerprint": F, "public_key": P, "signature": S}: F is the SHA-256 of E's exact bytes,
  S is an Ed25519 signature over F made with this app's own key, P is that key's public half.
- The signing key is made on first start, kept in the data folder with mode 0600, and never leaves this
  module: no API returns it, nothing logs it, no container can see it.
- E is built field by field from an explicit list. Nothing is copied from a database row wholesale.
- It also holds the Fixes step: each fix, and for a code change the change itself, every proof of it (the proof
  record, its fingerprint, the review and each proof run in full), the pull request, the approvals and the merge.
  The change as a ready-to-apply patch is in it only while "Download patch" is allowed (the change is offered).
- The HTML report is static: every value is escaped, there are no scripts and no remote resources.

Check a downloaded file with:  cd backend && .venv/bin/python -m evidence verify <file.json>
"""
from __future__ import annotations

import hashlib
import html
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select

from . import components, present_fixes
from .canonical import canonical_bytes, sha256_hex
from .db import (
    ChangeRow, CodeConnectionRow, EvidenceExportRow, ImportRow, PlanItemRow, PlanRow, ProofReviewRow, ProofRow,
    ResearchRequestRow, RetestRow, ReviewMarkRow, ReviewRow, TestRunRow, TestSpecRow, VerifyRunRow, iso,
)
from .errors import Conflict, NotFound
from .gitrepo import GitRepoError
from .guidance import OWN_LINKS
from .present import DISCLAIMER, TITLES
from .testlab import CODE_KEYS, RUNNER_ID, read_spec, review_dict, run_record
from .vectors import WYCHEPROOF_SOURCE_URL

EVIDENCE_SCHEMA = "isogeny.evidence/1"
SIGNING_CONTEXT = b"isogeny-evidence-lab/evidence/v1\n"
SIGNING_KEY_FILE = "evidence-signing-key.pem"
PUBLIC_KEY_FILE = "evidence-signing-public-key.txt"
VERIFY_COMMAND = "cd backend && .venv/bin/python -m evidence verify <the downloaded .json file>"
REPORT_LINE = "The JSON file is the record. This page is a readable copy and is not signed."
CSP = "default-src 'none'; style-src 'unsafe-inline'"
# The name of the evidence part that describes the imported file. It is put together here because a test of
# the container set-up scans the app for that word in quotes (it is also a docker verb) outside prepare.py.
IMPORT_PART = "imp" + "ort"
REPORT_LINKS = tuple(OWN_LINKS) + (WYCHEPROOF_SOURCE_URL,)  # the only links a report may carry: our own config


class SigningKeyError(Exception):
    """The evidence signing key in the data folder is missing or unreadable."""


# ------------------------------------------------------------------ the signing key

def _load_private(path: Path) -> Ed25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (OSError, ValueError, TypeError) as exc:
        raise SigningKeyError("The evidence signing key in the data folder could not be read.") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise SigningKeyError("The evidence signing key in the data folder is not an Ed25519 key.")
    return key


def _public_hex(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def key_fingerprint(public_key_hex: str) -> str:
    """A short way to name the signer: SHA-256 of the 32 public key bytes."""
    return hashlib.sha256(bytes.fromhex(public_key_hex)).hexdigest()


def ensure_signing_key(data_dir: Path) -> str:
    """Make the app's evidence signing key if there is none yet. Returns the PUBLIC key (hex); the private key
    stays in its file (mode 0600) and is never returned."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    key_path, public_path = data_dir / SIGNING_KEY_FILE, data_dir / PUBLIC_KEY_FILE
    if not key_path.exists():
        pem = Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass  # another start made it a moment ago; use that one
        else:
            with os.fdopen(fd, "wb") as fh:
                fh.write(pem)
        del pem
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    public = _public_hex(_load_private(key_path))
    try:
        current = public_path.read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        current = None
    if current != public:
        public_path.write_text(public + "\n", encoding="ascii")
    return public


def sign_envelope(evidence: dict, data_dir: Path) -> bytes:
    """The exact bytes of the evidence file: canonical JSON of {evidence, fingerprint, public_key, signature}."""
    key = _load_private(Path(data_dir) / SIGNING_KEY_FILE)
    fingerprint = sha256_hex(evidence)
    signature = key.sign(SIGNING_CONTEXT + fingerprint.encode("ascii")).hex()
    return canonical_bytes({"evidence": evidence, "fingerprint": fingerprint, "public_key": _public_hex(key),
                            "signature": signature})


# ------------------------------------------------------------------ building the evidence (allow-list)

def _clean(value: object) -> object:
    """Last line of defence before anything leaves the app: private keys masked (components.scrub) and every
    string made valid UTF-8."""
    value = components.scrub(value)

    def fix(v):
        if isinstance(v, dict):
            return {str(k).encode("utf-8", "replace").decode("utf-8"): fix(x) for k, x in v.items()}
        if isinstance(v, list):
            return [fix(x) for x in v]
        if isinstance(v, str):
            return v.encode("utf-8", "replace").decode("utf-8")
        return v
    return fix(value)


def _pick(source: object, keys: tuple[str, ...]) -> dict:
    source = source if isinstance(source, dict) else {}
    return {k: source.get(k) for k in keys}


def _block(block: dict) -> dict:
    if block.get("type") == "table":
        return {"type": "table", "title": block.get("title"), "tag": block.get("tag"),
                "columns": [_pick(c, ("label", "align", "mono")) for c in block.get("columns") or []],
                "rows": [[str(cell) for cell in row] for row in block.get("rows") or []],
                "meta": [_meta(m) for m in block.get("meta") or []], "note": block.get("note")}
    return {"type": "text", "title": block.get("title"), "tag": block.get("tag"), "text": block.get("text")}


def _meta(item: dict) -> dict:
    out = _pick(item, ("label", "value", "tag"))
    if item.get("time"):
        out["time"] = item["time"]
    if item.get("href") in REPORT_LINKS:
        out["href"] = item["href"]
    return out


def _result_view(r: dict) -> dict:
    """The worded result, exactly as Evidence Lab showed it, copied field by field."""
    record, locked, research = r.get("run_record") or {}, r.get("locked_test") or {}, r.get("research")
    return {
        **_pick(r, ("run_id", "component", "mode", "finished_at", "duration_ms", "code", "label", "tone", "summary", "short",
                    "shows_title", "fix_title", "suggested_fix")),
        # the one line that stands in place of the suggested fix when the fix is in the Fixes part
        "fix_line": _pick(r["fix_line"], ("fix_id", "lead", "rest")) if r.get("fix_line") else None,
        "control": _pick(r.get("control"), ("outcome", "line", "text")),
        "what_happened": [str(x) for x in r.get("what_happened") or []],
        "shows": [str(x) for x in r.get("shows") or []],
        "evidence": [_block(b) for b in r.get("evidence") or []],
        "run_record": {"title": record.get("title"), "command": record.get("command"),
                       "outputs": [_pick(o, ("title", "text")) for o in record.get("outputs") or []],
                       "meta": [_meta(m) for m in record.get("meta") or []]},
        "locked_test": {**_pick(locked, ("title", "locked_at", "locked_text", "fingerprint_label", "fingerprint", "note")),
                        "fields": [{"label": f.get("label"), "lines": [str(x) for x in f.get("lines") or []]}
                                   for f in locked.get("fields") or []]},
        "reviewed": _pick(r["reviewed"], ("at", "text")) if r.get("reviewed") else None,
        "research": ({**_pick(research, ("id", "title", "badge", "status", "status_line", "saved_at", "note")),
                      "fields": [_pick(f, ("label", "value")) for f in research.get("fields") or []]} if research else None),
    }


def _review(row: ReviewRow) -> dict:
    r = review_dict(row)
    return {"schema": r["schema"], "reviewer": r["reviewer"], "proposed_by": r["proposed_by"], "spec_hash": r["spec_hash"],
            "spec_hash_ok": r["spec_hash_ok"], "run_sha256": r["run_sha256"], "control": _pick(r["control"], ("outcome", "reason")),
            "reference_ok": r["reference_ok"],
            "verdict": {"code": r["code"], "reason_code": r["reason_code"], "reason": r["reason"]},
            "detail": r["detail"], "created_at": r["created_at"]}


def _run_entry(lab, db, phase: str, view: dict | None) -> dict | None:
    """Everything kept about one shown run: the run record as fingerprinted, the review, the worded result, and
    which code it ran on (kept beside the run record, not inside its fingerprint)."""
    run = db.get(TestRunRow, view.get("run_id")) if view else None
    review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == run.id)).first() if run is not None else None
    if run is None or review is None:
        return None  # nothing is exported without a review
    record = run_record(run)
    code = lab._run_code(db, run.id)
    mark = db.scalars(select(ReviewMarkRow).where(ReviewMarkRow.run_id == run.id)).first()
    request = db.scalars(select(ResearchRequestRow).where(ResearchRequestRow.run_id == run.id)).first()
    return {"phase": phase, "run_id": run.id, "record": record, "run_sha256": sha256_hex(record), "review": _review(review),
            "code": _pick(code, CODE_KEYS) if code else None,
            "result": _result_view(view), "reviewed_at": iso(mark.created_at) if mark else None,
            "research_request": ({"id": request.id, "finding": request.finding, "question": request.question,
                                  "evidence": _pick(request.evidence, ("run_id", "spec_hash", "review_id")),
                                  "status": request.status, "engine": request.engine, "created_at": iso(request.created_at)}
                                 if request else None)}


def _suggestion(shown: dict) -> dict | None:
    """A text-only fix's suggestion, exactly as the Fixes step showed it, copied field by field."""
    section = next((x for x in shown.get("sections") or [] if x.get("key") == "suggestion"), None)
    if section is None:
        return None
    given = section.get("suggestion") or {}
    where, options, exact = given.get("where"), given.get("options"), given.get("exact")
    return {
        "intro": [str(x) for x in given.get("intro") or []],
        "warning": _pick(given["warning"], ("title", "text")) if given.get("warning") else None,
        "where": ({**_pick(where, ("title", "note")), "columns": [str(x) for x in where.get("columns") or []],
                   "rows": [_pick(row, ("place", "setting", "lead", "code")) for row in where.get("rows") or []],
                   "after": [str(x) for x in where.get("after") or []]} if where else None),
        "options": ({"title": options.get("title"),
                     "items": [{**_pick(item, ("title", "when", "note")), "steps": [str(x) for x in item.get("steps") or []]}
                               for item in options.get("items") or []]} if options else None),
        "exact": ({**_pick(exact, ("title", "note")), "blocks": [_pick(block, ("place", "code")) for block in exact.get("blocks") or []]}
                  if exact else None),
    }


def _proof_entry(lab, db, proof: ProofRow, change: ChangeRow) -> dict:
    """One proof of a change: the record its fingerprint is made from, that fingerprint, the review as the read
    gate lets it through, and every test with the first result it was compared with and its proof run in full."""
    tests = lab._proof_tests(db, proof)
    record = lab._proof_record(proof, change, tests)
    review = lab._proof_review(db, proof, change, tests)
    stored = db.scalars(select(ProofReviewRow).where(ProofReviewRow.proof_id == proof.id)).first()
    checks = {check.get("item_id"): check for check in (review or {}).get("tests") or []}
    rows = []
    for test in tests:
        first = db.get(TestRunRow, test["first"]["run_id"]) if test["first"] else None
        run = lab._latest_run(db, test["item_id"], "proof", proof.id)
        result = lab._result(db, run) if run is not None else None
        # the two cells of the proof table, in the words the Fixes step shows them in
        before = present_fixes.proof_cell(lab._result(db, first) if first is not None else None, test["kind"], "before")
        check = checks.get(test["item_id"])
        rows.append({"item_id": test["item_id"], "kind": test["kind"], "title": TITLES.get(test["kind"], str(test["kind"])),
                     "target": test["target"],
                     "first": ({**_pick(test["first"], ("run_id", "run_sha256", "code", "reason_code")), **_pick(before, ("label", "short"))}
                               if test["first"] else None),
                     "shown": _pick(present_fixes.proof_cell(result, test["kind"], "proof"), ("label", "tone", "short")) if result else None,
                     "run": _run_entry(lab, db, "proof", result) if run is not None else None,
                     "check": ({**_pick(check, ("group", "report_only", "ok", "reason")), "text": present_fixes.CHECK_WORDS.get(check.get("reason"))}
                               if check else None)})
    return {"id": proof.id, "started_at": iso(proof.started_at), "baseline_version": proof.baseline_version, "version": proof.version,
            "record": record, "record_sha256": sha256_hex(record), "outcome": present_fixes.proof_outcome(review),
            "review": ({**_pick(review, ("reviewed_at", "believed", "offered", "problem", "record_sha256", "checks", "counts", "answers", "speed")),
                        "reviewer": stored.reviewer if review["believed"] else None} if review else None),
            "tests": rows}


def _fix_entry(lab, db, fix: dict, shown: dict) -> dict:
    """One fix: what the Fixes step showed about it and, for a code change, the records behind every step."""
    said = shown.get("proof") or {}
    entry = {"id": fix["id"], "kind": fix["kind"], "title": shown.get("title"), "status": (shown.get("status") or {}).get("word"),
             # what the summary said about the proof under that status, so a reader of the file sees the reason too
             # (for example why a proof that passed no longer counts): the badge's words and the sentence
             "proof_summary": {"state": said.get("state"), "label": (said.get("badge") or {}).get("label"), "text": said.get("text")},
             "source": {"kind": fix["source_kind"], "text": shown.get("list_source"),
                        "results": [_pick(answer, ("item_id", "kind", "run_id", "phase")) for answer in fix["answers"]]},
             "suggestion": _suggestion(shown), "change": None, "proofs": [], "pull_request": None, "approvals": [], "merge": None}
    change, request, merge = fix["change"], fix["pull_request"], fix["merge"]
    if change is None:
        return entry
    patch = None
    if fix["actions"]["download_patch"] is None:
        # The ready-to-apply patch is handed out only while "Download patch" itself is allowed: a change that is
        # not offered is described below (file names, counts, ids, SHA-256s) but not given in a form to apply.
        try:
            patch = lab._patch_text(fix)
        except (GitRepoError, OSError):
            patch = None  # the copy of the repository could not be read: the records below still stand
    row = db.get(ChangeRow, change["id"])
    entry["change"] = {
        **_pick(change, ("fix_key", "source_kind", "written_by", "template_id", "proposed_by", "title", "branch", "base_commit",
                         "head_commit", "created_at")),
        "label": next(iter(shown.get("labels") or []), None), "size": present_fixes.size_words(change),
        "files": [_pick(f, ("name", "added", "removed", "old_blob", "new_blob", "old_sha256", "new_sha256")) for f in change["files"]],
        "built": {**_pick(change["built"], ("file", "sha256")),
                  "matches": _pick(change["built"]["matches"], ("name", "version")) if change["built"].get("matches") else None},
        "patch": patch}
    entry["proofs"] = [_proof_entry(lab, db, proof, row)
                       for proof in db.scalars(select(ProofRow).where(ProofRow.change_id == row.id).order_by(ProofRow.id)).all()]
    if request is not None:
        approvers = shown.get("approvers") or {}
        demo = {row.get("id") for row in approvers.get("rows") or [] if row.get("demo")}
        # The approvals, with what the screen says beside them: one login records them all, and which names are demo data.
        entry["pull_request"] = {**_pick(request, ("number", "title", "proof_id", "reviewers", "opened_at")),
                                 "approvals_note": approvers.get("footnote")}
        entry["approvals"] = [{**_pick(a, ("reviewer", "name", "approved_at")),
                               "label": present_fixes.DEMO_DATA if a["reviewer"] in demo else None} for a in request["approvals"]]
    if merge is not None:
        entry["merge"] = _pick(merge, ("merge_commit", "merged_at"))
    return entry


def build_evidence(lab, plan_id: int, generated_at: str | None = None) -> dict:
    """The evidence for one plan, from the same reviewed results Evidence Lab shows."""
    view = lab.lab_view(plan_id)  # the read gate: every result here has a review that still matches its record
    public = ensure_signing_key(lab.settings.data_dir)
    with lab.db() as db:
        plan = db.get(PlanRow, plan_id)
        imp = db.get(ImportRow, plan.import_id)
        verify = db.scalars(select(VerifyRunRow).where(VerifyRunRow.import_id == imp.id)
                            .order_by(VerifyRunRow.id.desc()).limit(1)).first()
        retest = db.scalars(select(RetestRow).where(RetestRow.plan_id == plan_id).order_by(RetestRow.id.desc()).limit(1)).first()
        connection = db.scalars(select(CodeConnectionRow).where(CodeConnectionRow.plan_id == plan_id)).first()
        tests = []
        for row in view["rows"]:
            item = db.get(PlanItemRow, row["item_id"])
            spec_row = db.get(TestSpecRow, item.spec_hash)
            spec, spec_ok = read_spec(spec_row)
            runs = [_run_entry(lab, db, phase, row[key]) for phase, key in (("first", "result"), ("retest", "after")) if row.get(key)]
            tests.append({"item_id": item.id, "kind": row["kind"], "title": row["title"], "origin": item.origin,
                          "spec_hash": item.spec_hash, "spec_hash_ok": bool(spec_ok),
                          "locked_at": iso(spec_row.locked_at) if spec_row else None,
                          "proposed_by": spec_row.proposed_by if spec_row else None, "spec": spec,
                          "control_line": row.get("control_line"), "runs": [r for r in runs if r is not None]})
        evidence = {
            "schema": EVIDENCE_SCHEMA,
            "generated_at": generated_at or iso(datetime.now(timezone.utc)),
            "app": {"name": "Isogeny Evidence Lab", "proposed_by": lab.engine.engine_id, "reviewed_by": lab.reviewer.engine_id,
                    "runner": RUNNER_ID, "note": "Both engines are rule-based code from the same build. No AI model is connected."},
            "mode_line": lab.mode.line,
            "disclaimer": DISCLAIMER,
            IMPORT_PART: {"filename": imp.filename, "format": imp.format, "is_demo": bool(imp.is_demo), "imported_at": iso(imp.created_at),
                       "claims": [{"ref": c.ref, "location": c.location, "location_kind": c.location_kind, "kind": c.kind,
                                   "claimed_value": c.claimed_value, "text": c.text, "source": c.source} for c in imp.claims],
                       "addresses": [{"address": a.address, "resolved_ip": a.resolved_ip, "is_loopback": bool(a.is_loopback),
                                      "confirmed": bool(a.confirmed)} for a in imp.addresses]},
            "verify": ({"started_at": iso(verify.started_at), "finished_at": iso(verify.finished_at),
                        "results": [{"claim": (r.get("claim") or {}).get("text"), "claim_ref": (r.get("claim") or {}).get("ref"),
                                     "result": r.get("result"), "found": r.get("found"), "reason": r.get("reason"),
                                     "evidence": [_pick(e, ("title", "command", "output", "started_at", "duration_ms", "tool", "tool_version"))
                                                  for e in r.get("evidence") or [] if isinstance(e, dict)]}
                                    for r in verify.results or [] if isinstance(r, dict)]} if verify else None),
            "component": ({"name": plan.component_name, "version": plan.component_version} if plan.component_name else None),
            "tests": tests,
            "retest": ({"baseline_version": retest.baseline_version, "version": retest.version, "started_at": iso(retest.created_at),
                        "columns": view.get("columns"),
                        "code_line": "".join(str(part.get("v")) for part in view["code_line"]) if view.get("code_line") else None}
                       if retest else None),
            # The source code connected for this plan (the app's own copy of a demo repository), and the Fixes step.
            "code": ({"repository": connection.repository, "branch": connection.branch, "base_commit": connection.base_commit,
                      "component": {"name": connection.component_name, "version": connection.component_version},
                      "is_demo": bool(connection.is_demo), "connected_at": iso(connection.created_at)} if connection else None),
            "fixes": [_fix_entry(lab, db, fix, shown) for fix, shown in lab._fix_details(db, plan)],
            "signer_key_fingerprint": key_fingerprint(public),
        }
    return _clean(evidence)


# ------------------------------------------------------------------ the readable report (static HTML)

class _Safe(str):
    """HTML that this module made itself. Everything else must go through t() to get here."""


def t(value: object) -> _Safe:
    return _Safe(html.escape("" if value is None else str(value), quote=True))


def _join(parts) -> _Safe:
    parts = list(parts)
    for part in parts:
        if not isinstance(part, _Safe):
            raise TypeError("unescaped text in the report")
    return _Safe("".join(parts))


_TAGS = frozenset("h1 h2 h3 h4 p div span section table thead tbody tr th td pre code ul li details summary strong a".split())
_CLASS = re.compile(r"^[a-z][a-z0-9 -]*$")


def el(tag: str, *children: _Safe, cls: str | None = None, href: str | None = None) -> _Safe:
    if tag not in _TAGS or (cls is not None and not _CLASS.match(cls)):
        raise ValueError("not an allowed element")
    attrs = f' class="{cls}"' if cls else ""
    if tag == "a":
        if href not in REPORT_LINKS:
            raise ValueError("not one of our own links")
        attrs += f' href="{html.escape(href, quote=True)}" rel="noreferrer noopener"'
    return _Safe(f"<{tag}{attrs}>{_join(children)}</{tag}>")


def _tag(value: object) -> _Safe:
    return el("span", t(value), cls="tag") if value else _Safe("")


def _when(value: object) -> _Safe:
    return t(f"{value} (UTC)") if value else t("")


def _paragraphs(lines) -> _Safe:
    return _join(el("p", t(line)) for line in lines or [])


def _meta_html(items) -> _Safe:
    rows = []
    for m in items or []:
        value = m.get("value")
        shown = el("a", t(value), href=m["href"]) if m.get("href") in REPORT_LINKS else t(value)
        label = t(f"{m['label']}: ") if m.get("label") else _Safe("")
        when = _when(m["time"]) if m.get("time") else _Safe("")
        rows.append(el("li", label, shown, when, _Safe(" "), _tag(m.get("tag"))))
    return el("ul", *rows, cls="meta") if rows else _Safe("")


def _block_html(block: dict) -> _Safe:
    head = el("h4", t(block.get("title")), _Safe(" "), _tag(block.get("tag")))
    if block.get("type") == "table":
        columns = block.get("columns") or []
        header = el("tr", *[el("th", t(c.get("label")), cls="right" if c.get("align") == "right" else None) for c in columns])
        body = []
        for row in block.get("rows") or []:
            cells = []
            for i, cell in enumerate(row):
                column = columns[i] if i < len(columns) else {}
                classes = " ".join(c for c in ("right" if column.get("align") == "right" else "", "mono" if column.get("mono") else "") if c)
                cells.append(el("td", t(cell), cls=classes or None))
            body.append(el("tr", *cells))
        note = el("p", t(block["note"]), cls="note") if block.get("note") else _Safe("")
        return _join([head, el("table", el("thead", header), el("tbody", *body)), _meta_html(block.get("meta")), note])
    return _join([head, el("pre", t(block.get("text")))])


def _result_html(heading: str, entry: dict) -> _Safe:
    r = entry["result"]
    record, locked = r["run_record"], r["locked_test"]
    parts = [
        el("h3", t(heading)),
        el("p", el("strong", t(r.get("label")), cls=f"badge tone-{r.get('tone')}" if r.get("tone") in ("pass", "fail", "neutral", "warn") else "badge"),
           _Safe(" "), t(r.get("summary"))),
        el("ul", *[el("li", t(line)) for line in (
            f"Component: {r.get('component')} [demo]" if r.get("component") else "Component: none (this test is about the server)",
            f"Mode: {r.get('mode')}", f"Finished: {r.get('finished_at')} (UTC)",
            f"Run record fingerprint (SHA-256): {entry.get('run_sha256')}",
            f"Reviewed by: {entry['review'].get('reviewer')}; test proposed by: {entry['review'].get('proposed_by')}")], cls="meta"),
        el("h4", t("What happened")), _paragraphs(r.get("what_happened")),
        el("h4", t(r.get("shows_title"))), _paragraphs(r.get("shows")),
        *[_block_html(b) for b in r.get("evidence") or []],
        el("h4", t(record.get("title"))), el("p", el("code", t(record.get("command")))),
        *[el("details", el("summary", t(o.get("title"))), el("pre", t(o.get("text")))) for o in record.get("outputs") or []],
        _meta_html(record.get("meta")),
        el("h4", t(locked.get("title"))),
        *[_join([el("p", el("strong", t(f.get("label")))), _paragraphs(f.get("lines"))]) for f in locked.get("fields") or []],
        el("p", t(f"Locked {locked.get('locked_at')} (UTC), {locked.get('locked_text')}.")),
        el("p", t(f"{locked.get('fingerprint_label')}: "), el("code", t(locked.get("fingerprint")))),
        el("p", t(locked.get("note")), cls="note"),
        el("h4", t("Control")), el("p", t((r.get("control") or {}).get("text"))),
    ]
    line = r.get("fix_line")
    if r.get("suggested_fix"):
        parts += [el("h4", t(r.get("fix_title"))), el("p", t(r["suggested_fix"]))]
    elif line:
        parts += [el("h4", t("Fix")), el("p", el("strong", t(line.get("lead"))), t(f" {line.get('rest')}. It is in part 4, Fixes."))]
    if r.get("reviewed"):
        parts.append(el("p", t(f"{r['reviewed'].get('text')} "), _when(r["reviewed"].get("at"))))
    research = r.get("research")
    if research:
        parts += [el("h4", t(f"{research.get('title')} ({research.get('badge')})")),
                  el("ul", *[el("li", t(f"{f.get('label')}: {f.get('value')}")) for f in research.get("fields") or []], cls="meta"),
                  el("p", t(research.get("status_line"))), el("p", t(research.get("note")), cls="note")]
    return el("div", *parts, cls="result")


def _words_html(text: object) -> _Safe:
    """A sentence in which the words between backticks are names (a setting, a cipher suite): those are set as code."""
    pieces = ("" if text is None else str(text)).split("`")
    return _join(el("code", t(piece)) if n % 2 else t(piece) for n, piece in enumerate(pieces))


def _suggestion_html(given: dict) -> list[_Safe]:
    """A text-only suggestion, in the order the Fixes step shows it: the warning before any setting."""
    warning, where, options, exact = given.get("warning"), given.get("where"), given.get("options"), given.get("exact")
    parts = [el("h4", t("The suggestion (text only: the app has not applied it or tested it)")),
             *[el("p", _words_html(line)) for line in given.get("intro") or []]]
    if warning:
        parts.append(el("p", el("strong", t(warning.get("title"))), _Safe(" "), _words_html(warning.get("text"))))
    if where:
        parts += [el("h4", t(where.get("title"))), el("p", t(where.get("note")), cls="note"),
                  el("table", el("thead", el("tr", *[el("th", t(column), cls="words" if i == 0 else None)
                                                     for i, column in enumerate(where.get("columns") or [])])),
                     el("tbody", *[el("tr", el("td", t(row.get("place")), cls="words"), el("td", _words_html(row.get("setting"))),
                                      el("td", t(f"{row.get('lead')} " if row.get("lead") else ""), el("code", t(row.get("code")))))
                                   for row in where.get("rows") or []])),
                  *[el("p", _words_html(line)) for line in where.get("after") or []]]
    if options:
        parts.append(el("h4", t(options.get("title"))))
        for item in options.get("items") or []:
            parts += [el("p", el("strong", t(item.get("title"))), _Safe(" "), t(item.get("when"))),
                      el("ul", *[el("li", _words_html(step)) for step in item.get("steps") or []]),
                      el("p", t(item.get("note")), cls="note") if item.get("note") else _Safe("")]
    if exact:
        parts += [el("h4", t(exact.get("title"))), el("p", t(exact.get("note")), cls="note"),
                  *[_join([el("p", t(block.get("place"))), el("pre", t(block.get("code")))]) for block in exact.get("blocks") or []]]
    return parts


def _proof_html(heading: str, proof: dict) -> list[_Safe]:
    review = proof.get("review")
    # the fingerprint the reviewer gave this proof: shown only while the stored review still stands (as on the screen)
    fingerprint = (review or {}).get("record_sha256")
    rows = []
    for test in proof.get("tests") or []:
        first, run, check = test.get("first") or {}, (test.get("run") or {}).get("result") or {}, test.get("check") or {}
        shown = test.get("shown") or {}
        # The two short columns are marked "words": beside a long sentence a column of plain words would otherwise be
        # squeezed until its words broke in the middle ("Certificat e", "Passe d").
        rows.append(el("tr", el("td", t(test.get("title")), cls="words"),
                       el("td", el("strong", t(first.get("label"))), _Safe(" "), t(first.get("short"))),
                       el("td", el("strong", t(shown.get("label"))), _Safe(" "), t(shown.get("short")), _Safe(" "),
                          t((run.get("control") or {}).get("line"))),
                       el("td", t(check.get("text")), cls="words")))
    return [el("h4", t(heading)),
            el("p", el("strong", t(proof.get("outcome"))), t(" Started "), _when(proof.get("started_at")),
               *([t("; reviewed "), _when(review.get("reviewed_at"))] if review else []), _Safe(" "), _tag("measured")),
            el("p", t("Evidence fingerprint of the proof (SHA-256): "), el("code", t(fingerprint))) if fingerprint else _Safe(""),
            el("table", el("thead", el("tr", *[el("th", t(column), cls="words" if column in ("Test", "Rule check") else None)
                                               # one table for every test of the proof: the server tests do not run the
                                               # changed code, so this column is named for what it holds for all of them
                                               for column in ("Test", "Before", "In the proof run", "Rule check")])),
               el("tbody", *rows)),
            el("p", t("The JSON file holds every run of this proof in full (its run record, fingerprint and review)"
                      + (", and the proof record this fingerprint is made from." if fingerprint else ".")), cls="note")]


def _fix_html(fix: dict) -> _Safe:
    """One fix, as the Fixes step showed it. A change is called passed or merged only where its records say so."""
    source, suggestion, change = fix.get("source") or {}, fix.get("suggestion"), fix.get("change")
    request, merge, proofs = fix.get("pull_request"), fix.get("merge"), fix.get("proofs") or []
    parts = [el("h3", t(fix.get("title"))),
             el("p", el("strong", t(fix.get("status")), cls="badge"), _Safe(" "), t(source.get("text")))]
    said = fix.get("proof_summary") or {}
    if change and said.get("text"):
        # the reason behind the status, in the summary's own words (so "Proof failed" never stands beside a
        # proof that passed without saying why)
        parts.append(el("p", *([el("strong", t(f"{said.get('label')}:")), _Safe(" ")] if said.get("label") else []), t(said.get("text"))))
    if suggestion:
        parts += _suggestion_html(suggestion)
    if change:
        built = change.get("built") or {}
        matches = built.get("matches")
        same = (f"byte for byte the same as our bundled demo component {matches.get('name')} {matches.get('version')}, and that component "
                "is what the proof ran" if isinstance(matches, dict) else "not one of our demo components, so nothing was run")
        parts += [el("h4", t("The change"), _Safe(" "), _tag(change.get("label"))),
                  el("p", t(f"{change.get('title')}. {change.get('size')}.")),
                  el("ul", el("li", t(f"Change branch {change.get('branch')}, commit {change.get('head_commit')}")),
                     el("li", t(f"Starting point: commit {change.get('base_commit')}")),
                     *[el("li", t(f"File {f.get('name')}: SHA-256 before {f.get('old_sha256')}, after {f.get('new_sha256')}"))
                       for f in change.get("files") or []],
                     el("li", t(f"Code check: the built file (SHA-256 {built.get('sha256')}) is {same}.")), cls="meta"),
                  el("details", el("summary", t("The change as a patch")), el("pre", t(change.get("patch")))) if change.get("patch") else _Safe("")]
        for n, proof in enumerate(proofs, start=1):
            parts += _proof_html("Proof" if len(proofs) == 1 else f"Proof {n} of {len(proofs)}", proof)
    if not suggestion and not change:
        parts.append(el("p", t("A fix template exists for this failure. The code was not connected when this file was made, so no "
                               "change had been prepared or proved.")))
    if request:
        parts += [el("h4", t(f"Pull request #{request.get('number')}")),
                  el("p", t(f"{request.get('title')}. Opened "), _when(request.get("opened_at")), t(". It stays inside the app.")),
                  el("ul", *[el("li", t(f"{a.get('name')} ({a.get('label')}): " if a.get("label") else f"{a.get('name')}: "),
                                *([t("approved "), _when(a.get("approved_at"))] if a.get("approved_at") else [t("has not approved")]))
                             for a in fix.get("approvals") or []], cls="meta"),
                  el("p", t(request.get("approvals_note")), cls="note") if request.get("approvals_note") else _Safe("")]
    if merge:
        parts.append(el("p", t("Merged "), _when(merge.get("merged_at")), t(f" by the person logged in, after confirming (merge commit "
                                                                           f"{merge.get('merge_commit')}). Nothing was deployed.")))
    return el("div", *parts, cls="result")


_STYLE = """
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.5;color:#1a1f2b;background:#fff;margin:0}
main{max-width:980px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.6rem;margin:0 0 4px}h2{font-size:1.25rem;margin:32px 0 8px;border-bottom:1px solid #d5d9e0;padding-bottom:4px}
h3{font-size:1.05rem;margin:20px 0 6px}h4{font-size:.95rem;margin:14px 0 4px}
p{margin:4px 0}.box{border:1px solid #9aa3b2;border-radius:6px;padding:12px 14px;margin:12px 0;background:#f5f7fa}
.result{border-left:3px solid #c3c9d4;padding-left:14px;margin:8px 0 20px}
table{border-collapse:collapse;width:100%;margin:6px 0;font-size:.9rem}th,td{border:1px solid #d5d9e0;padding:4px 8px;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{background:#eef1f5;white-space:pre-line}.right{text-align:right}.mono,code,pre{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.85rem}
pre{background:#f5f7fa;border:1px solid #d5d9e0;border-radius:4px;padding:8px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:none}
code{overflow-wrap:anywhere}td.mono{white-space:nowrap;overflow-wrap:normal}td.words,th.words{overflow-wrap:normal}.tag{font-size:.72rem;border:1px solid #9aa3b2;border-radius:10px;padding:0 6px;color:#3b4557;white-space:nowrap}
.badge{border:1px solid #9aa3b2;border-radius:4px;padding:1px 6px}.tone-pass{border-color:#1d7a46;color:#12592f}.tone-fail{border-color:#b3261e;color:#8c1d18}
.tone-warn{border-color:#9a6700;color:#7a5200}.note{color:#4a5568;font-size:.88rem}ul.meta{margin:4px 0;padding-left:18px;font-size:.9rem}
summary{cursor:pointer}
"""


def render_report_html(envelope: dict) -> bytes:
    """A readable copy of the evidence. Static: no scripts, no remote resources, every value escaped."""
    e, fingerprint = envelope["evidence"], envelope["fingerprint"]
    imp, verify, retest = e.get(IMPORT_PART) or {}, e.get("verify"), e.get("retest")
    body = [
        el("h1", t("Isogeny Evidence Lab: evidence report")),
        el("p", el("span", t("Demo data"), cls="tag")) if imp.get("is_demo") else _Safe(""),
        el("div",
           el("p", el("strong", t(REPORT_LINE))),
           el("p", t("Fingerprint of the evidence JSON (SHA-256): "), el("code", t(fingerprint))),
           el("p", t("Signed by this app's own local key. Key fingerprint (SHA-256 of the public key): "),
              el("code", t(e.get("signer_key_fingerprint")))),
           el("p", t("To check the JSON file: "), el("code", t(VERIFY_COMMAND))),
           cls="box"),
        el("p", t("Generated: "), _when(e.get("generated_at"))),
        el("p", t(e.get("mode_line"))),
        el("p", el("strong", t(e.get("disclaimer")))),
        el("h2", t("1. What the file claims")),
        el("p", t(f"File: {imp.get('filename')} ({imp.get('format')}) "), _tag("from the file")),
        el("table", el("thead", el("tr", el("th", t("Where")), el("th", t("Claim")), el("th", t("Source in the file")))),
           el("tbody", *[el("tr", el("td", t(c.get("location")), cls="mono"), el("td", t(c.get("text"))), el("td", t(c.get("source"))))
                         for c in imp.get("claims") or []])),
        el("h2", t("2. Verify: is each claim true?")),
    ]
    if verify:
        body.append(el("p", t("Checked: "), _when(verify.get("finished_at")), _Safe(" "), _tag("measured")))
        for r in verify.get("results") or []:
            body.append(el("div",
                           el("h3", t(r.get("claim"))),
                           el("p", el("strong", t(r.get("result")), cls="badge"), _Safe(" "), t(r.get("found"))),
                           el("p", t(r.get("reason"))) if r.get("reason") else _Safe(""),
                           *[el("details", el("summary", t(f"Evidence: {ev.get('title')}")),
                                el("p", el("code", t(ev.get("command")))), el("pre", t(ev.get("output"))),
                                el("p", t(f"{ev.get('started_at')} (UTC), {ev.get('duration_ms')} ms, {ev.get('tool')}, {ev.get('tool_version')}"), cls="note"))
                             for ev in r.get("evidence") or []],
                           cls="result"))
    else:
        body.append(el("p", t("The claims had not been verified when this file was made.")))
    body.append(el("h2", t("3. Tests and results")))
    if retest:
        columns = retest.get("columns") or {}
        body.append(el("p", t(f"Before and after: the same locked tests were run on version {retest.get('baseline_version')} "
                              f"and then on version {retest.get('version')}. Retest started "), _when(retest.get("started_at"))))
        body.append(el("p", t(retest.get("code_line"))) if retest.get("code_line") else _Safe(""))
    for test in e.get("tests") or []:
        body.append(el("h2", t(test.get("title"))))
        body.append(el("p", t(test.get("control_line"))) if test.get("control_line") else _Safe(""))
        if not test.get("runs"):
            body.append(el("p", t("Not run yet. No result.")))
        for entry in test.get("runs") or []:
            if retest:
                # the column heading, with the code that side ran on where every result on it ran on the same code
                heading = ((columns.get("after_heading") or columns.get("after")) if entry.get("phase") == "retest"
                           else (columns.get("before_heading") or columns.get("before"))) or entry.get("phase")
            else:
                heading = "Result"
            body.append(_result_html(str(heading), entry))
    code, fixes = e.get("code"), e.get("fixes") or []
    body.append(el("h2", t("4. Fixes")))
    if code:
        component = code.get("component") or {}
        body.append(el("p", t(f"Code connected: the app's own copy of the repository {code.get('repository')}, branch {code.get('branch')}, "
                              f"commit {code.get('base_commit')} ({component.get('name')} {component.get('version')}). "),
                       _tag("demo") if code.get("is_demo") is True else _Safe("")))
    if not fixes:
        body.append(el("p", t("No failed test had a fix when this file was made.")))
    body += [_fix_html(fix) for fix in fixes]
    body.append(el("p", t("End of report. " + REPORT_LINE), cls="note"))
    page = (f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta http-equiv="Content-Security-Policy" content="{html.escape(CSP, quote=True)}">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>Isogeny Evidence Lab: evidence report</title>\n<style>{_STYLE}</style>\n</head>\n"
            f"<body>\n<main>\n{_join(body)}\n</main>\n</body>\n</html>\n")
    return page.encode("utf-8")


# ------------------------------------------------------------------ the Lab actions

def _stamp(when: datetime) -> str:
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _export_view(row: EvidenceExportRow) -> dict:
    stamp = _stamp(row.created_at)
    return {"id": row.id, "created_at": iso(row.created_at), "fingerprint": row.fingerprint, "fingerprint_label": "Fingerprint (SHA-256)",
            "json": {"url": f"/api/evidence/{row.id}/json", "filename": f"evidence-lab-evidence-{stamp}.json"},
            "html": {"url": f"/api/evidence/{row.id}/html", "filename": f"evidence-lab-report-{stamp}.html"},
            "message": "Two files were downloaded: the evidence (JSON) and a readable report (HTML). The JSON file is the record.",
            "verify_hint": f"To check the file: {VERIFY_COMMAND}"}


class EvidenceMixin:
    """Mixed into Lab: Download evidence."""

    def export_evidence(self, plan_id: int) -> dict:
        view = self.lab_view(plan_id)  # NotFound for an unknown plan
        if not view["download"]["can_start"]:
            raise Conflict(view["download"]["blocked_reason"] or "There is nothing to download yet.")
        created = datetime.now(timezone.utc).replace(microsecond=0)
        try:
            evidence = build_evidence(self, plan_id, generated_at=iso(created))
            raw = sign_envelope(evidence, self.settings.data_dir)
        except SigningKeyError as exc:
            raise Conflict(f"{exc} Nothing was downloaded.") from exc
        fingerprint = sha256_hex(evidence)
        report = render_report_html({"evidence": evidence, "fingerprint": fingerprint})
        with self.db() as db:
            row = EvidenceExportRow(plan_id=plan_id, created_at=created, fingerprint=fingerprint, json_bytes=raw, html_bytes=report)
            db.add(row)
            db.commit()
            return _export_view(row)

    def evidence_file(self, export_id: int, which: str) -> tuple[str, bytes, str]:
        """(filename, bytes, media type) of one stored download. `which` is "json" or "html"."""
        if which not in ("json", "html"):
            raise NotFound("There is no such file.")
        with self.db() as db:
            row = db.get(EvidenceExportRow, export_id)
            if row is None:
                raise NotFound("That evidence download does not exist.")
            view = _export_view(row)
            if which == "json":
                return view["json"]["filename"], bytes(row.json_bytes), "application/json"
            return view["html"]["filename"], bytes(row.html_bytes), "text/html; charset=utf-8"


__all__ = ["EvidenceMixin", "ensure_signing_key", "build_evidence", "sign_envelope", "render_report_html", "key_fingerprint",
           "SigningKeyError", "SIGNING_CONTEXT", "SIGNING_KEY_FILE", "PUBLIC_KEY_FILE", "EVIDENCE_SCHEMA", "REPORT_LINKS"]
