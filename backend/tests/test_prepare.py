"""The prepare step is the only code that may build or download an image, and it can never stop the app starting."""
import base64
import hashlib
import re
import urllib.request

import pytest
from pathlib import Path

from app import prepare
from app import real_libraries
from app.config import NGINX_IMAGE, OPENSSL_IMAGE, PYTHON_BASE_IMAGE, REPO_ROOT

APP = Path(prepare.__file__).parent


@pytest.fixture(autouse=True)
def no_otto_step(monkeypatch):
    """The Otto step of prepare (phase 5c) has its own tests (tests/otto/test_harness.py). Here it is a stand-in, so
    these tests say the same on a computer with Otto and on one without, and never try to fetch it."""
    asked = []
    monkeypatch.setattr(prepare, "prepare_otto", lambda check_only, say: asked.append(check_only) or False)
    return asked


def run(monkeypatch, argv, *, docker=True, present=()):
    """Nothing here downloads or builds: pull, fetch and both builds are stand-ins. `pulled` and `built` hold only what
    the older steps (the three base images and our components image) asked for; the real-library steps go to `real`."""
    said, pulled, built = [], [], []
    real = {"pulled": [], "fetched": [], "built": []}
    monkeypatch.setattr(prepare, "docker_running", lambda: docker)
    monkeypatch.setattr(prepare, "image_present", lambda ref: ref in present or ref in pulled or ref in built or ref in real["pulled"]
                        or ref in real["built"])
    monkeypatch.setattr(prepare, "pull", lambda ref, limit=prepare.PULL_LIMIT_SECONDS:
                        (pulled if limit == prepare.PULL_LIMIT_SECONDS else real["pulled"]).append(ref) or True)
    monkeypatch.setattr(prepare, "build", lambda tag: built.append(tag) or True)
    monkeypatch.setattr(prepare, "fetch", lambda pin, folder=None: real["fetched"].append(pin["file"]) or Path(pin["file"]))
    monkeypatch.setattr(prepare, "build_real", lambda family, tag, files: real["built"].append(tag) or True)
    code = prepare.main(argv, say=said.append)
    run.real = real
    return code, "\n".join(said), pulled, built


def test_without_docker_it_says_so_and_exits_0(monkeypatch, no_otto_step):
    code, text, pulled, built = run(monkeypatch, [], docker=False)
    assert code == 0 and "Docker is not running" in text and "demo mode" in text and pulled == built == []
    assert no_otto_step == [False]          # the Otto step is asked first, with or without Docker (it needs none)


def test_check_builds_and_downloads_nothing(monkeypatch):
    code, text, pulled, built = run(monkeypatch, ["--check"])
    assert code == 0 and pulled == built == []
    assert text.count(": missing  (") == 4 + 5 and "Real library, Java: missing" in text and "Isolated mode: not ready" in text and "nginx lab image is missing" in text


def test_it_downloads_only_the_pinned_images_and_builds_our_image(monkeypatch):
    code, text, pulled, built = run(monkeypatch, [])
    assert code == 0 and pulled == [PYTHON_BASE_IMAGE, OPENSSL_IMAGE, NGINX_IMAGE] and built == [prepare.components_image_tag()]
    assert "Isolated mode: ready" in text
    assert all("@sha256:" in ref and len(ref.split("@sha256:")[1]) == 64 for ref in pulled)


def test_nothing_to_do_when_everything_is_present(monkeypatch):
    everything = (PYTHON_BASE_IMAGE, OPENSSL_IMAGE, NGINX_IMAGE, prepare.components_image_tag())
    code, text, pulled, built = run(monkeypatch, [], present=everything)
    assert code == 0 and pulled == built == [] and text.count("ready") >= 4


def test_offline_or_failing_steps_still_exit_0(monkeypatch):
    said = []
    monkeypatch.setattr(prepare, "docker_running", lambda: True)
    monkeypatch.setattr(prepare, "image_present", lambda ref: False)
    monkeypatch.setattr(prepare, "pull", lambda ref, limit=0: False)
    monkeypatch.setattr(prepare, "build", lambda tag: (_ for _ in ()).throw(AssertionError("no base image, so no build")))
    assert prepare.main([], say=said.append) == 0
    text = "\n".join(said)
    assert "could not download" in text and "Isolated mode: not ready" in text and "OpenSSL 3.5 or newer" in text


def test_build_command_uses_only_our_folder_no_network_and_no_pull(monkeypatch):
    seen = []
    monkeypatch.setattr(prepare, "_run", lambda args, limit: seen.append((args, limit)) or True)
    prepare.build("evidence-lab-components:abc")
    (args, limit), = seen
    components = str(REPO_ROOT / "demo" / "components")
    assert args == ["build", "--pull=false", "--network", "none", "-t", "evidence-lab-components:abc",
                    "-f", components + "/Dockerfile", components] and limit == 180
    dockerfile = (REPO_ROOT / "demo" / "components" / "Dockerfile").read_text()
    lines = [line for line in dockerfile.splitlines() if line and not line.startswith("#")]
    assert lines == [f"FROM {PYTHON_BASE_IMAGE}", "COPY . /opt/evidence-lab/components/", "USER 65534:65534"]


