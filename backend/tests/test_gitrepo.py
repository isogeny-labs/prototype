"""The small git reader and writer (app/gitrepo.py).

What it writes has to be what git itself would write. So the ids below were worked out once with the real git
program, and the tests at the end ask git itself when it is installed. They are skipped with a message when
it is not: the app never needs git.
"""
import os
import re
import shutil
import subprocess
import zlib
from pathlib import Path

import pytest

from app import gitrepo
from app.gitrepo import Commit, GitRepo, GitRepoError, Person, Spot

WHO = Person("Test Person", "test@example.invalid")
OTHER = Person("Other One", "other@example.invalid")

# Ids git itself gives (git hash-object, git mktree, git commit-tree), so they are checked without git too.
EMPTY_BLOB, EMPTY_TREE = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391", "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
HELLO = "ce013625030ba8dba906f756967f9e9ca394464a"                                              # the blob "hello\n"
ONE, TWO = "5626abf0f72e58d7a153368ba57db4c673c0e171", "f719efd430d52bcfc8566a43b2eb655688d38871"  # "one\n", "two\n"
TREE = "6640fb01ffae1cdd778a3fe65b469f62a5230def"                                               # a.txt = one, b.txt = two
FIRST = "44db2ddd3ccebb877e9c90f98071c1ab5d7b5f5d"   # TREE, no parent, WHO, 1700000000, "First commit" + "With a body."
SECOND = "110d6bc9a85a56f94bc3de9a7966df03fc975133"  # TREE, parent FIRST, WHO wrote it, OTHER saved it, 1700000600, "Second"

GIT_SKIP = ("Skipped: the git program is not installed here, so what the app writes "
            "could not be checked against git itself.")


@pytest.fixture
def repo(tmp_path):
    return GitRepo.create(tmp_path / "work.git")


def real_git(folder):
    """The real git program for one test, or a skip with a clear message when it is not installed.
    It sees no user or system settings, and it is only ever pointed at temp folders, never at this project."""
    if shutil.which("git") is None:
        pytest.skip(GIT_SKIP)
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(folder), "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CEILING_DIRECTORIES": str(folder),
           "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C",
           "GIT_COMMITTER_NAME": "Somebody Else", "GIT_COMMITTER_EMAIL": "else@example.invalid"}

    def run(*args, cwd=folder, data=None, env_extra=None):
        done = subprocess.run(["git", *map(str, args)], cwd=cwd, input=data, capture_output=True,
                              env={**env, **(env_extra or {})}, timeout=60)
        assert done.returncode == 0, f"git {args[0]} failed: {done.stderr.decode(errors='replace')}"
        return done
    return run


@pytest.fixture
def git(tmp_path):
    return real_git(tmp_path)


def object_file(repo, sha):
    return repo.path / "objects" / sha[:2] / sha[2:]


def store(repo, kind, body):
    """Put an object into the repository by hand, laid out as git does, so a test can hold content that
    GitRepo itself refuses to write."""
    sha = gitrepo.object_id(kind, body)
    object_file(repo, sha).parent.mkdir(exist_ok=True)
    object_file(repo, sha).write_bytes(zlib.compress(kind.encode() + b" " + str(len(body)).encode() + b"\0" + body))
    return sha


def listing(folder):
    return sorted(p.relative_to(folder).as_posix() for p in Path(folder).rglob("*"))


# ------------------------------------------------------------------ making and opening a repository

def test_a_repository_is_made_only_in_an_empty_folder_and_opened_only_where_one_is(tmp_path):
    with pytest.raises(GitRepoError, match="No repository"):
        GitRepo(tmp_path)
    repo = GitRepo.create(tmp_path / "new.git", "trunk")
    assert repo.head_branch() == "trunk" and repo.branches() == {} and repo.branch("trunk") is None
    assert listing(repo.path) == ["HEAD", "objects", "refs", "refs/heads"]   # no settings file, no hooks
    assert GitRepo(repo.path).head_branch() == "trunk"
    (tmp_path / "empty").mkdir()
    assert GitRepo.create(tmp_path / "empty").head_branch() == "main"         # a folder that is there but empty will do
    with pytest.raises(GitRepoError, match="not empty"):
        GitRepo.create(repo.path)
    with pytest.raises(GitRepoError):
        GitRepo.create(tmp_path / "bad.git", "../outside")
    assert not (tmp_path / "bad.git").exists()


# ------------------------------------------------------------------ blobs, trees, commits

def test_blobs_trees_and_commits_round_trip_with_the_ids_git_gives(repo):
    assert gitrepo.blob_id(b"") == EMPTY_BLOB and gitrepo.blob_id(b"hello\n") == HELLO
    one, two = repo.write_blob(b"one\n"), repo.write_blob(b"two\n")
    assert (one, two) == (ONE, TWO) and repo.read_blob(one) == b"one\n" and repo.read_blob(two) == b"two\n"
    assert zlib.decompress(object_file(repo, one).read_bytes()) == b"blob 4\0one\n"   # git's own layout on disk
    everything = bytes(range(256)) * 3
    assert repo.read_blob(repo.write_blob(everything)) == everything and repo.write_blob(b"") == EMPTY_BLOB
    before = listing(repo.path)
    assert repo.write_blob(b"one\n") == one and listing(repo.path) == before   # the same content is stored once

    tree = repo.write_tree({"b.txt": two, "a.txt": one})                       # stored sorted by name
    assert tree == TREE and list(repo.read_tree(tree).items()) == [("a.txt", one), ("b.txt", two)]
    assert repo.write_tree({}) == EMPTY_TREE and repo.read_tree(EMPTY_TREE) == {}

    first = repo.write_commit(tree, (), WHO, 1700000000, "First commit\n\nWith a body.")
    second = repo.write_commit(tree, [first], WHO, 1700000600, "Second", committer=OTHER)
    assert (first, second) == (FIRST, SECOND)
    assert repo.read_commit(first) == Commit(first, tree, (), WHO, 1700000000, WHO, 1700000000, "First commit\n\nWith a body.")
    assert repo.read_commit(first).title == "First commit"
    assert repo.read_commit(second) == Commit(second, tree, (first,), WHO, 1700000600, OTHER, 1700000600, "Second")


