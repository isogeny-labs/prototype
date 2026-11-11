"""./run-demo.sh prepares isolated mode before the app starts, and that step can never stop the start."""
import re
import subprocess

from app.config import REPO_ROOT

SCRIPT = REPO_ROOT / "run-demo.sh"


def test_the_script_is_valid_shell():
    assert subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, timeout=20).returncode == 0


def test_prepare_is_called_before_the_start_and_cannot_fail_it():
    text = SCRIPT.read_text(encoding="utf-8")
    calls = [m.start() for m in re.finditer(r"-m app\.prepare", text)]
    assert calls and max(calls) < text.index('exec "$VENV/bin/python" -m app')
    for line in (l for l in text.splitlines() if "-m app.prepare" in l):
        assert line.rstrip().endswith("\\")  # the next line is the `|| echo ...` guard
    assert text.count("-m app.prepare") == text.count('|| echo "   Isolated mode could not be prepared.')
    assert "command -v docker" in text
    # the script itself never pulls or builds: only app.prepare may
    for word in ("docker pull", "docker build", "docker run", "curl ", "wget "):
        assert word not in text
