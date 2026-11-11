"""The job runner: a limit on how many run at once, the three statuses, and a job that crashes."""
import threading
import time

import pytest

from app import testlab
from app.db import ReviewRow, TestRunRow
from app.jobs import JobRunner
from conftest import demo_plan, result_of


def test_never_more_than_the_limit_and_the_statuses_in_order():
    runner = JobRunner(max_parallel=2)
    running, peak, release = [0], [0], threading.Event()
    lock = threading.Lock()

    def work(job):
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        job.progress("working", 50)
        release.wait(5)
        with lock:
            running[0] -= 1

    try:
        jobs = [runner.submit((n, "first"), work, group="plan") for n in range(5)]
        deadline = time.monotonic() + 5
        while sum(j.status == "running" for j in jobs) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert sorted(j.status for j in jobs) == ["running", "running", "waiting", "waiting", "waiting"]
        assert runner.busy("plan") and not runner.busy("another plan")
        with pytest.raises(ValueError):
            runner.submit((0, "first"), work)  # no second live job for the same test
        release.set()
        assert runner.wait_idle(5, group="plan")
        assert [j.status for j in jobs] == ["done"] * 5 and peak[0] == 2 and runner.most_at_once == 2
        assert all(j.queued_at <= j.started_at <= j.finished_at for j in jobs)
        assert runner.submit((0, "first"), lambda job: None).key == (0, "first")  # once done, it can be run again
        assert runner.wait_idle(5)
    finally:
        release.set()
        runner.stop()


def test_a_job_whose_work_raises_still_ends():
    runner = JobRunner(max_parallel=1)
    try:
        def bad(job):
            raise RuntimeError("boom")
        job = runner.submit((1, "first"), bad)
        after = runner.submit((2, "first"), lambda job: job.log("fine"))
        assert runner.wait_idle(5)
        assert job.status == "done" and job.error == "RuntimeError" and after.status == "done" and after.error is None
    finally:
        runner.stop()


def test_run_all_really_overlaps_jobs(demo_flow):
    assert 2 <= demo_flow.most_at_once <= demo_flow.lab.settings.max_jobs == 4
    with demo_flow.lab.db() as db:
        first = [r for r in db.query(TestRunRow).all() if r.phase == "first"]
    spans = sorted((r.started_at, r.finished_at) for r in first)
    assert any(a_end > b_start for (_, a_end), (b_start, _) in zip(spans, spans[1:])), "two tests were running at the same moment"


def test_max_jobs_setting_is_respected(tmp_path):
    from conftest import make_lab
    lab = make_lab(tmp_path, max_jobs=1)
    try:
        plan = demo_plan(lab)
        lab.remove_test(plan.id, plan.item["official_vectors"])
        lab.remove_test(plan.id, plan.item["speed_size"])
        view = lab.run_all(plan.id)
        assert view["max_parallel"] == 1 and view["running"] is True
        statuses = {t["status"] for t in view["tests"]}
        assert statuses <= {"waiting", "running", "done"} and "waiting" in statuses
        waiting = next(t for t in view["tests"] if t["status"] == "waiting")
        assert waiting["status_text"] == "Waiting" and waiting["progress"]["text"] == "1 tests run at once; starts when one finishes"
        lab.wait_until_idle(plan.id, 60)
        assert lab.jobs.most_at_once == 1
        assert [t["status"] for t in lab.plan_view(plan.id)["tests"]] == ["done"] * 3
    finally:
        lab.stop()


def test_a_crashing_test_still_leaves_a_run_and_a_review(lab, monkeypatch):
    def crash(spec, ctx):
        raise RuntimeError("the runner fell over")
    monkeypatch.setattr(testlab, "execute", crash)
    plan = demo_plan(lab)
    lab.run_test(plan.id, plan.item["certificate"])
    lab.wait_until_idle(plan.id, 30)
    result = result_of(lab.lab_view(plan.id), "certificate")
    assert result["label"] == "Couldn't run (the test could not be run)"
    with lab.db() as db:
        assert db.query(TestRunRow).count() == 1 and db.query(ReviewRow).count() == 1
        assert db.query(TestRunRow).one().raw["problem"]["code"] == "harness_error"


def test_failed_runs_are_kept_and_a_rerun_adds_a_new_record(lab):
    plan = demo_plan(lab)
    for _ in range(2):
        lab.run_test(plan.id, plan.item["bad_signatures"])
        lab.wait_until_idle(plan.id, 60)
    with lab.db() as db:
        runs = db.query(TestRunRow).order_by(TestRunRow.id).all()
        assert len(runs) == 2 and runs[0].spec_hash == runs[1].spec_hash and db.query(ReviewRow).count() == 2
    assert result_of(lab.lab_view(plan.id), "bad_signatures")["run_id"] == runs[1].id  # the latest run is the one shown


def test_a_test_interrupted_by_closing_the_app_writes_no_record(tmp_path, monkeypatch):
    """Ctrl+C while a test waits behind a long one: the test goes on after the demo server has stopped. It must
    not record "the server did not answer" (that was the shutdown, not the server); it must record nothing."""
    from conftest import make_lab
    lab = make_lab(tmp_path)
    holding, release, ended = threading.Event(), threading.Event(), threading.Event()
    real_execute, real_run_one = testlab.execute, lab._run_one

    def held_execute(spec, ctx):
        holding.set()
        release.wait(30)            # stands in for waiting behind the speed measurement
        return real_execute(spec, ctx)

    def run_one(job, args):
        try:
            real_run_one(job, args)
        finally:
            ended.set()
    monkeypatch.setattr(testlab, "execute", held_execute)
    monkeypatch.setattr(lab, "_run_one", run_one)
    stopped = False
    try:
        plan = demo_plan(lab)
        lab.run_test(plan.id, plan.item["certificate"])
        assert holding.wait(10)
        monkeypatch.setattr(lab.jobs, "wait_idle", lambda timeout, group=None: False)   # the 20 s grace, run out
        lab.stop()
        stopped = True
        assert lab.demo.running is False
        release.set()               # the held test now carries on against a demo server that is gone
        assert ended.wait(60)
        with lab.db() as db:
            assert db.query(TestRunRow).count() == 0 and db.query(ReviewRow).count() == 0
        again = make_lab(tmp_path)   # the app, started again on the same data folder
        try:
            card = next(t for t in again.plan_view(plan.id)["tests"] if t["kind"] == "certificate")
            assert card["status"] == "not_run" and card["result"] is None
        finally:
            again.stop()
    finally:
        release.set()
        if not stopped:
            lab.stop()