def test_a_name_or_a_message_cannot_add_lines_to_a_commit(repo):
    tree = repo.write_tree({})
    sneaky = Person("Eve\nparent " + "1" * 40, "<eve@example.invalid>\n")
    commit = repo.read_commit(repo.write_commit(tree, (), sneaky, 5, "\n\nThe message\r\n\n"))
    assert commit.parents == () and commit.message == "The message"
    assert commit.author == Person("Eveparent " + "1" * 40, "eve@example.invalid")
    assert repo.read_commit(repo.write_commit(tree, (), Person("", " "), 5, "x")).author == Person("unknown", "unknown")


def test_objects_that_are_too_large_are_refused(repo, monkeypatch):
    monkeypatch.setattr(gitrepo, "MAX_OBJECT_BYTES", 1000)
    assert repo.read_blob(repo.write_blob(b"x" * 1000)) == b"x" * 1000
    with pytest.raises(GitRepoError, match="too large"):
        repo.write_blob(b"x" * 1001)
    big = store(repo, "blob", b"\0" * 50_000)      # put there by something else; it packs down to a few bytes
    with pytest.raises(GitRepoError, match="too large"):
        repo.read_blob(big)
    with pytest.raises(GitRepoError, match="more files"):
        repo.write_tree({f"f{n}.txt": EMPTY_BLOB for n in range(gitrepo.MAX_FILES + 1)})


# ------------------------------------------------------------------ branches

def test_branches_commits_files_and_history_round_trip(repo):
    assert repo.head_branch() == "main" and repo.branches() == {} and repo.branch("main") is None
    first = repo.commit("main", {"a.txt": b"one\n", "b.txt": b"two\n"}, "First", WHO, 100, None)
    second = repo.commit("main", {"a.txt": b"ONE\n", "b.txt": b"two\n"}, "Second\n\nWhy: a test.", WHO, 200, first)
    side = repo.branch_from("fix/side-1.2", second, {"a.txt": b"ONE\n", "b.txt": b"2\n", "c.txt": b""}, "Side", OTHER, 300)
    assert repo.branch("main") == second and repo.branch("fix/side-1.2") == side and repo.branch("fix") is None
    assert repo.branches() == {"fix/side-1.2": side, "main": second} == GitRepo(repo.path).branches()
    assert (repo.path / "refs" / "heads" / "fix" / "side-1.2").read_text() == side + "\n"
    assert sorted(p.name for p in repo.path.iterdir()) == ["HEAD", "objects", "refs"]   # no working file left behind
    assert repo.files(first) == {"a.txt": b"one\n", "b.txt": b"two\n"}
    assert repo.files(side) == {"a.txt": b"ONE\n", "b.txt": b"2\n", "c.txt": b""}
    assert repo.file_ids(second) == {"a.txt": gitrepo.blob_id(b"ONE\n"), "b.txt": TWO}
    assert repo.read_commit(first).parents == () and repo.read_commit(side).parents == (second,)
    assert [(c.sha, c.title, c.author, c.commit_time) for c in repo.history(side)] == [
        (side, "Side", OTHER, 300), (second, "Second", WHO, 200), (first, "First", WHO, 100)]
    assert [c.sha for c in repo.history(side, limit=2)] == [side, second]
    assert repo.is_ancestor(first, side) and repo.is_ancestor(side, side) and not repo.is_ancestor(side, second)

    with pytest.raises(GitRepoError, match="already exists"):
        repo.branch_from("main", first, {"a.txt": b"x\n"}, "Taken", WHO, 400)
    with pytest.raises(GitRepoError, match="missing"):       # a start that is not a commit of this repository
        repo.branch_from("other", "1" * 40, {"a.txt": b"x\n"}, "Nowhere", WHO, 400)
    assert repo.branches() == {"fix/side-1.2": side, "main": second}


GOOD_BRANCH_NAMES = ["main", "fix/ecdsa-range-check", "release-1.4.3", "a_b/c.d/E9", "x" * 100]
BAD_BRANCH_NAMES = [
    "", " ", "a b", "..", "../x", "a/../b", "a..b", ".hidden", "a/.b", "a.", "x.lock", "a.lock/b", "/abs", "a/", "a//b",
    "-dash", "a\\b", "a:b", "a~1", "a^", "a?", "a*", "a[b", "a@{1}", "main\n", "ma\0in", "café", "x" * 101,
    "refs/heads/../../HEAD", None, 5, b"main", ["main"],
]


@pytest.mark.parametrize("name", GOOD_BRANCH_NAMES)
def test_ordinary_branch_names_are_accepted(repo, name):
    assert gitrepo.check_branch_name(name) == name
    sha = repo.commit(name, {"a.txt": b"1\n"}, "one", WHO, 1, None)
    assert repo.branches() == {name: sha}


