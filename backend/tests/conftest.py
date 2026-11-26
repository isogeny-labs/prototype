import socket
import ssl
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.servers.demo_server import TlsServer, ensure_demo_certificate, make_server_context  # noqa: E402
from app.main import create_app  # noqa: E402

PASSWORD = "test-only-passphrase"  # a throwaway value for tests, not a real credential

# Every JSON answer a test gets from the app is checked against the shape its route declares (tests/api_shapes.py).
pytest_plugins = ("api_shapes",)


# ---------------------------------------------------------------- the two sets: fast (everyday) and full


def pytest_addoption(parser):
    parser.addoption(
        "--full",
        action="store_true",
        default=False,
        help="run every test, the slow ones too (Docker, real libraries, timing, long flows)",
    )


# Files whose tests read one long demo walk (run all, proof, retest, speed rounds ...) built once for the file. The
# walk alone takes 10 to 80 seconds, so every test that reads it is in the slow set too (file name: the walk's fixture).
SLOW_SHARED_WALKS = {
    "test_accuracy.py": "migration_answers",
    "test_vectors.py": "official_run",
    "test_fixes_view.py": "flow",
    "test_changes.py": "fix_flow",
    "test_fixes_api.py": "app_client",
    "test_multi_target.py": "flow",
    "test_ledger.py": "measured",  # phase 5b: the Acme Pay demo verified and measured for Migration, built for that file
    "test_otto_fix.py": "failed",  # phase 5c: the Acme Pay demo with a test pack installed and every test run, built for each test
    # phase 5c, second part: the Acme Pay demo measured, a pack installed, its check run and the evidence downloaded, built
    # once for that file. The walk is short, but some thirty tests read it (the tamper cases of the verify command), and
    # with them the fast set had reached five minutes on a slow day.
    "test_otto_evidence.py": "ran",
    # 22 November 2026: the whole Acme Pay demo (every test, a retest, Measure status, a try, Apply and Roll back), for the
    # source tags of every view
    "test_source_tags.py": "tagged",
    # 19 November 2026 (Kevin's answer to the phase 6 plan's first open question: move the three oldest shared walks to
    # the slow set, no new package). The fast set had reached five minutes. These three are the `flow` walks of phase
    # 3a (the fix with its two proofs, pull request, merge and retest), phase 4a (the migration demo measured once) and
    # phase 4b (a change tried, approved, applied and rolled back). Their tests still run with --full and in the nightly
    # checks; the answers they stand on are also graded on every push by the accuracy check.
    "test_fixes_evidence.py": "flow",
    "test_migration.py": "flow",
    "test_phase4b.py": "flow",
    # 19 November 2026, phase 6: the Otto panel's shared walk (tests/assistant/assistant_walk.py). It takes about 40
    # seconds to make (the Acme Pay demo verified, run, measured, with decisions and every typed sentence asked at
    # each stage), and with it the fast set took 6 min 49 s on the build machine. By the rule above its readers are
    # slow. What stays in the everyday run for the panel: the rules that read a sentence, the lists and the unit
    # tests (about 120 tests that need no walk). Run the rest with: pytest -q tests/assistant --full (about 80 seconds).
    "test_read.py": "assistant_walk",
    "test_name.py": "assistant_walk",
    "test_panel_decision.py": "assistant_walk",
    "test_reads_only.py": "assistant_walk",
    "test_commands.py": "assistant_walk",
    "test_questions.py": "assistant_walk",
    # 19 November 2026, phase 6d: three Change watch walks. The evidence file's walk is short, but some fifty tests read
    # it (the tamper cases of the verify command and 400 damaged copies), as with test_otto_evidence.py above; the
    # panel's and the page's walk each take three to four seconds to make. The rules of a watch run itself
    # (test_watch_run.py, test_changes_read.py) stay in the everyday run. Run all of it with:
    # pytest -q tests/changewatch --full (about a minute), whenever Change watch is touched.
    "test_watch_evidence.py": "made",
    "test_watch_panel.py": "beside",
    "test_watch_view.py": "page",
    # 26 November 2026, Evidence as the full record: one walk shared by the files of tests/record (the fix from Connect
    # demo code to the merge, a retest, a developer's change and its picked tests, two downloads; five to six seconds to
    # make). Its readers are slow by the rule above. What stays in the everyday run: the tests on the short walk of
    # tests/record/record_walk.py, the name sources, what leaves no row, the source scans and the bent copies of the
    # evidence part. Run all of it with: pytest -q tests/record --full (about a minute).
    "test_actions_record.py": "walked",
    "test_record_timeline.py": "walked",
    "test_record_reads_only.py": "walked",
    "test_record_evidence.py": "walked",
}
# 19 November 2026: the whole demo, made once for the run (`demo_flow` below: Run all, then Retest on 1.4.3). It takes
# about 49 seconds on the build machine (the published test cases twice and the speed test twice), and 41 tests in
# eleven files read it. With the tests of phases 6a to 6e the fast set had reached seven minutes, so by the rule above
# its readers are slow too, whatever file they are in. What they stand on is graded on every push all the same: the
# accuracy check walks this same demo through the same path and compares its 18 answers with the answer key. The scan
# for private keys has a short form of its own that stays in the everyday run (tests/test_secrets_scan.py).
SLOW_SESSION_WALKS = {"demo_flow"}


