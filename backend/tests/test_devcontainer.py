"""A brand-new Codespace starts the app with ./run-demo.sh alone (fix 8, 19 November 2026).

Two things make that true, and both are checked here without Docker and without the network:

- `.devcontainer/devcontainer.json` names what a Codespace is built from: the official Python 3.12 image and the
  features Node.js 22, Docker inside the Codespace and Git LFS, each pinned by its fingerprint. The Otto read
  permission of phase 5c is still there, unchanged.
- `./run-demo.sh` makes the app's private Python environment only with a Python 3.12 that can make one, makes a
  half-made environment again, and otherwise stops with one plain sentence.

The script's steps 1 to 3 are run for real, in a folder of their own, with pretend Pythons (small scripts that
answer the few questions the script asks). One slow test does the same with the real Python.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import REPO_ROOT

DEVCONTAINER = REPO_ROOT / ".devcontainer" / "devcontainer.json"
SCRIPT = REPO_ROOT / "run-demo.sh"

FINGERPRINT = r"sha256:[0-9a-f]{64}"
IMAGE = r"mcr\.microsoft\.com/devcontainers/python:3-3\.12-bookworm@" + FINGERPRINT
FEATURE = r"ghcr\.io/devcontainers/features/([a-z0-9-]+)@" + FINGERPRINT
OTTO_PERMISSION = {"codespaces": {"repositories": {"isogeny-labs/otto": {"permissions": {"contents": "read"}}}}}


# ---------------------------------------------------------------- .devcontainer/devcontainer.json

def devcontainer() -> dict:
    """The file is JSON with // comment lines. They are left out before it is read."""
    lines = DEVCONTAINER.read_text(encoding="utf-8").splitlines()
    return json.loads("\n".join(line for line in lines if not line.lstrip().startswith("//")))


def features() -> dict[str, dict]:
    """Each feature of the file by its short name (node, docker-in-docker, git-lfs): its options."""
    found = {}
    for reference, options in devcontainer()["features"].items():
        match = re.fullmatch(FEATURE, reference)
        assert match, f"this feature is not an official one pinned by its fingerprint: {reference}"
        found[match.group(1)] = options
    return found


def test_the_image_is_the_official_python_312_image_pinned_by_its_fingerprint():
    config = devcontainer()
    assert re.fullmatch(IMAGE, config["image"]), config["image"]
    # the image is named, not built here: nothing else may decide what a Codespace starts from
    assert not {"build", "dockerFile", "dockerComposeFile"} & set(config)


def test_the_three_features_are_there_each_pinned_by_its_fingerprint():
    assert {"node", "docker-in-docker", "git-lfs"} <= set(features())
    references = list(devcontainer()["features"])
    assert len(features()) == len(references)   # no feature is named twice
    # four parts, four different fingerprints (one pasted twice would pin the wrong thing)
    pins = re.findall(FINGERPRINT, " ".join([devcontainer()["image"], *references]))
    assert len(pins) == len(set(pins)) == len(references) + 1


def test_node_is_22():
    assert features()["node"] == {"version": "22"}


def test_the_otto_read_permission_is_unchanged():
    assert devcontainer()["customizations"] == OTTO_PERMISSION


def test_nothing_in_the_file_comes_from_a_registry_without_a_fingerprint():
    def texts(value):
        if isinstance(value, dict):
            for key, inner in value.items():
                yield key
                yield from texts(inner)
        elif isinstance(value, list):
            for inner in value:
                yield from texts(inner)
        elif isinstance(value, str):
            yield value

    from_a_registry = [text for text in texts(devcontainer()) if re.match(r"(mcr\.microsoft\.com|ghcr\.io|docker\.io)/", text)]
    assert len(from_a_registry) >= 4
    for text in from_a_registry:
        assert re.search("@" + FINGERPRINT + "$", text), f"not pinned by its fingerprint: {text}"
        assert ":latest" not in text


# ---------------------------------------------------------------- ./run-demo.sh, steps 1 to 3

BASH = shutil.which("bash")
TOOLS = ("dirname", "grep", "rm", "touch", "mkdir", "cat", "chmod")   # every program steps 1 to 3 and the pretend Pythons start
FIXED_PLACES = {"/usr/local/bin/python3.12": "usr-local-bin", "/usr/bin/python3.12": "usr-bin"}
HALF_MADE = "The virtual environment was not created successfully because ensurepip is not available."