@pytest.mark.parametrize("name", BAD_BRANCH_NAMES, ids=repr)
def test_every_bad_branch_name_is_refused_everywhere(repo, tmp_path, name):
    first = repo.commit("main", {"a.txt": b"1\n"}, "one", WHO, 1, None)
    before = listing(tmp_path)
    for use in (gitrepo.check_branch_name, repo.branch, lambda n: repo.set_branch(n, first, None),
                lambda n: repo.commit(n, {"a.txt": b"2\n"}, "two", WHO, 2, None),
                lambda n: repo.branch_from(n, first, {"a.txt": b"2\n"}, "two", WHO, 2),
                lambda n: repo.merge(n, "main", "merge", WHO, 3), lambda n: repo.merge("main", n, "merge", WHO, 3),
                lambda n: GitRepo.create(tmp_path / "another.git", n)):
        with pytest.raises(GitRepoError):
            use(name)
    assert repo.branches() == {"main": first}
    assert [p for p in listing(tmp_path) if not p.startswith("work.git/objects/")] == \
           [p for p in before if not p.startswith("work.git/objects/")]   # no branch file anywhere, in or out of the repository


def test_a_name_that_needs_a_folder_where_another_branch_is_a_file_is_refused(repo):
    first = repo.commit("main", {"a.txt": b"1\n"}, "one", WHO, 1, None)
    side = repo.branch_from("fix/one", first, {"a.txt": b"2\n"}, "two", WHO, 2)
    before = listing(repo.path / "refs")
    for name in ("main/sub", "fix", "fix/one/more"):
        with pytest.raises(GitRepoError, match="clashes"):
            repo.set_branch(name, first, None)
        with pytest.raises(GitRepoError, match="clashes"):
            repo.branch_from(name, first, {"a.txt": b"3\n"}, "three", WHO, 3)
    assert listing(repo.path / "refs") == before and repo.branches() == {"fix/one": side, "main": first}
    repo.set_branch("fix/two", first, None)      # a second branch beside it is fine


def test_a_branch_is_moved_only_from_where_the_caller_last_saw_it(repo):
    first = repo.commit("main", {"a.txt": b"1\n"}, "one", WHO, 1, None)
    second = repo.commit("main", {"a.txt": b"2\n"}, "two", WHO, 2, first)
    for stale in (first, None, "1" * 40):                    # main moved on to `second` in the meantime
        with pytest.raises(GitRepoError, match="changed in the meantime"):
            repo.set_branch("main", first, stale)
        with pytest.raises(GitRepoError, match="changed in the meantime"):
            repo.commit("main", {"a.txt": b"3\n"}, "three", WHO, 3, stale)
    with pytest.raises(GitRepoError, match="changed in the meantime"):
        repo.set_branch("new", first, first)                 # said to exist, but it does not
    assert repo.branches() == {"main": second}
    # only a commit of this repository can be pointed at
    for not_a_commit in (repo.read_commit(second).tree, gitrepo.blob_id(b"2\n"), "1" * 40):
        with pytest.raises(GitRepoError):
            repo.set_branch("main", not_a_commit, second)
    assert repo.branches() == {"main": second}
    repo.set_branch("main", first, second)                   # with the right last-seen commit it moves, even back
    repo.set_branch("new", second, None)
    assert repo.branches() == {"main": first, "new": second}


def test_a_damaged_branch_file_or_head_is_noticed(repo):
    first = repo.commit("main", {"a.txt": b"1\n"}, "one", WHO, 1, None)
    ref = repo.path / "refs" / "heads" / "main"
    for damage in (b"", b"not an id\n", first[:39].encode() + b"\n", f"{first}\n{first}\n".encode(), b"\xff\xfe\x00 not text"):
        ref.write_bytes(damage)
        with pytest.raises(GitRepoError):
            repo.branch("main")
        with pytest.raises(GitRepoError):
            repo.branches()
        with pytest.raises(GitRepoError):
            repo.set_branch("main", first, first)
    ref.write_text("1" * 40 + "\n")                           # well formed, but that commit is not there
    with pytest.raises(GitRepoError, match="missing"):
        repo.files(repo.branch("main"))
    ref.write_text(first + "\n")
    (repo.path / "refs" / "heads" / "link").symlink_to(ref)   # a link is not followed
    assert repo.branch("link") is None and repo.branches() == {"main": first}
    for damage in (b"\xff\xfe", first.encode() + b"\n", b"ref: refs/heads/../../outside\n", b"ref: refs/tags/v1\n"):
        (repo.path / "HEAD").write_bytes(damage)
        with pytest.raises(GitRepoError):
            repo.head_branch()


# ------------------------------------------------------------------ file names and ids

BAD_FILE_NAMES = ["", " ", ".", "..", ".git", ".hidden", "a/b", "../x", "/abs", "x y", "a\\b", "a\nb", "name.py\n", "a\0b",
                  "con.lock", "-rf", "café.py", "x" * 101, None, 7, b"a.py"]


@pytest.mark.parametrize("name", BAD_FILE_NAMES, ids=repr)
def test_every_bad_file_name_is_refused_everywhere(repo, tmp_path, name):
    first = repo.commit("main", {"a.txt": b"1\n"}, "one", WHO, 1, None)
    for use in (gitrepo.check_file_name, lambda n: repo.write_tree({n: EMPTY_BLOB}),
                lambda n: repo.commit("main", {n: b"2\n"}, "two", WHO, 2, first),
                lambda n: repo.branch_from("side", first, {"a.txt": b"1\n", n: b"2\n"}, "two", WHO, 2),
                lambda n: gitrepo.unified_diff(b"1\n", b"2\n", n),
                lambda n: gitrepo.format_patch(repo.read_commit(first), {n: b"1\n"}, {n: b"2\n"}, "footer")):
        with pytest.raises(GitRepoError):
            use(name)
    assert repo.branches() == {"main": first}
    for good in ("acme_sign.py", "README", "a-b_c.d.txt", "_x", "x" * 100):
        assert gitrepo.check_file_name(good) == good