def test_only_prepare_can_build_or_pull():
    """Source scan of the whole backend app: no other module holds a docker build or pull command."""
    pattern = re.compile(r"""["']build["']|["']pull["']|docker\s+(build|pull)|buildx|["']load["']|["']import["']""")
    offenders = [str(path.relative_to(APP)) for path in sorted(APP.rglob("*.py"))
                 if path.name != "prepare.py" and pattern.search(path.read_text())]
    assert offenders == []
    assert pattern.search((APP / "prepare.py").read_text())
    run_flags = (APP / "run" / "runner.py").read_text()
    assert '"--pull", "never"' in run_flags  # a missing image is an error, never a download
    assert '"--pull", "never"' in (APP / "servers" / "lab_nginx.py").read_text()   # the lab nginx too (phase 4b)
    assert NGINX_IMAGE.startswith("nginx@sha256:") and len(NGINX_IMAGE.split("@sha256:")[1]) == 64


# ---------------------------------------------------------------- real libraries (phase 4c); nothing is downloaded or built

def test_main_prepares_one_image_per_real_library_family_and_says_so(monkeypatch):
    code, text, pulled, built = run(monkeypatch, [])
    real = run.real
    assert code == 0 and built == [prepare.components_image_tag()]
    assert sorted(real["built"]) == sorted(prepare.real_image_tag(f) for f in real_libraries.FAMILIES)
    for family, pins in real_libraries.FAMILIES.items():
        assert f"Real library, {pins['label']}: ready  ({prepare.real_image_tag(family)})" in text
        assert set(pins["images"].values()) <= set(real["pulled"]) | set(pulled)   # the OpenSSL one was pulled with the bases
    assert sorted(real["fetched"]) == sorted(d["file"] for p in real_libraries.FAMILIES.values() for d in p["downloads"])
    assert "Real libraries:" not in text


def test_check_only_prepares_no_real_library_and_says_which_are_missing(monkeypatch):
    code, text, _, _ = run(monkeypatch, ["--check"])
    assert code == 0 and run.real == {"pulled": [], "fetched": [], "built": []}
    assert text.count("Real library, ") == 5 and "can't run until" not in text      # nothing built here, so the demo image is missing too


def test_a_family_that_cannot_be_prepared_is_named_and_the_others_still_work(monkeypatch):
    said = []
    monkeypatch.setattr(prepare, "prepare_real", lambda family, check_only, say, base_ready: family != "java")
    monkeypatch.setattr(prepare, "docker_running", lambda: True)
    present = (PYTHON_BASE_IMAGE, OPENSSL_IMAGE, NGINX_IMAGE, prepare.components_image_tag())
    monkeypatch.setattr(prepare, "image_present", lambda ref: ref in present)
    assert prepare.main([], say=said.append) == 0
    text = "\n".join(said)
    assert "Real library, Java: missing" in text and "Real library, OpenSSL: ready" in text
    assert "Real libraries: Java can't run until its image is prepared" in text


def test_matches_works_for_both_kinds_of_pin():
    data = b"the pinned file"
    by_sha256 = {"sha256": hashlib.sha256(data).hexdigest()}
    by_integrity = {"sha512_base64": base64.b64encode(hashlib.sha512(data).digest()).decode()}
    for pin in (by_sha256, by_integrity):
        assert prepare._matches(data, pin) is True
        assert prepare._matches(data + b"x", pin) is False
        assert prepare._matches(b"", pin) is False
    assert prepare._matches(data, {"sha256": "0" * 64}) is False
    assert prepare._matches(data, {"sha512_base64": "AAAA"}) is False


class _Answer:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit=-1):
        return self.data[:limit] if limit >= 0 else self.data


def test_fetch_refuses_a_file_whose_fingerprint_differs(monkeypatch, tmp_path):
    pin = {"file": "lib-1.0.tgz", "url": "https://registry.npmjs.org/lib/-/lib-1.0.tgz", "sha256": hashlib.sha256(b"the real one").hexdigest()}
    asked = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=None: asked.append(url) or _Answer(b"some other bytes"))
    assert prepare.fetch(pin, tmp_path) is None
    assert asked == [pin["url"]] and list(tmp_path.iterdir()) == []         # nothing was kept
    pin["sha256"] = hashlib.sha256(b"some other bytes").hexdigest()           # the same bytes are fine when they are the pinned ones
    path = prepare.fetch(pin, tmp_path)
    assert path == tmp_path / "lib-1.0.tgz" and path.read_bytes() == b"some other bytes"


def test_fetch_uses_the_kept_copy_without_any_download_when_it_matches(monkeypatch, tmp_path):
    pin = {"file": "lib-1.0.tgz", "url": "https://registry.npmjs.org/lib/-/lib-1.0.tgz", "sha256": hashlib.sha256(b"kept").hexdigest()}
    (tmp_path / pin["file"]).write_bytes(b"kept")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no download")))
    assert prepare.fetch(pin, tmp_path) == tmp_path / "lib-1.0.tgz"
    (tmp_path / pin["file"]).write_bytes(b"tampered")                          # a kept copy that no longer matches is not trusted
    with pytest.raises(AssertionError, match="no download"):                    # so it goes to the download, which here would fail
        prepare.fetch(pin, tmp_path)


def test_fetch_gives_nothing_when_the_download_fails_or_is_too_big(monkeypatch, tmp_path):
    pin = {"file": "lib-1.0.tgz", "url": "https://registry.npmjs.org/lib/-/lib-1.0.tgz", "sha256": "0" * 64}

    def offline(*args, **kwargs):
        raise OSError("no network")
    monkeypatch.setattr(urllib.request, "urlopen", offline)
    assert prepare.fetch(pin, tmp_path) is None
    big = b"x" * (prepare.MAX_DOWNLOAD_BYTES + 5)
    pin["sha256"] = hashlib.sha256(big).hexdigest()
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Answer(big))
    assert prepare.fetch(pin, tmp_path) is None