def environment_python(log: Path, name: str, pip: bool) -> str:
    """The Python inside a pretend environment. Its pip answers, or (half made) there is no pip."""
    answer = "exit 0" if pip else 'echo "No module named pip" >&2; exit 1'
    return (f"#!{BASH}\n"
            f'echo "environment of {name}: $*" >> {shlex.quote(str(log))}\n'
            f'case "$1 $2" in "-m pip") {answer} ;; esac\n'
            'echo "pretend environment: a question the test did not expect: $*" >&2; exit 97\n')


def pretend_python(log: Path, name: str, version: str, parts: bool, makes: str) -> str:
    """A pretend Python: a small script that answers the questions run-demo.sh asks a Python, and notes each one.
    `version` is what it says it is; `parts` is whether it has venv and ensurepip; `makes` is what `-m venv` does:
    "whole" (an environment whose pip works), "half" (what Ubuntu's Python does without its venv package: a folder
    with a Python and no pip, and an error) or "half, quietly" (the same folder, and it says it worked)."""
    inner = environment_python(log, name, pip=makes == "whole")
    ending = f"echo {shlex.quote(HALF_MADE)} >&2; exit 1" if makes == "half" else "exit 0"
    return (f"#!{BASH}\n"
            f'echo "{name}: $*" >> {shlex.quote(str(log))}\n'
            'case "$1 $2" in\n'
            f'  "-c "*version_info*) [ "{version}" = "3.12" ]; exit ;;\n'
            f'  "-c "*ensurepip*) [ "{"yes" if parts else "no"}" = "yes" ]; exit ;;\n'
            '  "-m venv") ;;\n'
            '  *) echo "pretend Python: a question the test did not expect: $*" >&2; exit 97 ;;\n'
            'esac\n'
            'mkdir -p "$3/bin"\n'
            f'echo "{name}" > "$3/made-by"\n'
            f'cat > "$3/bin/python" <<\'INNER\'\n{inner}INNER\n'
            'chmod +x "$3/bin/python"\n'
            f"{ending}\n")