def test_bad_file_names_inside_a_repository_are_refused_when_read(repo):
    """A repository is data from outside: what its folder listings say is checked like everything else."""
    blob = repo.write_blob(b"data\n")
    for entry in (b"100644 ../outside", b"100644 .git", b"100644 sub/file", b"100644 two words", b"100644 caf\xc3\xa9",
                  b"40000 folder", b"120000 link", b"160000 other-repository"):
        tree = store(repo, "tree", entry + b"\0" + bytes.fromhex(blob))
        with pytest.raises(GitRepoError):
            repo.read_tree(tree)
        commit = repo.write_commit(tree, (), WHO, 1, "holds it")
        with pytest.raises(GitRepoError):
            repo.files(commit)
    for body in (b"100644 a.txt\0" + bytes.fromhex(blob)[:19], b"100644 a.txt", b"junk"):   # cut short
        with pytest.raises(GitRepoError, match="damaged folder listing"):
            repo.read_tree(store(repo, "tree", body))


BAD_IDS = ["", "abc", "g" * 40, "A" * 40, "a" * 39, "a" * 41, "a" * 40 + "\n", " " + "a" * 39, "../" + "a" * 37,
           "a" * 38 + "/a", None, 123, b"a" * 40]


@pytest.mark.parametrize("bad", BAD_IDS, ids=repr)
def test_every_bad_id_is_refused_everywhere(repo, tmp_path, bad):
    first = repo.commit("main", {"a.txt": b"1\n"}, "one", WHO, 1, None)
    tree, before = repo.read_commit(first).tree, listing(tmp_path)
    for use in (repo.read_blob, repo.read_tree, repo.read_commit, repo.files, repo.file_ids,
                lambda sha: repo.write_tree({"a.txt": sha}), lambda sha: repo.write_commit(sha, (), WHO, 2, "x"),
                lambda sha: repo.write_commit(tree, (first, sha), WHO, 2, "x"),
                lambda sha: repo.set_branch("other", sha, None),
                lambda sha: repo.branch_from("other", sha, {"a.txt": b"2\n"}, "x", WHO, 2),
                lambda sha: repo.is_ancestor(first, sha)):
        with pytest.raises(GitRepoError):
            use(bad)
    if bad:   # an empty id is where a history ends, so it gives an empty history
        with pytest.raises(GitRepoError):
            repo.history(bad)
    assert repo.branches() == {"main": first} and listing(tmp_path) == before   # nothing was written anywhere


def test_a_commit_this_app_cannot_read_is_refused(repo):
    tree = repo.write_tree({})
    person = "Test Person <test@example.invalid> 5 +0000"
    for text in (f"author {person}\ncommitter {person}\n\nno tree\n", f"tree {tree}\ncommitter {person}\n\nno author\n",
                 f"tree {tree}\nauthor {person}\n\nno committer\n", f"tree not-an-id\nauthor {person}\ncommitter {person}\n\nx\n",
                 f"tree {tree}\nparent ../x\nauthor {person}\ncommitter {person}\n\nx\n",
                 f"tree {tree}\nauthor Test Person 5 +0000\ncommitter {person}\n\nx\n",
                 f"tree {tree}\nauthor {person} and more\ncommitter {person}\n\nx\n"):
        with pytest.raises(GitRepoError):
            repo.read_commit(store(repo, "commit", text.encode()))
    # a commit written by another git client, with lines this app has no use for, is read
    signed = (f"tree {tree}\nauthor Zoë <zoe@example.invalid> 1700000000 +0100\ncommitter {person}\n"
              "gpgsig -----BEGIN PGP SIGNATURE-----\n \n abc\n -----END PGP SIGNATURE-----\nencoding UTF-8\n\nSigned\n\nBody\n")
    commit = repo.read_commit(store(repo, "commit", signed.encode()))
    assert (commit.author, commit.author_time, commit.committer, commit.commit_time, commit.message) == (
        Person("Zoë", "zoe@example.invalid"), 1700000000, WHO, 5, "Signed\n\nBody")


# ------------------------------------------------------------------ damage on disk

def test_an_object_damaged_on_disk_is_noticed(repo):
    first = repo.commit("main", {"a.txt": b"the first file\n" * 20, "b.txt": b"the second file\n" * 20}, "one", WHO, 1, None)
    ids = repo.file_ids(first)
    good = object_file(repo, ids["a.txt"]).read_bytes()

    def damaged(data):
        object_file(repo, ids["a.txt"]).write_bytes(data)
        for read in (lambda: repo.read_blob(ids["a.txt"]), lambda: repo.files(first)):
            with pytest.raises(GitRepoError):
                read()

    for at in range(len(good)):                                     # any one byte of the stored file changed
        damaged(good[:at] + bytes([good[at] ^ 0xFF]) + good[at + 1:])
    for cut in range(1, len(good) + 1):                             # cut short anywhere, even by one byte
        damaged(good[:-cut])
    damaged(good + b"\n")                                           # something added after it
    damaged(b"blob 15\0the first file\n")                           # not packed the way git packs objects
    damaged(object_file(repo, ids["b.txt"]).read_bytes())           # another object's content under this id
    damaged(zlib.compress(b"blob 999\0" + b"the first file\n" * 20))  # says a size it does not have
    damaged(zlib.compress(b"commit 300\0" + b"the first file\n" * 20))  # says it is something else
    damaged(zlib.compress(b"the first file\n" * 20))                # no header at all
    object_file(repo, ids["a.txt"]).unlink()
    with pytest.raises(GitRepoError, match="missing"):
        repo.read_blob(ids["a.txt"])
    object_file(repo, ids["a.txt"]).symlink_to(object_file(repo, ids["b.txt"]))   # a link is not followed
    with pytest.raises(GitRepoError, match="missing"):
        repo.read_blob(ids["a.txt"])
    object_file(repo, ids["a.txt"]).unlink()
    object_file(repo, ids["a.txt"]).write_bytes(good)               # put back as it was: it reads again
    assert repo.files(first)["a.txt"] == b"the first file\n" * 20
    assert repo.read_blob(ids["b.txt"]) == b"the second file\n" * 20  # the other file was readable all along


