"""The trial instrument for public copies made by sandbox research: one arm of one registered experiment.

Otto's harness runs this file, pinned by SHA-256, once per arm, and reads the numbers it writes to $OTTO_METRICS. It
decides nothing: the numbers are counts read from the separate reviewer's review of the run, and the harness judges
them against thresholds frozen before the first run. (`trial.py`, the instrument of the pinned libraries, is not
changed: frozen means frozen.)

    trial_sandbox.py check --design designs/<id>.json --set sandbox/<advisory>/set-a-<id>.json --library NAME --version V
                           --report subject|reference|control [--agree-with sandbox/<advisory>/set-b-<id>.json]
        Lock the advisory check of that design for NAME V, run it on the public copy the set holds, and read the review.
        Writes {"right", "wrong", "total", "agree"}. With --agree-with the same check is also run on the second set,
        whose asking code was written apart: `agree` is on how many cases the two pieces of asking code handed back the
        same answer. Without it, `agree` is the number of cases (there is nothing to disagree with).

    trial_sandbox.py fix --fix fixes/<id>.json --set sandbox/<advisory>/set-a-<id>.json --version V
        Run every pass-or-fail test the fix file lists on NAME V. Writes {"failing", "tests"}.

Everything runs through Evidence Lab's own path, in a scratch copy of the app with Sandbox research on and exactly this
one copy set in its store: the scanner-file reader, the locked test, the job runner (the public copy in its own locked
container, no network) and the separate reviewer. The asking code never sees a right answer: the runner sends only the
questions, and the reviewer compares outside.

A test that could not run, or a run that can't be trusted, is not a number: the script stops with an error (exit code
3), which the harness records as an infrastructure failure, never as a result.
"""
import argparse
import json
import os
import socket
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = Path(os.environ.get("EVIDENCE_LAB_BACKEND") or HERE.parents[1] / "backend")
sys.path.insert(0, str(BACKEND))
# This script's scratch copies of the app are sandbox copies by definition, and nothing in them looks by itself.
os.environ["EVIDENCE_LAB_SANDBOX_RESEARCH"] = "1"
os.environ["EVIDENCE_LAB_WATCH_CLOCK"] = "off"

from sqlalchemy import select  # noqa: E402

from app.config import load_settings  # noqa: E402
from app.db import ImportRow, PlanItemRow, ReviewRow, TestRunRow, TestSpecRow  # noqa: E402
from app.engine import vectors  # noqa: E402
from app.errors import Conflict  # noqa: E402
from app.lab.hub import Lab  # noqa: E402
from app.lab.testlab import run_record  # noqa: E402
from app.otto import checks, designs  # noqa: E402
from app.sandbox import copies  # noqa: E402

NOT_A_RESULT = 3
WAIT_SECONDS = 840.0
INFO = {"plain_name": "(trial)", "quote": "(trial on a public copy)",
        "source": {"title": "(trial)", "url": "", "published": "", "checked": ""}}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _stop(text: str) -> None:
    print(f"not a result: {text}", file=sys.stderr)
    raise SystemExit(NOT_A_RESULT)


def _inside(path: str) -> Path:
    full = (HERE / path).resolve()
    if HERE not in full.parents:
        _stop("the file is outside the lab folder")
    return full


def _read(path: str) -> dict:
    return json.loads(_inside(path).read_text(encoding="utf-8"))


def _set(path: str) -> dict:
    try:
        return copies.read_set(_inside(path).read_bytes())
    except (OSError, copies.CopyError) as exc:
        _stop(f"the copy set's record could not be read ({exc})")
        raise


def _open(scratch: str, library: str, version: str, record: dict):
    """A scratch copy of the app with Sandbox research on, this one copy set in its store, and one scanner file that
    names one program: (lab, plan id, the program)."""
    settings = load_settings(data_dir=Path(scratch) / "data", demo_tls_port=_free_port())
    copies.write_set(settings.sandbox_dir, record)
    lab = Lab(settings, allow_external_demo_server=True)
    lab.start()
    try:
        lab.set_sandbox(on=True)
    except Conflict as refused:
        lab.stop()
        _stop(f"Sandbox research could not be turned on in the scratch copy ({refused})")
    if not lab.mode.real_images.get(copies.family_of(record)):
        lab.stop()
        _stop("the image of the public copies is not on this computer, or is not the one its record names")
    line = f"location,type,claim,value\n{library} {version},software,signature_algorithm,ECDSA P-256\n"
    imp = lab.import_file("trial.csv", line.encode("utf-8"))
    plan = lab.ensure_plan(imp["id"])
    with lab.db() as db:
        claims = lab._claims(db.get(ImportRow, imp["id"]))
    fitting = checks.programs_that_fit(claims)
    if len(fitting) != 1 or (fitting[0]["component"], fitting[0]["version"]) != (library, version):
        lab.stop()
        _stop(f"{library} {version} is not a program this app can run an advisory check on")
    return lab, plan["id"], fitting[0]


def _add(lab, plan_id: int, design: dict, program: dict) -> int:
    with lab._plan_lock, lab.db() as db:
        item, _, _ = checks.add_design_item(lab, db, lab._plan(db, plan_id), design, checks.TRIAL_PACK, INFO, program)
        db.commit()
        return item.id


def _newest(lab, item_id: int):
    with lab.db() as db:
        run = db.scalars(select(TestRunRow).where(TestRunRow.plan_item_id == item_id).order_by(TestRunRow.id.desc())).first()
        if run is None:
            _stop("the test left no run record")
        verdict = lab._verdict(db, run)
        review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == run.id)).first()
        if verdict is None or review is None:
            _stop("the run has no review")
        return verdict, dict(review.detail or {}), run_record(run)