def program(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


class Stage:
    """A folder laid out like the repository, holding the real script's steps 1 to 3, and the pretend Pythons.

    The script is the real one, cut off where step 4 begins (nothing after the Python environment is run here).
    Its two fixed places to look are moved into this folder, and the PATH holds only this folder's own programs, so
    the same thing happens on every computer, whatever Pythons it has."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.root = folder / "repo"
        self.venv = self.root / "backend" / ".venv"
        self.lock = self.root / "backend" / "requirements.lock"
        self.log = folder / "asked.log"
        head, found, _rest = SCRIPT.read_text(encoding="utf-8").partition("\n# 4. ")
        assert found, "run-demo.sh has no line that begins step 4: say here where the Python environment step ends"
        for fixed, place in FIXED_PLACES.items():
            assert fixed in head, f"run-demo.sh no longer looks at {fixed}: bring this test up to date"
            head = head.replace(fixed, shlex.quote(str(folder / place / "python3.12")))
        self.lock.parent.mkdir(parents=True)
        self.lock.write_text("", encoding="utf-8")
        (self.root / "run-demo.sh").write_text(head + "\n", encoding="utf-8")
        (folder / "tools").mkdir()
        for tool in TOOLS:
            real = shutil.which(tool)
            assert real, f"this computer has no {tool}"
            (folder / "tools" / tool).symlink_to(real)

    def python(self, place: str, name: str, *, version: str = "3.12", parts: bool = True, makes: str = "whole",
               called: str = "python3.12") -> None:
        """Put a pretend Python into one of the folders: "usr-bin", "usr-local-bin" or any other name."""
        program(self.folder / place / called, pretend_python(self.log, name, version, parts, makes))

    def half_made(self, how: str) -> None:
        """backend/.venv as a first try that stopped halfway left it."""
        (self.venv / "bin").mkdir(parents=True)
        (self.venv / "left-from-before").write_text("x", encoding="utf-8")
        (self.venv / ".requirements-installed").write_text("", encoding="utf-8")
        if how == "no pip":                       # Ubuntu's Python without its venv package leaves exactly this
            program(self.venv / "bin" / "python", environment_python(self.log, "the half-made one", pip=False))
        elif how == "its Python does not start":
            program(self.venv / "bin" / "python", f"#!{BASH}\nexit 1\n")
        elif how == "its Python is gone":         # for example after the computer under it was rebuilt
            (self.venv / "bin" / "python").symlink_to(self.folder / "was-here-once" / "python3.12")
        else:
            assert how == "no Python at all"

    def whole(self) -> None:
        """backend/.venv whole, with its packages installed."""
        program(self.venv / "bin" / "python", environment_python(self.log, "the one already there", pip=True))
        (self.venv / "left-from-before").write_text("x", encoding="utf-8")
        (self.venv / ".requirements-installed").write_text("", encoding="utf-8")

    def run(self, *path: str, codespace: bool = False) -> subprocess.CompletedProcess:
        """Run steps 1 to 3 with these folders on the PATH, in this order (and nothing of the computer's own)."""
        env = {"PATH": os.pathsep.join(str(self.folder / place) for place in (*path, "tools")), "HOME": str(self.folder)}
        if codespace:
            env["CODESPACES"] = "true"
        return subprocess.run([BASH, str(self.root / "run-demo.sh")], env=env, cwd=self.folder, capture_output=True,
                              text=True, timeout=60, stdin=subprocess.DEVNULL)

    def asked(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def made_by(self) -> str | None:
        note = self.venv / "made-by"
        return note.read_text(encoding="utf-8").strip() if note.exists() else None

    def installs(self) -> list[str]:
        return [line for line in self.asked() if "-m pip install" in line]


@pytest.fixture
def stage(tmp_path):
    return Stage(tmp_path)


def stopped_with_one_plain_sentence(done: subprocess.CompletedProcess) -> str:
    """The script stopped, and said so once: what is wrong, and what to do. Nothing of Python's own leaks out."""
    assert done.returncode == 1
    said = [line for line in done.stderr.splitlines() if line.strip()]
    assert len(said) == 1 and said[0].startswith("Could not start: "), done.stderr
    assert said[0].endswith("then run ./run-demo.sh again.")
    assert "Traceback" not in done.stderr + done.stdout
    return said[0]


def test_the_script_asks_every_python_whether_it_can_make_the_environment():
    lines = SCRIPT.read_text(encoding="utf-8").splitlines()
    text = "\n".join(line for line in lines if not line.lstrip().startswith("#"))   # the commands, without the comments
    assert text.count("-m venv") == 1                   # one place makes the environment ...
    assert "import venv, ensurepip" in text             # ... and a Python is asked first whether it can
    assert not re.search(r"^\s*PY=[\"']?/", text, re.MULTILINE)   # no Python is picked by its place alone


def test_a_python_312_that_cannot_make_the_environment_is_passed_over(stage):
    """Today's failure in a new Codespace: the system's /usr/bin/python3.12 has no venv part. It used to be picked
    first, whatever else was there."""
    stage.python("usr-bin", "the system one", parts=False, makes="half")
    stage.python("usr-local-bin", "the good one")
    done = stage.run("usr-local-bin", "usr-bin")
    assert done.returncode == 0, done.stderr
    assert stage.made_by() == "the good one"
    assert not any(line.startswith("the system one: -m venv") for line in stage.asked())
    # the packages went into that environment, with their fingerprints checked
    assert len(stage.installs()) == 1 and stage.installs()[0].startswith("environment of the good one: ")
    assert f"--require-hashes -r {stage.lock}" in stage.installs()[0]
    assert (stage.venv / ".requirements-installed").exists()


def test_the_order_on_the_path_does_not_let_a_python_that_cannot_win(stage):
    stage.python("usr-bin", "the system one", parts=False, makes="half")
    stage.python("elsewhere", "the good one")
    done = stage.run("usr-bin", "elsewhere")            # the one that cannot comes first
    assert done.returncode == 0, done.stderr
    assert stage.made_by() == "the good one"
    assert not any(line.startswith("the system one: -m venv") for line in stage.asked())


def test_python3_counts_only_when_it_is_312(stage):
    stage.python("newer", "python 3.14", version="3.14", called="python3")
    stage.python("elsewhere", "the good one", called="python3")
    done = stage.run("newer", "elsewhere")
    assert done.returncode == 0, done.stderr
    assert stage.made_by() == "the good one"
    assert not any(line.startswith("python 3.14: -m venv") for line in stage.asked())


def test_the_two_fixed_places_are_looked_at_when_they_are_not_on_the_path(stage):
    stage.python("usr-local-bin", "the good one")
    done = stage.run()                                  # a PATH with no Python on it at all
    assert done.returncode == 0, done.stderr
    assert stage.made_by() == "the good one"


@pytest.mark.parametrize("how", ["no pip", "its Python does not start", "its Python is gone", "no Python at all"])
def test_a_half_made_environment_is_made_again(stage, how):
    stage.half_made(how)
    stage.python("usr-bin", "the good one")
    done = stage.run("usr-bin")
    assert done.returncode == 0, done.stderr
    assert stage.made_by() == "the good one"
    assert not (stage.venv / "left-from-before").exists()       # thrown away, not patched
    assert "again" in done.stdout                               # and the script says it is doing it again
    assert len(stage.installs()) == 1                           # the packages are installed again too


def test_a_half_made_environment_stays_when_no_python_can_make_it_again(stage):
    """The script could not do better, so it deletes nothing and says what to do."""
    stage.half_made("no pip")
    stage.python("usr-bin", "the system one", parts=False, makes="half")
    sentence = stopped_with_one_plain_sentence(stage.run("usr-bin"))
    assert "python3.12-venv" in sentence
    assert (stage.venv / "left-from-before").exists()
    assert not any("-m venv" in line for line in stage.asked())


def test_a_whole_environment_is_left_alone(stage):
    stage.whole()
    stage.python("usr-bin", "the good one")
    done = stage.run("usr-bin")
    assert done.returncode == 0, done.stderr
    assert (stage.venv / "left-from-before").exists()
    assert stage.made_by() is None and stage.installs() == []
    assert not any(line.startswith("the good one: ") for line in stage.asked())    # no other Python is even asked


def test_a_whole_environment_needs_no_other_python(stage):
    stage.whole()
    done = stage.run()                                  # no Python 3.12 anywhere else
    assert done.returncode == 0, done.stderr
    assert (stage.venv / "left-from-before").exists()


@pytest.mark.parametrize("makes", ["half", "half, quietly"])
def test_a_try_that_fails_leaves_nothing_behind(stage, makes):
    """A Python that looks able (3.12, with venv and ensurepip) and still fails, or says it worked and left no pip."""
    stage.python("usr-bin", "the one that fails", makes=makes)
    done = stage.run("usr-bin")
    assert done.returncode == 1
    assert not stage.venv.exists()                      # the next run starts clean
    said = [line for line in done.stderr.splitlines() if line.strip()]
    assert said[-1].startswith("Could not start: ") and said[-1].endswith("then run ./run-demo.sh again.")
    assert "backend/.venv" in said[-1]
    # what Python itself said is kept, on its own line, for whoever is asked to help
    assert said[:-1] == ([f"   Python said: {HALF_MADE}"] if makes == "half" else [])
    assert stage.installs() == []


def test_after_a_try_that_fails_the_next_python_is_tried(stage):
    stage.python("first", "the one that fails", makes="half")
    stage.python("second", "the good one")
    done = stage.run("first", "second")
    assert done.returncode == 0, done.stderr
    assert stage.made_by() == "the good one"
    assert len(stage.installs()) == 1 and stage.installs()[0].startswith("environment of the good one: ")


def test_without_any_python_312_it_stops_with_one_plain_sentence(stage):
    stage.python("newer", "python 3.14", version="3.14", called="python3")
    sentence = stopped_with_one_plain_sentence(stage.run("newer"))
    assert "Python 3.12 is not installed" in sentence
    assert not stage.venv.exists()


def test_with_only_a_python_312_that_cannot_it_stops_with_one_plain_sentence(stage):
    stage.python("usr-bin", "the system one", parts=False, makes="half")
    stage.python("newer", "python 3.14", version="3.14", called="python3")
    sentence = stopped_with_one_plain_sentence(stage.run("newer", "usr-bin"))
    assert "Python 3.12 is installed" in sentence and "python3.12-venv" in sentence
    assert not stage.venv.exists()                      # nothing half made is left for the next run to trip over
    assert not any("-m venv" in line for line in stage.asked())


def test_in_a_codespace_the_sentence_says_what_to_do_there(stage):
    stage.python("usr-bin", "the system one", parts=False, makes="half")
    sentence = stopped_with_one_plain_sentence(stage.run("usr-bin", codespace=True))
    assert "Codespace" in sentence and "README.md" in sentence
    assert "apt install" not in sentence                # that advice is for a computer of one's own
    assert not stage.venv.exists()


@pytest.mark.slow
def test_with_the_real_python_the_environment_is_really_made(stage):
    """The pretend Pythons above answer the way Python does. This one asks the real Python, which takes a few seconds."""
    real = os.path.realpath(sys.executable)             # the Python under the one running these tests
    if subprocess.run([real, "-c", "import venv, ensurepip"], capture_output=True, timeout=60).returncode != 0:
        pytest.skip("the Python under this test run has no venv and ensurepip, so it can't make an environment")
    program(stage.folder / "real" / "python3.12", f'#!{BASH}\nexec {shlex.quote(real)} "$@"\n')
    stage.half_made("no pip")
    done = stage.run("real")
    assert done.returncode == 0, done.stderr
    pip = subprocess.run([str(stage.venv / "bin" / "python"), "-m", "pip", "--version"], capture_output=True, text=True,
                         timeout=60)
    assert pip.returncode == 0 and pip.stdout.startswith("pip ")
    assert not (stage.venv / "left-from-before").exists()
    assert (stage.venv / ".requirements-installed").exists()