def test_an_object_is_only_read_as_what_it_is(repo):
    first = repo.commit("main", {"a.txt": b"1\n"}, "one", WHO, 1, None)
    tree, blob = repo.read_commit(first).tree, repo.file_ids(first)["a.txt"]
    for read, sha in ((repo.read_commit, tree), (repo.read_commit, blob), (repo.read_tree, first), (repo.read_tree, blob),
                      (repo.read_blob, first), (repo.read_blob, tree), (repo.files, tree), (repo.history, blob)):
        with pytest.raises(GitRepoError, match="unexpected kind"):
            read(sha)


# ------------------------------------------------------------------ merge

def test_merge_makes_a_two_parent_commit(repo):
    base = repo.commit("main", {"a.txt": b"old\n", "b.txt": b"same\n"}, "Base", WHO, 10, None)
    tip = repo.branch_from("fix/a", base, {"a.txt": b"new\n", "b.txt": b"same\n"}, "Change a", OTHER, 20)
    merged = repo.merge("main", "fix/a", "Merge pull request #1: Change a\n", WHO, 30)
    commit = repo.read_commit(merged)
    assert commit.parents == (base, tip) and commit.tree == repo.read_commit(tip).tree
    assert (commit.author, commit.committer, commit.commit_time, commit.message) == (WHO, WHO, 30, "Merge pull request #1: Change a")
    assert repo.branches() == {"fix/a": tip, "main": merged}        # the branch that was merged stays where it was
    assert repo.files(merged) == {"a.txt": b"new\n", "b.txt": b"same\n"}
    assert [c.sha for c in repo.history(merged)] == [merged, base]  # first parents: what main itself went through
    assert repo.is_ancestor(tip, merged) and repo.is_ancestor(base, merged) and not repo.is_ancestor(merged, tip)


def test_merge_is_refused_when_the_target_moved_or_nothing_is_ahead(repo):
    base = repo.commit("main", {"a.txt": b"old\n"}, "Base", WHO, 10, None)
    tip = repo.branch_from("fix/a", base, {"a.txt": b"new\n"}, "Change a", OTHER, 20)
    repo.set_branch("same", base, None)
    with pytest.raises(GitRepoError, match="holds nothing new"):    # points at the very commit main points at
        repo.merge("main", "same", "Merge", WHO, 30)
    for into, source in (("main", "missing"), ("missing", "fix/a"), ("missing", "gone")):
        with pytest.raises(GitRepoError, match="does not exist"):
            repo.merge(into, source, "Merge", WHO, 30)
    moved = repo.commit("main", {"a.txt": b"old\n", "b.txt": b"someone else\n"}, "Something else", WHO, 25, base)
    with pytest.raises(GitRepoError, match="has changed since"):    # main moved after the change was made
        repo.merge("main", "fix/a", "Merge", WHO, 30)
    with pytest.raises(GitRepoError, match="Nothing was merged"):   # behind main: nothing is ahead
        repo.merge("main", "same", "Merge", WHO, 30)
    assert repo.branches() == {"fix/a": tip, "main": moved, "same": base}
    assert repo.files(moved) == {"a.txt": b"old\n", "b.txt": b"someone else\n"}

    merged = repo.merge("same", "fix/a", "Merge", WHO, 30)          # where nothing else changed, it merges
    with pytest.raises(GitRepoError, match="Nothing was merged"):   # and a second time there is nothing left to merge
        repo.merge("same", "fix/a", "Merge again", WHO, 40)
    assert repo.branches() == {"fix/a": tip, "main": moved, "same": merged}


# ------------------------------------------------------------------ what changed between two texts

def program(extra=()):
    """A text shaped like a small program: 60 three-line functions, then one that turns a bad value away,
    with the lines `extra` put in right after that. It is over 200 lines with many blank ones, which is where
    Python's difflib, left at its default, lines the two texts up wrongly (see gitrepo._matcher)."""
    lines = []
    for n in range(60):
        lines += [f"def step_{n}(value):", f"    return value + {n}", ""]
    lines += ["def check(text):", "    try:", "        value = parse(text)", "    except ValueError:", "        return None"]
    lines += list(extra)
    lines += [f"    value = step_{n}(value)" for n in range(40)] + ["    return value"]
    return "\n".join(lines) + "\n"


TEN = "".join(f"line {n}\n" for n in range(1, 11))
THIRTY = "".join(f"line {n}\n" for n in range(1, 31))