def pytest_collection_modifyitems(config, items):
    """A test that needs Docker, or reads one of the long demo walks above, is slow by itself; others are marked
    @pytest.mark.slow by hand. The everyday run leaves the slow ones out; --full (or naming a marker with -m) runs them.
    Phase 5c: a test marked needs_otto is skipped, and counted, where Adam's Otto harness is not installed (GitHub's
    checks can't fetch a private repository without a secret). Never a silent pass."""
    for item in items:
        fixtures = getattr(item, "fixturenames", ())
        if (
            "docker_ready" in fixtures
            or SLOW_SHARED_WALKS.get(item.path.name) in fixtures
            or SLOW_SESSION_WALKS.intersection(fixtures)
        ):
            item.add_marker(pytest.mark.slow)
    if not (config.getoption("--full") or config.getoption("markexpr")):
        slow = [item for item in items if item.get_closest_marker("slow")]
        if slow:
            config.hook.pytest_deselected(items=slow)
            items[:] = [item for item in items if not item.get_closest_marker("slow")]
            config._slow_left_out = len(slow)
    from app.otto import harness

    otto = harness.status()
    if not otto.installed:
        needing = [item for item in items if item.get_closest_marker("needs_otto")]
        for item in needing:
            item.add_marker(pytest.mark.skip(reason=f"Otto is not installed here ({otto.reason})"))
        config._otto_skipped = (len(needing), otto.reason)


def pytest_terminal_summary(terminalreporter, config):
    skipped, reason = getattr(config, "_otto_skipped", (0, None))
    if skipped:
        terminalreporter.write_line(f"Otto is not installed here ({reason}): {skipped} tests skipped.")
    left_out = getattr(config, "_slow_left_out", 0)
    if left_out:
        terminalreporter.write_line(
            f"{left_out} slow tests were left out (Docker, real libraries, timing, long "
            "flows). Run them with: pytest -q tests --full"
        )


def api_routes(app) -> list:
    """Every route of the app, in registration order, including those the step modules add with include_router."""

    def flat(routes):
        for r in routes:
            if type(r).__name__ == "_IncludedRouter":
                yield from flat(r.original_router.routes)
            else:
                yield r

    return list(flat(app.routes))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def free_ports(n: int) -> tuple[int, ...]:
    """n free ports, all different. Asked one after the other, the system can hand the same free port out twice; a
    demo file made from such ports names one address twice and is refused (it failed one run on 18 November 2026)."""
    found: list[int] = []
    while len(found) < n:
        port = free_port()
        if port not in found:
            found.append(port)
    return tuple(found)


class ReachedClaude(BaseException):
    """A test tried to reach the Claude API. Not an ordinary error on purpose: Otto's client turns every ordinary
    error of a request into a plain sentence, and this one must stop the test instead."""


@pytest.fixture(autouse=True)
def no_call_to_claude(monkeypatch):
    """Phase 5c: no test ever reaches the Claude API. Otto's client looks its transport up at the moment of a call;
    here it is replaced by one that fails the test. A test of the live path puts its own stand-in in its place."""
    from app.otto import model

    def refuse(body, headers, timeout):
        raise ReachedClaude("a test tried to reach the Claude API; give the client a stand-in transport")

    monkeypatch.setattr(model, "_http_transport", refuse)


class ReachedTheNetwork(BaseException):
    """A test tried to read advisories from the public source. Not an ordinary error, for the same reason."""


@pytest.fixture(autouse=True)
def no_read_of_the_advisory_source(monkeypatch):
    """Phase 6, the research loop: no test ever reaches osv.dev. The reader looks its transport up at the moment of a
    request; here it is replaced by one that fails the test. Tests read recorded answers, or give a stand-in."""
    from app.otto import lookup

    def refuse(body, timeout):
        raise ReachedTheNetwork(
            "a test tried to read advisories from the network; use a recorded source or a stand-in transport"
        )

    monkeypatch.setattr(lookup, "_http_transport", refuse)


