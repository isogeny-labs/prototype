"""The trial instrument of Otto's research side: one arm of one registered experiment.

Otto's harness runs this file, pinned by SHA-256, once per arm, and reads the numbers it writes to $OTTO_METRICS.
It decides nothing: the numbers are counts, and the harness judges them against thresholds frozen before the run.

    trial.py check --design designs/<id>.json --library NAME --version V --report subject|reference|control
        Lock the advisory check of that design for NAME V, run it, and read the review. Writes {"right", "wrong",
        "total"} for one of three columns of the same run: the program itself (as the reviewer scored it), the
        app's reference library (as the reviewer scored it), or the accept-everything control (its raw answers
        against the published ones).

    trial.py fix --fix fixes/<id>.json --version V
        Run every pass-or-fail test the fix file lists on NAME V: the standard tests of the plan and the advisory
        checks. Writes {"failing", "tests"}: how many did not read Passed.

Everything runs through Evidence Lab's own path: the scanner-file reader, the locked test, the job runner and the
separate reviewer. So a real library still runs only in its locked-down container (isolated mode), exactly as when
a person presses Run. A test that could not run, or a run that can't be trusted, is not a number: the script stops
with an error, which the harness records as an infrastructure failure, never as a result.

Speed is not part of a fix trial: timings hold only for the computer they are measured on.
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

from sqlalchemy import select  # noqa: E402

from app.config import load_settings  # noqa: E402
from app.db import ImportRow, PlanItemRow, ReviewRow, TestRunRow, TestSpecRow  # noqa: E402
from app.engine import vectors  # noqa: E402
from app.lab.hub import Lab  # noqa: E402
from app.lab.testlab import run_record  # noqa: E402
from app.otto import checks, designs  # noqa: E402

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


def _read(path: str) -> dict:
    full = (HERE / path).resolve()
    if HERE not in full.parents:
        _stop("the file is outside the lab folder")
    return json.loads(full.read_text(encoding="utf-8"))


def _open(scratch: str, library: str, version: str):
    """A scratch copy of the app with one scanner file that names one program: (lab, plan id, the program)."""
    settings = load_settings(data_dir=Path(scratch) / "data", demo_tls_port=_free_port())
    lab = Lab(settings, allow_external_demo_server=True)
    lab.start()
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
    """(the review as the read gate lets it through, the stored review's detail, the run record) of an item's newest run."""
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


def check(args) -> None:
    design = designs.check_design(_read(args.design))
    with tempfile.TemporaryDirectory(prefix="otto-trial-") as scratch:
        lab, plan_id, program = _open(scratch, args.library, args.version)
        try:
            item_id = _add(lab, plan_id, design, program)
            _run(lab, plan_id, [item_id])
            verdict, detail, record = _newest(lab, item_id)
        finally:
            lab.stop()
    code = verdict["code"]
    print(f"advisory check for {design['advisory']} on {args.library} {args.version}: review code {code}, mode {record.get('mode')}")
    if code == "couldnt_run":
        _stop(f"the check could not run ({verdict.get('reason_code')})")
    total = len(design["cases"]["ids"])
    if args.report == "subject":
        if code not in ("passed", "failed"):
            _stop("the run can't be trusted, so the program's answers are not counted")
        right = int(detail["right"])
    elif args.report == "reference":
        right = int(detail["reference"][designs.CASE_SET]["right"])
    else:   # the control's raw answers against the published ones
        answers = ((record.get("raw") or {}).get("control") or {}).get("answers") or {}
        wanted = set(design["cases"]["ids"])
        cases = [c for c in vectors.load_wycheproof(designs.CASE_SET).cases if c.id in wanted]
        if set(answers) != wanted:
            _stop("the control did not answer every case")
        right = sum(1 for c in cases if answers.get(c.id) == ("accept" if c.expected == "valid" else "reject"))
    _write({"right": right, "wrong": total - right, "total": total})


def fix(args) -> None:
    plan_file = _read(args.fix)
    if plan_file.get("schema") != "isogeny.advisory-fix/1" or args.version not in (plan_file.get("from"), plan_file.get("to")):
        _stop("the fix file does not name this version")
    library = plan_file["library"]
    made = [designs.check_design(_read(entry["file"])) for entry in plan_file["checks"]]
    for entry, design in zip(plan_file["checks"], made):  # noqa: B905
        if designs.design_sha256(design) != entry["design_sha256"]:
            _stop("a design file is not the one the fix file names")
    with tempfile.TemporaryDirectory(prefix="otto-trial-") as scratch:
        lab, plan_id, program = _open(scratch, library, args.version)
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
    parser = argparse.ArgumentParser(prog="trial.py")
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("check")
    one.add_argument("--design", required=True)
    one.add_argument("--library", required=True)
    one.add_argument("--version", required=True)
    one.add_argument("--report", required=True, choices=("subject", "reference", "control"))
    one.set_defaults(run=check)
    two = sub.add_parser("fix")
    two.add_argument("--fix", required=True)
    two.add_argument("--version", required=True)
    two.set_defaults(run=fix)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