# name: old text, new text, the changed places (counted from 0, end not included).
# git shows every one of these changes at exactly these places (checked by the tests at the end of this file).
# That is not so for every text: see the comment at gitrepo._matcher for the kind that can come out one line off.
CASES = {
    "one line replaced": (TEN, TEN.replace("line 5\n", "line five\n"), [Spot(4, 5, 4, 5)]),
    "first line replaced": (TEN, TEN.replace("line 1\n", "LINE 1\n"), [Spot(0, 1, 0, 1)]),
    "last line replaced": (TEN, TEN.replace("line 10\n", "line ten\n"), [Spot(9, 10, 9, 10)]),
    "two lines removed": (TEN, TEN.replace("line 4\nline 5\n", ""), [Spot(3, 5, 3, 3)]),
    "lines added at the end": (TEN, TEN + "line 11\nline 12\n", [Spot(10, 10, 10, 12)]),
    "a line added at the top": (TEN, "line 0\n" + TEN, [Spot(0, 0, 0, 1)]),
    "two changes far apart": (THIRTY, THIRTY.replace("line 3\n", "line three\n").replace("line 25\n", ""),
                              [Spot(2, 3, 2, 3), Spot(24, 25, 24, 24)]),
    "two changes close together": (THIRTY, THIRTY.replace("line 10\n", "line ten\n").replace("line 14\n", "line 14\nline 14 b\n"),
                                   [Spot(9, 10, 9, 10), Spot(14, 14, 14, 15)]),
    "an empty file gets its first lines": ("", "a\nb\n", [Spot(0, 0, 0, 2)]),
    "every line removed": ("a\nb\n", "", [Spot(0, 2, 0, 0)]),
    "the last line break added": ("a\nb", "a\nb\n", [Spot(1, 2, 1, 2)]),
    "the last line break removed": ("a\nb\n", "a\nb", [Spot(1, 2, 1, 2)]),
    "no last line break, last line changed": ("x\ny", "x\nz", [Spot(1, 2, 1, 2)]),
    "no last line break, first line changed": ("x\ny\nz", "X\ny\nz", [Spot(0, 1, 0, 1)]),
    # git ends a line at a line feed only; Python's splitlines would cut this text into five lines, not three
    "a form feed and carriage returns inside lines": ("a\r\nb\x0cc\rd\r\ne\n", "a\r\nb\x0cc\rd\r\nE\n", [Spot(2, 3, 2, 3)]),
    "letters outside ASCII": ("café\nnaïve\n", "café\nnaive\n", [Spot(1, 2, 1, 2)]),
    # the new block ends with a line that also stands just above it (a second `return None` after the first):
    # it belongs after the old `return None`, not one line earlier with the old line shown as new
    "a block added after a line it also ends with": (program(), program(["    if value < 0:", "        return None"]),
                                                     [Spot(185, 185, 185, 187)]),
}


@pytest.mark.parametrize("name", CASES)
def test_changed_places_and_counts(name):
    old, new, spots = CASES[name]
    assert gitrepo.changed_spots(old, new) == spots
    assert gitrepo.count_changes(old, new) == (sum(s.new_end - s.new_start for s in spots), sum(s.old_end - s.old_start for s in spots))
    assert gitrepo.changed_spots(old, old) == [] and gitrepo.count_changes(new, new) == (0, 0)


def test_a_changed_place_says_how_many_lines_it_adds_and_removes():
    assert (Spot(3, 5, 3, 3).added, Spot(3, 5, 3, 3).removed) == (0, 2)
    assert (Spot(185, 185, 185, 187).added, Spot(185, 185, 185, 187).removed) == (2, 0)
    assert gitrepo.count_changes(*CASES["two changes close together"][:2]) == (2, 1)


def diff_of(old, new, **options):
    text = gitrepo.unified_diff(old.encode(), new.encode(), "f.txt", **options)
    head = (f"diff --git a/f.txt b/f.txt\nindex {gitrepo.blob_id(old.encode())[:7]}..{gitrepo.blob_id(new.encode())[:7]} 100644\n"
            "--- a/f.txt\n+++ b/f.txt\n")
    assert text.startswith(head)
    return text[len(head):]


def test_unified_diff_is_written_the_way_git_writes_it():
    old, new, _ = CASES["a block added after a line it also ends with"]
    assert diff_of(old, new) == (
        "@@ -183,6 +183,8 @@\n"
        "         value = parse(text)\n"
        "     except ValueError:\n"
        "         return None\n"
        "+    if value < 0:\n"
        "+        return None\n"
        "     value = step_0(value)\n"
        "     value = step_1(value)\n"
        "     value = step_2(value)\n")
    assert diff_of(TEN, TEN.replace("line 5\n", "line five\n")) == (
        "@@ -2,7 +2,7 @@\n line 2\n line 3\n line 4\n-line 5\n+line five\n line 6\n line 7\n line 8\n")
    assert diff_of(TEN, TEN.replace("line 5\n", "line five\n"), context=1) == "@@ -4,3 +4,3 @@\n line 4\n-line 5\n+line five\n line 6\n"
    assert diff_of(*CASES["two changes far apart"][:2]) == (
        "@@ -1,6 +1,6 @@\n line 1\n line 2\n-line 3\n+line three\n line 4\n line 5\n line 6\n"
        "@@ -22,7 +22,6 @@\n line 22\n line 23\n line 24\n-line 25\n line 26\n line 27\n line 28\n")
    assert diff_of("a\n", "b\n") == "@@ -1 +1 @@\n-a\n+b\n"
    assert diff_of("", "a\nb\n") == "@@ -0,0 +1,2 @@\n+a\n+b\n"
    assert diff_of("a\nb\n", "") == "@@ -1,2 +0,0 @@\n-a\n-b\n"
    assert diff_of("x\ny", "x\nz") == "@@ -1,2 +1,2 @@\n x\n-y\n\\ No newline at end of file\n+z\n\\ No newline at end of file\n"
    assert diff_of("a\nb", "a\nb\n") == "@@ -1,2 +1,2 @@\n a\n-b\n\\ No newline at end of file\n+b\n"
    assert diff_of("x\ny\nz", "X\ny\nz") == "@@ -1,3 +1,3 @@\n-x\n+X\n y\n z\n\\ No newline at end of file\n"
    assert gitrepo.unified_diff(b"same\n", b"same\n", "f.txt") == ""
    with pytest.raises(GitRepoError, match="text files"):
        gitrepo.unified_diff(b"\xff\xfe\x00", b"text\n", "f.bin")


