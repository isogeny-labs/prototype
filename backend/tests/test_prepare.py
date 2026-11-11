"""The prepare step is the only code that may build or download an image, and it can never stop the app starting."""
import re
from pathlib import Path

from app import prepare
from app.config import OPENSSL_IMAGE, PYTHON_BASE_IMAGE, REPO_ROOT

APP = Path(prepare.__file__).parent


def run(monkeypatch, argv, *, docker=True, present=()):
    said, pulled, built = [], [], []
    monkeypatch.setattr(prepare, "docker_running", lambda: docker)
    monkeypatch.setattr(prepare, "image_present", lambda ref: ref in present or ref in pulled or ref in built)
    monkeypatch.setattr(prepare, "pull", lambda ref: pulled.append(ref) or True)
    monkeypatch.setattr(prepare, "build", lambda tag: built.append(tag) or True)
    code = prepare.main(argv, say=said.append)
    return code, "\n".join(said), pulled, built


def test_without_docker_it_says_so_and_exits_0(monkeypatch):
    code, text, pulled, built = run(monkeypatch, [], docker=False)
    assert code == 0 and "Docker is not running" in text and "demo mode" in text and pulled == built == []


def test_check_builds_and_downloads_nothing(monkeypatch):
    code, text, pulled, built = run(monkeypatch, ["--check"])
    assert code == 0 and pulled == built == []
    assert text.count(": missing  (") == 3 and "Isolated mode: not ready" in text


def test_it_downloads_only_the_pinned_images_and_builds_our_image(monkeypatch):
    code, text, pulled, built = run(monkeypatch, [])
    assert code == 0 and pulled == [PYTHON_BASE_IMAGE, OPENSSL_IMAGE] and built == [prepare.components_image_tag()]
    assert "Isolated mode: ready" in text
    assert all("@sha256:" in ref and len(ref.split("@sha256:")[1]) == 64 for ref in pulled)


def test_nothing_to_do_when_everything_is_present(monkeypatch):
    everything = (PYTHON_BASE_IMAGE, OPENSSL_IMAGE, prepare.components_image_tag())
    code, text, pulled, built = run(monkeypatch, [], present=everything)
    assert code == 0 and pulled == built == [] and text.count("ready") >= 4


def test_offline_or_failing_steps_still_exit_0(monkeypatch):
    said = []
    monkeypatch.setattr(prepare, "docker_running", lambda: True)
    monkeypatch.setattr(prepare, "image_present", lambda ref: False)
    monkeypatch.setattr(prepare, "pull", lambda ref: False)
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
    run_flags = (APP / "runner.py").read_text()
    assert '"--pull", "never"' in run_flags  # a missing image is an error, never a download