class ReachedGitHub(BaseException):
    """A test tried to reach GitHub for a login. Not an ordinary error, for the same reason."""


@pytest.fixture(autouse=True)
def no_login_at_github(monkeypatch):
    """Hosting: no test reaches GitHub. Tests of the GitHub login give a stand-in transport."""
    from app import github_login

    def refuse():
        raise ReachedGitHub("a test tried to reach GitHub; give the login a stand-in transport")

    monkeypatch.setattr(github_login, "_http_client", refuse)


@pytest.fixture(autouse=True, scope="session")
def database_per_lab(request):
    """Hosting: with EVIDENCE_LAB_TEST_DATABASE_URL=postgresql://user@host/any, the whole suite runs on PostgreSQL.
    Every data folder gets a database of its own, made on that server and dropped at the end. Tests that open the
    SQLite file itself or use SQLite's own SQL (triggers dropped, json_set) fail there by design."""
    import os
    import uuid

    url = os.environ.get("EVIDENCE_LAB_TEST_DATABASE_URL")
    if not url:
        yield
        return
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    from app import db as app_db
    from app.infra.database import normalise_url
    from app.lab import hub

    server = make_url(normalise_url(url))
    admin = create_engine(server.set(database="postgres"), isolation_level="AUTOCOMMIT")
    made: dict[str, str] = {}
    original = app_db.make_session_factory

    def fresh(database):
        # One database per data folder: an app started again on the same folder finds its records, as with SQLite.
        key = str(database)
        if key not in made:
            made[key] = "evlab_test_" + uuid.uuid4().hex[:16]
            with admin.connect() as conn:
                conn.execute(text(f'CREATE DATABASE "{made[key]}"'))
        return original(server.set(database=made[key]).render_as_string(hide_password=False))

    patcher = pytest.MonkeyPatch()
    patcher.setattr(hub, "make_session_factory", fresh)
    try:
        yield
    finally:
        patcher.undo()
        with admin.connect() as conn:
            for name in made.values():
                conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(autouse=True)
def no_read_of_a_package_registry(monkeypatch):
    """Sandbox research (a prototype): no test ever reaches npm or PyPI. The reader looks its transport up at the moment
    of a request; here it is replaced by one that fails the test. Tests read a folder of recorded answers, or give a
    stand-in. (A research command a test starts as a process of its own is given EVIDENCE_LAB_REGISTRY_SOURCE.)"""
    from app.sandbox import registries

    def refuse(url, timeout, limit):
        raise ReachedTheNetwork(
            "a test tried to read a package registry; use a recorded registry or a stand-in transport"
        )

    # (the reader's own function, for the one test that is about it: that test puts a stand-in where the function
    #  would open a connection, so it reaches nothing either)
    refuse.the_readers_own = getattr(registries._http, "the_readers_own", registries._http)  # type: ignore[attr-defined]
    monkeypatch.setattr(registries, "_http", refuse)


@pytest.fixture
def settings(tmp_path):
    # Tests run in demo mode unless they ask for the docker_ready fixture; the speed test uses fewer pairs
    # (25 short rounds of 4: enough for the slowed control to stand clear of the noise on a busy machine).
    return Settings(
        data_dir=tmp_path / "data", demo_tls_port=free_port(), force_mode="demo", speed_rounds=25, speed_repeats=4
    )


DOCKER_SKIP = (
    "Skipped: Docker is not running or the test images are not prepared "
    "(run: cd backend && .venv/bin/python -m app.prepare)."
)


@pytest.fixture(scope="session")
def docker_ready(tmp_path_factory):
    """The isolated mode, for tests that need real containers. Skips with a clear message when it is not available."""
    from app.run import runner

    mode = runner.detect_mode(Settings(data_dir=tmp_path_factory.mktemp("isolated-data"), demo_tls_port=1))
    if mode.name != "isolated" or not mode.components_image:
        pytest.skip(DOCKER_SKIP)
    return mode


@pytest.fixture
def anon_client(settings):
    """The app with a fresh data folder and its demo server on a spare port. Not logged in."""
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def client(anon_client):
    assert anon_client.post("/api/setup", json={"password": PASSWORD}).status_code == 200
    return anon_client


@pytest.fixture(scope="session")
def test_cert(tmp_path_factory):
    return ensure_demo_certificate(tmp_path_factory.mktemp("certs"))