def test_patch_file_layout(repo):
    old = {"a.txt": TEN.encode(), "b.txt": b"same\n", "c.txt": b"x\ny"}
    new = {"a.txt": TEN.replace("line 5\n", "line five\n").encode(), "b.txt": b"same\n", "c.txt": b"x\nz\nmore\n"}
    base = repo.commit("main", old, "Base", WHO, 1700000000, None)
    tip = repo.branch_from("fix/x", base, new, "Change two files\n\nWhy: a test.\nSecond line.", OTHER, 1700000600)
    patch = gitrepo.format_patch(repo.read_commit(tip), repo.files(base), repo.files(tip), "Isogeny Evidence Lab (demo)\n")
    assert patch == (
        f"From {tip} Mon Sep 17 00:00:00 2001\n"
        "From: Other One <other@example.invalid>\n"
        "Date: Tue, 14 Nov 2023 22:23:20 +0000\n"
        "Subject: [PATCH] Change two files\n"
        "\n"
        "Why: a test.\nSecond line.\n"
        "---\n"
        " a.txt | 2 +-\n"
        " c.txt | 3 ++-\n"
        " 2 files changed, 3 insertions(+), 2 deletions(-)\n"
        "\n"
        + gitrepo.unified_diff(old["a.txt"], new["a.txt"], "a.txt") + gitrepo.unified_diff(old["c.txt"], new["c.txt"], "c.txt")
        + "-- \nIsogeny Evidence Lab (demo)\n\n")
    one_line = repo.branch_from("fix/y", base, {**old, "b.txt": b"same\nand more\n"}, "Add a line", WHO, 1700000600)
    patch = gitrepo.format_patch(repo.read_commit(one_line), repo.files(base), repo.files(one_line), "footer")
    assert "Subject: [PATCH] Add a line\n\n---\n b.txt | 1 +\n 1 file changed, 1 insertion(+)\n\ndiff --git a/b.txt b/b.txt\n" in patch
    # a change that adds or removes a file is not something this app writes patches for
    for files in ({**old, "d.txt": b"new file\n"}, {"a.txt": old["a.txt"]}):
        with pytest.raises(GitRepoError, match="files that already exist"):
            gitrepo.format_patch(repo.read_commit(tip), old, files, "footer")
    with pytest.raises(GitRepoError, match="text files"):
        gitrepo.format_patch(repo.read_commit(tip), {"a.bin": b"\xff\xfe"}, {"a.bin": b"\xff\xfd"}, "footer")


def test_nothing_is_run_and_the_git_program_is_never_called():
    source = Path(gitrepo.__file__).read_text()
    for banned in ("subprocess", "os.system", "popen", "eval(", "exec(", "importlib", "pickle", "shutil"):
        assert banned not in source


# ------------------------------------------------------------------ the same, checked by git itself (skipped without git)

def strip_hint(diff_text):
    """git adds a hint after the second @@ (the nearest line above that starts at the margin). We leave it out."""
    return re.sub(r"^(@@ [^@]* @@).*$", r"\1", diff_text, flags=re.M)


def fsck(git, path):
    done = git("--git-dir", path, "fsck", "--strict", "--full")
    return (done.stdout + done.stderr).decode()


def test_git_makes_the_same_objects_from_the_same_values(repo, git):
    assert git("hash-object", "--stdin", data=b"hello\n").stdout.decode().strip() == HELLO == gitrepo.blob_id(b"hello\n")
    one, two = repo.write_blob(b"one\n"), repo.write_blob(b"two\n")
    tree = repo.write_tree({"b.txt": two, "a.txt": one})
    listed = f"100644 blob {two}\tb.txt\n100644 blob {one}\ta.txt\n".encode()
    assert git("--git-dir", repo.path, "mktree", data=listed).stdout.decode().strip() == tree == TREE
    first = repo.write_commit(tree, (), WHO, 1700000000, "First commit\n\nWith a body.")
    second = repo.write_commit(tree, [first], WHO, 1700000600, "Second", committer=OTHER)

    def people(author, committer, when):
        return {"GIT_AUTHOR_NAME": author.name, "GIT_AUTHOR_EMAIL": author.email, "GIT_AUTHOR_DATE": f"{when} +0000",
                "GIT_COMMITTER_NAME": committer.name, "GIT_COMMITTER_EMAIL": committer.email, "GIT_COMMITTER_DATE": f"{when} +0000"}
    theirs = git("--git-dir", repo.path, "commit-tree", tree, "-m", "First commit", "-m", "With a body.",
                 env_extra=people(WHO, WHO, 1700000000)).stdout.decode().strip()
    assert theirs == first == FIRST
    theirs = git("--git-dir", repo.path, "commit-tree", tree, "-p", first, "-m", "Second",
                 env_extra=people(WHO, OTHER, 1700000600)).stdout.decode().strip()
    assert theirs == second == SECOND


