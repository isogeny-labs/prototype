"""The demo repository that ships with the app (demo/repos/acme-sign.git, Demo data) and the module that makes
it (app/demo_repo.py). This is what "Connect demo code" connects, so it must hold our registered acme-sign 1.4.2
and nothing else."""
import shutil
from pathlib import Path

import pytest

from app import components, demo_repo, gitrepo
from app.config import DEMO_DIR
from app.gitrepo import GitRepo, GitRepoError, Person
from test_gitrepo import fsck, listing, real_git, strip_hint

BUNDLED = DEMO_DIR / "repos" / "acme-sign.git"
ACME = DEMO_DIR / "components" / "acme-sign-1.4.2" / "acme_sign.py"
ACME_143 = DEMO_DIR / "components" / "acme-sign-1.4.3" / "acme_sign.py"
FIXER = Person("Evidence Lab fix template", "fix-template@example.invalid")
USER = Person("Evidence Lab user", "user@example.invalid")
TITLE = "Reject signatures whose r or s is out of range"


def test_bundled_repository_holds_exactly_the_registered_1_4_2():
    assert demo_repo.bundled("acme-sign") == BUNDLED and components.lookup("acme-sign", "1.4.2") == ACME
    repo = GitRepo(BUNDLED)
    assert repo.head_branch() == "main" and list(repo.branches()) == ["main"]      # one branch
    commit = repo.read_commit(repo.branch("main"))
    assert commit.parents == () and len(repo.history(commit.sha)) == 1             # one commit
    assert repo.files(commit.sha) == {"acme_sign.py": ACME.read_bytes()}           # one file, byte for byte
    assert commit.author == commit.committer == Person("Acme Pay demo", "demo@example.invalid")
    assert commit.author_time == commit.commit_time == 1794300000
    assert commit.message == "acme-sign 1.4.2 (demo software)"


def test_making_it_again_gives_the_same_commit(tmp_path):
    """Author, time and message are fixed, so the repository made again from the same file is the very same one.
    If this fails after a change to the registered 1.4.2, run: cd backend && .venv/bin/python -m app.demo_repo"""
    fresh = demo_repo.make(tmp_path / "again.git")
    assert GitRepo(BUNDLED).branches() == {"main": fresh} == GitRepo(tmp_path / "again.git").branches()
    assert listing(tmp_path / "again.git") == listing(BUNDLED)        # the same pieces under the same ids
    with pytest.raises(GitRepoError, match="not empty"):
        demo_repo.make(tmp_path / "again.git")


def test_bundled_folder_holds_no_settings_no_hooks_and_no_packed_objects():
    """Only what this app reads is there: HEAD, the one branch and three loose objects (the commit, its file
    list and the file). So there is nothing in it that git, or anything else, could be made to run."""
    repo = GitRepo(BUNDLED)
    commit = repo.read_commit(repo.branch("main"))
    ids = sorted([commit.sha, commit.tree, repo.file_ids(commit.sha)["acme_sign.py"]])
    assert listing(BUNDLED) == ["HEAD", "objects", *[part for sha in ids for part in (f"objects/{sha[:2]}", f"objects/{sha[:2]}/{sha[2:]}")],
                                "refs", "refs/heads", "refs/heads/main"]
    assert not any(path.is_symlink() for path in BUNDLED.rglob("*"))
    assert (BUNDLED / "HEAD").read_text() == "ref: refs/heads/main\n"
    assert (BUNDLED / "refs" / "heads" / "main").read_text() == commit.sha + "\n"


@pytest.mark.parametrize("name", ["acme-sign ", "Acme-Sign", "acme-sign.git", "acme-sign-1.4.2", "acme-sign/../acme-sign",
                                  "../repos/acme-sign", "other-tool", "", None, 5, ["acme-sign"]], ids=repr)
def test_only_the_one_exact_name_has_a_bundled_repository(name):
    assert demo_repo.bundled(name) is None


def test_the_command_makes_it_again_in_place_and_keeps_the_old_one_when_it_cannot(tmp_path, monkeypatch):
    monkeypatch.setattr(demo_repo, "REPOS_DIR", tmp_path / "repos")      # a temp folder, never the project's own
    target, said = tmp_path / "repos" / "acme-sign.git", []
    assert demo_repo.main(said.append) == 0 and demo_repo.bundled("acme-sign") == target
    commit = GitRepo(BUNDLED).branch("main")
    assert GitRepo(target).branches() == {"main": commit} and commit in "\n".join(said)
    (target / "left-over.txt").write_text("from an earlier time\n")
    assert demo_repo.main(said.append) == 0                              # made afresh, not on top of the old one
    assert listing(target) == listing(BUNDLED) and [p.name for p in (tmp_path / "repos").iterdir()] == ["acme-sign.git"]

    monkeypatch.setattr(components, "lookup", lambda name, version: None)   # the registered file is gone
    said.clear()
    assert demo_repo.main(said.append) == 1 and "not made" in said[0] and len(said) == 1
    assert listing(target) == listing(BUNDLED) and GitRepo(target).branches() == {"main": commit}   # the old one is as it was
    assert [p.name for p in (tmp_path / "repos").iterdir()] == ["acme-sign.git"]


def test_nothing_is_run_to_make_it():
    source = Path(demo_repo.__file__).read_text()
    for banned in ("subprocess", "os.system", "popen", "eval(", "exec(", "importlib", "run_component", "pickle"):
        assert banned not in source