@pytest.fixture
def tls_server(test_cert):
    """Start throwaway TLS servers on spare ports: kind = demo | legacy | tls13only."""
    started = []

    def start(kind: str = "demo") -> int:
        cert, key = test_cert
        if kind == "demo":
            ctx = make_server_context(cert, key)
        elif kind == "legacy":
            ctx = make_server_context(cert, key, ciphers="ALL:@SECLEVEL=0", minimum=ssl.TLSVersion.TLSv1, group=None)
        elif kind == "tls13only":
            ctx = make_server_context(cert, key, minimum=ssl.TLSVersion.TLSv1_3)
        else:
            raise ValueError(kind)
        server = TlsServer(ctx)
        started.append(server)
        return server.port

    yield start
    for server in started:
        server.close()


class CountingListener:
    """A plain TCP listener that never speaks TLS and counts connection attempts."""

    def __init__(self):
        self.sock = socket.create_server(("127.0.0.1", 0))
        self.sock.setblocking(False)
        self.port = self.sock.getsockname()[1]

    def connections(self) -> int:
        n = 0
        while True:
            try:
                conn, _ = self.sock.accept()
            except BlockingIOError:
                return n
            conn.close()
            n += 1

    def close(self):
        self.sock.close()


@pytest.fixture
def listener():
    item = CountingListener()
    yield item
    item.close()


def csv_bytes(*rows: str) -> bytes:
    return ("location,type,claim,value\n" + "\n".join(rows) + "\n").encode()


def upload(client, name: str, data: bytes):
    return client.post(
        "/api/import/file",
        params={"filename": name},
        content=data,
        headers={"Content-Type": "application/octet-stream"},
    )


# ------------------------------------------------------------------ phase 2: tests and Evidence Lab

import threading  # noqa: E402
from contextlib import contextmanager  # noqa: E402
from types import SimpleNamespace  # noqa: E402


def result_of(view: dict, kind: str, which: str = "result") -> dict:
    """The LabResult for one kind of test in a LabView ("result" = first run, "after" = retest)."""
    return next(r for r in view["rows"] if r["kind"] == kind)[which]


def make_lab(tmp_path, **overrides):
    """A started Lab in demo mode with its own data folder and demo server. The caller stops it."""
    from app.lab.hub import Lab

    values = dict(
        data_dir=tmp_path / "data", demo_tls_port=free_port(), force_mode="demo", speed_rounds=25, speed_repeats=4
    )
    values.update(overrides)
    lab = Lab(Settings(**values))
    lab.start()
    return lab


def demo_plan(lab) -> SimpleNamespace:
    """Import the demo file, confirm its address, and make the plan (the five suggested tests)."""
    imp = lab.import_demo()
    lab.confirm_address(imp["id"], imp["addresses"][0]["address"], True)
    plan = lab.ensure_plan(imp["id"])
    return SimpleNamespace(imp=imp, id=plan["id"], item={t["kind"]: t["id"] for t in plan["tests"]})


def play_back_speed(lab) -> None:
    """From now on this lab's "Speed and size" test plays back made-up timings instead of timing the signer.
    The harness job that would run the bench rounds answers at once, in the harness's own line format: every
    program takes about the same time, and the slowed control 6 ms more on every sign and verify. Everything
    after that is the real thing: the run record, the reviewer's slowdown rule applied to those numbers, the
    control check, the read gate. A change can only be offered with a speed comparison, so every plan that is
    proved needs this test; with played-back timings such a plan stays quick and comes out the same on a busy
    machine. It is for tests about where a fix stands. The tests of the speed rule itself, and the full flows,
    time the real programs."""
    import random

    from app.run import runner

    real = lab.component_runner.run_job
    if getattr(real, "plays_back_speed", False):
        return

    def run_job(job, *, time_limit=120.0, on_line=None, family=None):
        subjects = job.get("subjects") or []
        if (
            job.get("op") != "bench_rounds" or len(subjects) < 2
        ):  # only the speed test times two or three programs side by side
            return real(job, time_limit=time_limit, on_line=on_line, family=family)
        rng = random.Random(7)
        # A test may set this on the lab to play back a real slowdown: in a comparison of old, new and the slowed
        # control (a retest or a proof), the new version then takes this much longer on every sign and verify.
        slower = float(getattr(lab, "played_back_new_version_slower_by_ms", 0.0)) if len(subjects) == 3 else 0.0

        def timings(base: float, subject: str) -> list[float]:
            extra = slower if subject == subjects[1] else 0.0
            if subject.startswith("control-slow:"):
                extra = slower + 6.0
            return [round(base + extra + rng.random() * 0.2, 4) for _ in range(job["repeats"])]

        lines = [{"keygen": job["keygen_with"], "rc": 0, "public_key_bytes": 65}]
        for number in range(job["rounds"]):
            for subject in subjects if number % 2 == 0 else list(reversed(subjects)):  # the order the harness goes in
                out = {
                    "sign_ms": timings(7.0, subject),
                    "verify_ms": timings(13.0, subject),
                    "signature_bytes": 71,
                    "public_key_bytes": 65,
                    "all_verified": True,
                }
                lines.append({"round": number, "subject": subject, "rc": 0, "out": out, "error": None})
        for line in lines:
            if on_line is not None:
                on_line(line)
        return runner.BatchResult(
            True, lines, None, lab.mode.name, "played back for a test: no program was timed", runner._now(), 0, ""
        )

    run_job.plays_back_speed = True
    lab.component_runner.run_job = run_job