def _run(lab, plan_id: int, item_ids: list[int]) -> None:
    for item_id in item_ids:
        lab.run_test(plan_id, item_id)
        try:
            lab.wait_until_idle(plan_id, WAIT_SECONDS)
        except TimeoutError:
            _stop("the test did not finish in time")


def _write(metrics: dict) -> None:
    out = os.environ.get("OTTO_METRICS")
    if out:
        Path(out).write_text(json.dumps(metrics, sort_keys=True), encoding="utf-8")
    print(json.dumps(metrics, sort_keys=True))


def _one(design: dict, library: str, version: str, record: dict):
    """One run of the design's check on one copy: (the reviewer's verdict, the review's detail, the run record)."""
    with tempfile.TemporaryDirectory(prefix="otto-sandbox-trial-") as scratch:
        lab, plan_id, program = _open(scratch, library, version, record)
        try:
            item_id = _add(lab, plan_id, design, program)
            _run(lab, plan_id, [item_id])
            return _newest(lab, item_id)
        finally:
            lab.stop()


def _answers(record: dict) -> dict:
    return ((record.get("raw") or {}).get("subject") or {}).get("answers") or {}


def check(args) -> None:
    design = designs.check_design(_read(args.design))
    first = _set(args.set)
    verdict, detail, record = _one(design, args.library, args.version, first)
    code = verdict["code"]
    print(f"advisory check for {design['advisory']} on {args.library} {args.version} (copy set {first['id']}): review code {code}, "
          f"mode {record.get('mode')}")
    if code == "couldnt_run":
        _stop(f"the check could not run ({verdict.get('reason_code')})")
    wanted = set(design["cases"]["ids"])
    total = len(wanted)
    if args.report == "subject":
        if code not in ("passed", "failed"):
            _stop("the run can't be trusted, so the library's answers are not counted")
        right = int(detail["right"])
    elif args.report == "reference":
        right = int(detail["reference"][designs.CASE_SET]["right"])
    else:   # the control's raw answers against the published ones
        answers = ((record.get("raw") or {}).get("control") or {}).get("answers") or {}
        cases = [c for c in vectors.load_wycheproof(designs.CASE_SET).cases if c.id in wanted]
        if set(answers) != wanted:
            _stop("the control did not answer every case")
        right = sum(1 for c in cases if answers.get(c.id) == ("accept" if c.expected == "valid" else "reject"))
    agree = total
    if args.agree_with:
        second = _set(args.agree_with)
        if second["asking"]["sha256"] == first["asking"]["sha256"]:
            _stop("the second copy set holds the same asking code, so there is nothing to compare")
        other_verdict, _, other_record = _one(design, args.library, args.version, second)
        if other_verdict["code"] == "couldnt_run":
            _stop("the check could not run with the second piece of asking code")
        mine, theirs = _answers(record), _answers(other_record)
        if set(mine) != wanted or set(theirs) != wanted:
            _stop("a piece of asking code did not answer every case")
        agree = sum(1 for case_id in wanted if mine[case_id] == theirs[case_id])
        print(f"the two pieces of asking code gave the same answer on {agree} of {total} cases")
    _write({"right": right, "wrong": total - right, "total": total, "agree": agree})


def fix(args) -> None:
    plan_file = _read(args.fix)
    if plan_file.get("schema") != "isogeny.advisory-fix/1" or args.version not in (plan_file.get("from"), plan_file.get("to")):
        _stop("the fix file does not name this version")
    library = plan_file["library"]
    record = _set(args.set)
    made = [designs.check_design(_read(entry["file"])) for entry in plan_file["checks"]]
    for entry, design in zip(plan_file["checks"], made, strict=True):
        if designs.design_sha256(design) != entry["design_sha256"]:
            _stop("a design file is not the one the fix file names")
    with tempfile.TemporaryDirectory(prefix="otto-sandbox-trial-") as scratch:
        lab, plan_id, program = _open(scratch, library, args.version, record)
        try:
            with lab.db() as db:
                standard = []
                for item in db.scalars(select(PlanItemRow).where(PlanItemRow.plan_id == plan_id).order_by(PlanItemRow.position)).all():
                    kind = db.get(TestSpecRow, item.spec_hash).kind
                    if kind in plan_file["tests"]:
                        standard.append((kind, item.id))
            if sorted(k for k, _ in standard) != sorted(plan_file["tests"]):
                _stop("the plan does not hold exactly the standard tests the fix file names")
            added = [(f"advisory check {d['advisory']}", _add(lab, plan_id, d, program)) for d in made]
            items = standard + added
            _run(lab, plan_id, [item_id for _, item_id in items])
            codes = [(name, _newest(lab, item_id)[0]["code"]) for name, item_id in items]
        finally:
            lab.stop()
    for name, code in codes:
        print(f"{library} {args.version}: {name}: {code}")
    unusable = [name for name, code in codes if code not in ("passed", "failed")]
    if unusable:
        _stop("no usable result for: " + ", ".join(unusable))
    _write({"failing": sum(1 for _, code in codes if code != "passed"), "tests": len(codes)})


def main() -> None:
    parser = argparse.ArgumentParser(prog="trial_sandbox.py")
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("check")
    one.add_argument("--design", required=True)
    one.add_argument("--set", required=True)
    one.add_argument("--library", required=True)
    one.add_argument("--version", required=True)
    one.add_argument("--report", required=True, choices=("subject", "reference", "control"))
    one.add_argument("--agree-with", dest="agree_with", default=None)
    one.set_defaults(run=check)
    two = sub.add_parser("fix")
    two.add_argument("--fix", required=True)
    two.add_argument("--set", required=True)
    two.add_argument("--version", required=True)
    two.set_defaults(run=fix)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