def test_the_demo_fix_as_a_branch_and_a_merge_on_a_copy(tmp_path):
    """What Fixes will do with a connected copy, with the pieces of the foundation only: the fix as a branch on
    top of main, its size, and a merge after which main holds the registered 1.4.3 byte for byte."""
    before = listing(BUNDLED)
    repo = GitRepo(shutil.copytree(BUNDLED, tmp_path / "acme-sign.git"))
    base, old, new = repo.branch("main"), ACME.read_bytes(), ACME_143.read_bytes()
    tip = repo.branch_from("fix/ecdsa-range-check", base, {"acme_sign.py": new}, TITLE, FIXER, 1794300600)
    assert repo.read_commit(tip).parents == (base,) and repo.files(tip) == {"acme_sign.py": new}
    assert gitrepo.count_changes(old.decode(), new.decode()) == (3, 1)
    patch = gitrepo.format_patch(repo.read_commit(tip), repo.files(base), repo.files(tip), "Isogeny Evidence Lab (demo)")
    assert f"Subject: [PATCH] {TITLE}\n\n---\n acme_sign.py | 4 +++-\n 1 file changed, 3 insertions(+), 1 deletion(-)\n\n" in patch
    assert ('         r, s = der_decode(bytes.fromhex(req["signature"]))\n     except ValueError:\n'
            '         return {"valid": False}\n+    if not (1 <= r < N and 1 <= s < N):\n+        return {"valid": False}\n'
            "     e = digest_int(message)\n") in patch
    merged = repo.merge("main", "fix/ecdsa-range-check", f"Merge pull request #1: {TITLE}", USER, 1794301200)
    assert repo.read_commit(merged).parents == (base, tip) and repo.branch("main") == merged
    assert repo.files(merged) == {"acme_sign.py": new} and components.lookup("acme-sign", "1.4.3").read_bytes() == new
    assert listing(BUNDLED) == before and GitRepo(BUNDLED).branches() == {"main": base}   # the bundled one is untouched


# ------------------------------------------------------------------ checked by git itself (skipped without git)

def test_git_itself_finds_nothing_wrong_with_the_bundled_repository(tmp_path):
    git = real_git(tmp_path)
    copy = shutil.copytree(BUNDLED, tmp_path / "acme-sign.git")   # git only sees a copy: it cannot leave anything in the project
    assert fsck(git, copy) == ""
    commit = GitRepo(BUNDLED).branch("main")
    assert git("--git-dir", copy, "rev-parse", "main", "HEAD").stdout.decode().split() == [commit, commit]
    assert git("--git-dir", copy, "show", "main:acme_sign.py").stdout == ACME.read_bytes()
    assert git("--git-dir", copy, "log", "--format=%an <%ae>|%cn <%ce>|%at|%ct|%s|%P", "main").stdout.decode() == (
        "Acme Pay demo <demo@example.invalid>|Acme Pay demo <demo@example.invalid>|1794300000|1794300000|"
        "acme-sign 1.4.2 (demo software)|\n")
    assert git("--git-dir", copy, "count-objects", "-v").stdout.decode().split()[:2] == ["count:", "3"]
    assert listing(copy) == listing(BUNDLED)                      # reading it, git added nothing


def test_git_shows_and_applies_the_demo_fix_exactly_as_we_do(tmp_path):
    git = real_git(tmp_path)
    repo = GitRepo(shutil.copytree(BUNDLED, tmp_path / "acme-sign.git"))
    base, old, new = repo.branch("main"), ACME.read_bytes(), ACME_143.read_bytes()
    tip = repo.branch_from("fix/ecdsa-range-check", base, {"acme_sign.py": new},
                           f"{TITLE}\n\nAdds the range check and sets the version to 1.4.3.", FIXER, 1794300600)
    theirs = git("--git-dir", repo.path, "diff", "main", "fix/ecdsa-range-check").stdout.decode()
    assert gitrepo.unified_diff(old, new, "acme_sign.py") == strip_hint(theirs)
    assert git("--git-dir", repo.path, "diff", "--numstat", "main", "fix/ecdsa-range-check").stdout.decode() == "3\t1\tacme_sign.py\n"

    patch = tmp_path / "acme-sign-pull-request-1.patch"
    patch.write_bytes(gitrepo.format_patch(repo.read_commit(tip), repo.files(base), repo.files(tip), "Isogeny Evidence Lab (demo)").encode())
    checkout = tmp_path / "checkout"
    git("clone", "-q", repo.path, checkout)
    assert (checkout / "acme_sign.py").read_bytes() == old
    git("apply", "--check", patch, cwd=checkout)
    git("am", "-q", patch, cwd=checkout)
    assert (checkout / "acme_sign.py").read_bytes() == new        # the registered 1.4.3, byte for byte
    assert git("log", "-1", "--format=%T|%P|%an <%ae>|%s", cwd=checkout).stdout.decode().strip() == (
        f"{repo.read_commit(tip).tree}|{base}|Evidence Lab fix template <fix-template@example.invalid>|{TITLE}")

    merged = repo.merge("main", "fix/ecdsa-range-check", f"Merge pull request #1: {TITLE}", USER, 1794301200)
    assert fsck(git, repo.path) == ""
    assert git("--git-dir", repo.path, "log", "-1", "--format=%H %P", "main").stdout.decode().split() == [merged, base, tip]
    assert git("--git-dir", repo.path, "show", "main:acme_sign.py").stdout == new