@contextmanager
def held(lab):
    """While this is open the harness jobs wait at the door until the Event it gives is set: a proof that is
    certainly still running, and that ends exactly when the test says so."""
    go, real = threading.Event(), lab.component_runner.run_job

    def waiting(job, **more):
        go.wait(60)
        return real(job, **more)

    lab.component_runner.run_job = waiting
    try:
        yield go
    finally:
        go.set()
        lab.component_runner.run_job = real


def run_kind(lab, plan, kind: str) -> dict:
    """Run one test by itself and return its reviewed result."""
    lab.run_test(plan.id, plan.item[kind])
    lab.wait_until_idle(plan.id, 240)
    return result_of(lab.lab_view(plan.id), kind)


@pytest.fixture
def lab(tmp_path):
    item = make_lab(tmp_path)
    yield item
    item.stop()


@pytest.fixture(scope="session")
def demo_flow(tmp_path_factory):
    """The whole demo, once, through the same service path as the buttons: propose, lock, add the two catalog
    tests, Run all, then Retest on 1.4.3. Tests that only read results share it."""
    lab = make_lab(tmp_path_factory.mktemp("demo-flow"))
    try:
        plan = demo_plan(lab)
        verify = lab.verify(plan.imp["id"])
        for kind in ("pq_readiness", "mldsa_compare"):
            view = lab.add_test(plan.id, kind)
        plan.item = {t["kind"]: t["id"] for t in view["tests"]}
        lab.run_all(plan.id)
        lab.wait_until_idle(plan.id, 300)
        most_at_once = lab.jobs.most_at_once
        first = lab.lab_view(plan.id)
        lab.start_retest(plan.id, "1.4.3")
        lab.wait_until_idle(plan.id, 300)
        after = lab.lab_view(plan.id)
        yield SimpleNamespace(lab=lab, plan=plan, verify=verify, first=first, after=after, most_at_once=most_at_once)
    finally:
        lab.stop()


@pytest.fixture(scope="session")
def _assistant_walk_made(tmp_path_factory):
    """The walk itself, made once for the run. What it patched to be made (its own list of trusted pack keys, and the
    wrapper that records Otto's prompts) is taken off again at once and handed on: for the rest of the run nothing of
    it may stand between the tests of other files. (Left in place, every later test that needs the real shipped key
    was refused its packs: found on 19 November 2026 by the first whole run of the fast set with Otto.)"""
    from app.otto import model, packs
    from tests.assistant import assistant_walk as made

    walk, lab, patches = made.make_walk(tmp_path_factory)
    held = {"keys": packs.TRUSTED_KEYS_FILE, "recorded": model.OttoModel.__dict__["recorded"]}
    patches.undo()
    try:
        yield walk, held
    finally:
        lab.stop()


@pytest.fixture
def assistant_walk(_assistant_walk_made, monkeypatch):
    """Phase 6a: one walk of a demo-mode Lab for the Otto panel's tests, with every page's read of the panel kept at
    each stage (tests/assistant/assistant_walk.py). It needs Adam's Otto harness: decisions are recorded in its
    ledger. A few seconds, once, for the tests that read it. The walk's own patches are put back for the one test
    that reads it (its Lab is asked again by some), and taken off when that test ends."""
    from app.otto import model, packs

    walk, held = _assistant_walk_made
    monkeypatch.delenv(model.KEY_ENV, raising=False)
    monkeypatch.setattr(packs, "TRUSTED_KEYS_FILE", held["keys"])
    monkeypatch.setattr(model.OttoModel, "recorded", held["recorded"])
    return walk