def test_git_reads_what_we_write_and_finds_nothing_wrong(repo, git, tmp_path):
    base = repo.commit("main", {"a.txt": b"old\n", "b.txt": b"same\n"}, "Base\n\nWith a body.", WHO, 1700000000, None)
    tip = repo.branch_from("fix/a", base, {"a.txt": b"new\n", "b.txt": b"same\n"}, "Change a", OTHER, 1700000600)
    assert fsck(git, repo.path) == ""
    merged = repo.merge("main", "fix/a", "Merge pull request #1: Change a", WHO, 1700001200)
    assert fsck(git, repo.path) == ""

    def ask(*args):
        return git("--git-dir", repo.path, *args).stdout.decode()
    assert ask("rev-parse", "main", "fix/a", "HEAD").split() == [merged, tip, merged]
    assert ask("log", "--format=%H %P|%an <%ae>|%at|%s", "main").splitlines() == [
        f"{merged} {base} {tip}|Test Person <test@example.invalid>|1700001200|Merge pull request #1: Change a",
        f"{tip} {base}|Other One <other@example.invalid>|1700000600|Change a",
        f"{base} |Test Person <test@example.invalid>|1700000000|Base"]
    assert ask("log", "-1", "--format=%b", base).strip() == "With a body."
    new_id, same_id = gitrepo.blob_id(b"new\n"), gitrepo.blob_id(b"same\n")
    assert ask("ls-tree", "main").splitlines() == [f"100644 blob {new_id}\ta.txt", f"100644 blob {same_id}\tb.txt"]
    assert git("--git-dir", repo.path, "show", "main:a.txt").stdout == b"new\n"
    git("clone", "-q", repo.path, tmp_path / "checkout")           # a plain copy of the files, made by git
    assert {p.name: p.read_bytes() for p in (tmp_path / "checkout").iterdir() if p.is_file()} == repo.files(merged)

    # and the other way round: what git wrote into the same repository, this app reads
    theirs = git("--git-dir", repo.path, "commit-tree", repo.read_commit(merged).tree, "-p", merged, "-m", "Made by git",
                 env_extra={"GIT_AUTHOR_NAME": "Zoë", "GIT_AUTHOR_EMAIL": "zoe@example.invalid",
                            "GIT_AUTHOR_DATE": "1700002000 +0100"}).stdout.decode().strip()
    commit = repo.read_commit(theirs)
    assert (commit.parents, commit.author, commit.author_time, commit.title) == (
        (merged,), Person("Zoë", "zoe@example.invalid"), 1700002000, "Made by git")
    assert commit.committer == Person("Somebody Else", "else@example.invalid")
    repo.set_branch("main", theirs, merged)
    assert ask("rev-parse", "main").strip() == theirs and fsck(git, repo.path) == ""


@pytest.mark.parametrize("name", CASES)
def test_git_shows_counts_and_applies_each_change_as_we_do(name, repo, git, tmp_path):
    old, new, _ = (part.encode() if isinstance(part, str) else part for part in CASES[name])
    base = repo.commit("main", {"f.txt": old}, "Base", WHO, 1700000000, None)
    tip = repo.branch_from("change", base, {"f.txt": new}, "Change the file\n\nWhy: a test.", OTHER, 1700000600)

    # our diff is git's diff, and our counts are git's counts
    theirs = git("--git-dir", repo.path, "diff", "main", "change").stdout.decode()
    assert gitrepo.unified_diff(old, new, "f.txt") == strip_hint(theirs)
    added, removed = gitrepo.count_changes(old.decode(), new.decode())
    assert git("--git-dir", repo.path, "diff", "--numstat", "main", "change").stdout.decode() == f"{added}\t{removed}\tf.txt\n"

    # git accepts our patch file and, applying it, gets the new file byte for byte
    patch = tmp_path / "change.patch"
    patch.write_bytes(gitrepo.format_patch(repo.read_commit(tip), repo.files(base), repo.files(tip), "Evidence Lab test").encode())
    checkout = tmp_path / "checkout"
    git("clone", "-q", repo.path, checkout)
    assert (checkout / "f.txt").read_bytes() == old
    git("apply", "--check", patch, cwd=checkout)
    git("am", "-q", "--keep-cr", patch, cwd=checkout)   # without --keep-cr git am drops carriage returns, from its own patches too
    assert (checkout / "f.txt").read_bytes() == new
    made = git("log", "-1", "--format=%T|%P|%an <%ae>|%at|%s|%b", cwd=checkout).stdout.decode().strip()
    assert made == f"{repo.read_commit(tip).tree}|{base}|Other One <other@example.invalid>|1700000600|Change the file|Why: a test."
    assert git("status", "--porcelain", cwd=checkout).stdout == b""


def test_git_applies_a_patch_that_changes_two_files(repo, git, tmp_path):
    old = {"a.txt": TEN.encode(), "b.txt": b"same\n", "c.txt": b"x\ny"}
    new = {"a.txt": TEN.replace("line 5\n", "line five\n").encode(), "b.txt": b"same\n", "c.txt": b"x\nz\nmore\n"}
    base = repo.commit("main", old, "Base", WHO, 1700000000, None)
    tip = repo.branch_from("fix/x", base, new, "Change two files\n\nWhy: a test.\nSecond line.", OTHER, 1700000600)
    patch = tmp_path / "two.patch"
    patch.write_bytes(gitrepo.format_patch(repo.read_commit(tip), old, new, "Evidence Lab test").encode())
    checkout = tmp_path / "checkout"
    git("clone", "-q", repo.path, checkout)
    assert git("apply", "--numstat", patch, cwd=checkout).stdout.decode() == "1\t1\ta.txt\n2\t1\tc.txt\n"
    git("apply", "--check", patch, cwd=checkout)
    git("am", "-q", patch, cwd=checkout)
    assert {p.name: p.read_bytes() for p in checkout.iterdir() if p.is_file()} == new
    assert git("log", "-1", "--format=%T|%s|%b", cwd=checkout).stdout.decode().strip() == (
        f"{repo.read_commit(tip).tree}|Change two files|Why: a test.\nSecond line.")
