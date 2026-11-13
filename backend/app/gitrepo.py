"""A small reader and writer for repositories in git's own on-disk format.

Why this exists: the connected demo code is kept as a real git repository, the demo machine must not need git
installed, and no dependency may be added (SPEC 7b). So the few things the app needs are done here with the
standard library only: read and write blobs, trees and commits, move branches, merge a branch that is strictly
ahead, list what changed between two texts, and write a patch that git itself can apply.

It knows nothing about any particular program, version or fix. Everything in a repository is data: nothing
read from it is ever executed, and every name, id and size is checked before it is used.

Limits, on purpose: loose objects only (no pack files), flat repositories (files at the top level, no folders),
UTF-8 text files, UTC times. Changes are lined up with Python's difflib, which is not git's own method (see
`_matcher`).
"""
from __future__ import annotations

import difflib
import hashlib
import os
import re
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MAX_OBJECT_BYTES = 2_000_000   # nothing in a demo repository comes near this; bigger objects are refused
MAX_FILES = 200
MAX_HISTORY = 500

# Always used with fullmatch: "$" would also accept a name or an id that ends with a line break.
_SHA = re.compile(r"[0-9a-f]{40}")
_BRANCH_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+)*")
_FILE_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*")
_PERSON = re.compile(r"(?P<name>[^<>\n]*) <(?P<email>[^<>\n ]*)> (?P<time>\d{1,12}) (?P<zone>[+-]\d{4})")
_FILE_MODES = (b"100644", b"100755")


class GitRepoError(Exception):
    """The repository could not be read or changed. The message is plain and safe to show."""


@dataclass(frozen=True)
class Person:
    name: str
    email: str


@dataclass(frozen=True)
class Commit:
    sha: str
    tree: str
    parents: tuple[str, ...]
    author: Person
    author_time: int
    committer: Person
    commit_time: int
    message: str

    @property
    def title(self) -> str:
        return self.message.split("\n", 1)[0]


def _check_sha(sha: str) -> str:
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise GitRepoError("That is not a valid commit or object id.")
    return sha


def check_branch_name(name: str) -> str:
    """Branch names the app accepts: letters, digits, dot, dash, underscore, with / between parts."""
    parts = name.split("/") if isinstance(name, str) else []
    if not parts or len(name) > 100 or any(not _BRANCH_PART.fullmatch(p) or p.endswith(".lock") for p in parts):
        raise GitRepoError("That is not a branch name this app accepts.")
    return name


def check_file_name(name: str) -> str:
    if not isinstance(name, str) or len(name) > 100 or not _FILE_NAME.fullmatch(name) or name.endswith(".lock"):
        raise GitRepoError("That is not a file name this app accepts.")
    return name


def _ref_text(path: Path) -> str:
    # bytes that are not text become a mark that no id or name contains, so a damaged file is refused by the
    # checks that follow instead of stopping the app with a decoding error
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _person_text(value: str) -> str:
    return re.sub(r"[<>\n\r\0]", "", value).strip() or "unknown"


def object_id(kind: str, body: bytes) -> str:
    """The id git gives an object: SHA-1 over a short header and the content."""
    return hashlib.sha1(kind.encode() + b" " + str(len(body)).encode() + b"\0" + body).hexdigest()


def blob_id(data: bytes) -> str:
    return object_id("blob", data)


class GitRepo:
    """One bare repository in a folder: HEAD, objects/ and refs/heads/."""

    def __init__(self, path: Path):
        self.path = Path(path)
        if not (self.path / "HEAD").is_file() or not (self.path / "objects").is_dir():
            raise GitRepoError("No repository was found in that folder.")

    # ------------------------------------------------------------------ making one

    @classmethod
    def create(cls, path: Path, branch: str = "main") -> "GitRepo":
        """A new, empty bare repository whose first branch will be `branch`."""
        path = Path(path)
        check_branch_name(branch)
        if path.exists() and any(path.iterdir()):
            raise GitRepoError("That folder is not empty.")
        (path / "objects").mkdir(parents=True, exist_ok=True)
        (path / "refs" / "heads").mkdir(parents=True, exist_ok=True)
        (path / "HEAD").write_text(f"ref: refs/heads/{branch}\n")
        return cls(path)

    # ------------------------------------------------------------------ objects

    def _object_path(self, sha: str) -> Path:
        return self.path / "objects" / sha[:2] / sha[2:]

    def _write(self, kind: str, body: bytes) -> str:
        if len(body) > MAX_OBJECT_BYTES:
            raise GitRepoError("That is too large to store.")
        sha = object_id(kind, body)
        target = self._object_path(sha)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + f".tmp{os.getpid()}")
            temp.write_bytes(zlib.compress(kind.encode() + b" " + str(len(body)).encode() + b"\0" + body))
            os.replace(temp, target)
        return sha

    def _read(self, sha: str, kind: str) -> bytes:
        target = self._object_path(_check_sha(sha))
        if target.is_symlink() or not target.is_file():
            raise GitRepoError("The repository is missing a piece it refers to.")
        unpack = zlib.decompressobj()
        try:
            raw = unpack.decompress(target.read_bytes(), MAX_OBJECT_BYTES + 64)
        except zlib.error:
            raise GitRepoError("The repository holds a damaged object.") from None
        if unpack.unconsumed_tail:                  # there is more than the size this app reads
            raise GitRepoError("The repository holds an object that is too large to read.")
        if not unpack.eof or unpack.unused_data:    # the file was cut short, or something was added after it
            raise GitRepoError("The repository holds a damaged object.")
        head, sep, body = raw.partition(b"\0")
        if not sep or head != kind.encode() + b" " + str(len(body)).encode():
            raise GitRepoError("The repository holds an object of an unexpected kind or size.")
        if object_id(kind, body) != sha:
            raise GitRepoError("The repository holds an object that does not match its id.")
        return body

    def write_blob(self, data: bytes) -> str:
        return self._write("blob", data)

    def read_blob(self, sha: str) -> bytes:
        return self._read(sha, "blob")

    def write_tree(self, files: dict[str, str]) -> str:
        """A flat tree: file name -> blob id. Entries are stored sorted by name, as git requires."""
        if len(files) > MAX_FILES:
            raise GitRepoError("That is more files than this app handles.")
        names = sorted((check_file_name(name) for name in files), key=str.encode)  # checked before they are sorted
        body = b"".join(b"100644 " + name.encode() + b"\0" + bytes.fromhex(_check_sha(files[name])) for name in names)
        return self._write("tree", body)

    def read_tree(self, sha: str) -> dict[str, str]:
        body, files, at = self._read(sha, "tree"), {}, 0
        while at < len(body):
            space, nul = body.find(b" ", at), body.find(b"\0", at)
            if space < 0 or nul < space or nul + 21 > len(body):
                raise GitRepoError("The repository holds a damaged folder listing.")
            mode, name = body[at:space], body[space + 1:nul].decode("utf-8", "replace")
            if mode not in _FILE_MODES:
                raise GitRepoError("This app only handles repositories whose files are all at the top level.")
            files[check_file_name(name)] = body[nul + 1:nul + 21].hex()
            at = nul + 21
        if len(files) > MAX_FILES:
            raise GitRepoError("That is more files than this app handles.")
        return files

    def write_commit(self, tree: str, parents: tuple[str, ...] | list[str], author: Person, when: int, message: str,
                     committer: Person | None = None) -> str:
        who = committer or author
        lines = [f"tree {_check_sha(tree)}"] + [f"parent {_check_sha(p)}" for p in parents]
        lines.append(f"author {_person_text(author.name)} <{_person_text(author.email)}> {int(when)} +0000")
        lines.append(f"committer {_person_text(who.name)} <{_person_text(who.email)}> {int(when)} +0000")
        text = "\n".join(lines) + "\n\n" + message.replace("\r", "").strip("\n") + "\n"
        return self._write("commit", text.encode())

    def read_commit(self, sha: str) -> Commit:
        text = self._read(sha, "commit").decode("utf-8", "replace")
        head, _, message = text.partition("\n\n")
        tree, parents, people = None, [], {}
        for line in head.split("\n"):
            key, _, value = line.partition(" ")
            if key == "tree":
                tree = value
            elif key == "parent":
                parents.append(value)
            elif key in ("author", "committer"):
                match = _PERSON.fullmatch(value)
                if not match:
                    raise GitRepoError("The repository holds a commit this app cannot read.")
                people[key] = (Person(match["name"], match["email"]), int(match["time"]))
        if tree is None or "author" not in people or "committer" not in people:
            raise GitRepoError("The repository holds a commit this app cannot read.")
        return Commit(sha, _check_sha(tree), tuple(_check_sha(p) for p in parents), people["author"][0],
                      people["author"][1], people["committer"][0], people["committer"][1], message.rstrip("\n"))

    # ------------------------------------------------------------------ branches

    def head_branch(self) -> str:
        text = _ref_text(self.path / "HEAD")
        if not text.startswith("ref: refs/heads/"):
            raise GitRepoError("The repository's HEAD does not name a branch.")
        return check_branch_name(text[len("ref: refs/heads/"):])

    def _branch_path(self, name: str) -> Path:
        return self.path / "refs" / "heads" / Path(*check_branch_name(name).split("/"))

    def branch(self, name: str) -> str | None:
        """The commit a branch points at, or None when there is no such branch."""
        target = self._branch_path(name)
        if target.is_symlink() or not target.is_file():
            return None
        return _check_sha(_ref_text(target))

    def branches(self) -> dict[str, str]:
        root, found = self.path / "refs" / "heads", {}
        for target in sorted(root.rglob("*")) if root.is_dir() else []:
            if target.is_file() and not target.is_symlink():
                name = target.relative_to(root).as_posix()
                found[check_branch_name(name)] = _check_sha(_ref_text(target))
        return found

    def set_branch(self, name: str, sha: str, expect: str | None) -> None:
        """Point a branch at a commit, but only if it still points where the caller last saw it
        (`expect`; None means the branch must not exist yet). Stops two changes overwriting each other."""
        self.read_commit(sha)
        if self.branch(name) != expect:
            raise GitRepoError("The branch changed in the meantime. Nothing was moved.")
        # each branch is kept as a file, so `a` and `a/b` cannot both exist: one would need a folder where
        # the other is a file
        target, heads = self._branch_path(name), self.path / "refs" / "heads"
        if target.is_dir() or any(above.is_file() for above in target.parents if heads in above.parents):
            raise GitRepoError("That branch name clashes with a branch that already exists. Nothing was moved.")
        target.parent.mkdir(parents=True, exist_ok=True)
        # written beside HEAD and then swapped in, so a half-written file is never read or listed as a branch
        temp = self.path / f"branch.tmp{os.getpid()}"
        temp.write_text(sha + "\n")
        os.replace(temp, target)

    # ------------------------------------------------------------------ files, commits, history, merge

    def files(self, commit_sha: str) -> dict[str, bytes]:
        """Every file of a commit: name -> content."""
        tree = self.read_tree(self.read_commit(commit_sha).tree)
        return {name: self.read_blob(blob) for name, blob in tree.items()}

    def file_ids(self, commit_sha: str) -> dict[str, str]:
        return self.read_tree(self.read_commit(commit_sha).tree)

    def commit(self, branch: str, files: dict[str, bytes], message: str, author: Person, when: int,
               expect: str | None) -> str:
        """Save `files` as the whole content of a new commit on `branch`. `expect` is the commit the branch
        points at now (None for a branch that does not exist yet and has no parent)."""
        tree = self.write_tree({name: self.write_blob(data) for name, data in files.items()})
        sha = self.write_commit(tree, (expect,) if expect else (), author, when, message)
        self.set_branch(branch, sha, expect)
        return sha

    def branch_from(self, name: str, start: str, files: dict[str, bytes], message: str, author: Person, when: int) -> str:
        """A new branch `name` with one new commit on top of commit `start`."""
        if self.branch(name) is not None:
            raise GitRepoError("A branch with that name already exists.")
        self.read_commit(start)  # must be a commit of this repository, or the new commit would point at nothing
        tree = self.write_tree({n: self.write_blob(d) for n, d in files.items()})
        sha = self.write_commit(tree, (start,), author, when, message)
        self.set_branch(name, sha, None)
        return sha

    def history(self, sha: str, limit: int = 50) -> list[Commit]:
        """The commit and its first parents, newest first."""
        out: list[Commit] = []
        while sha and len(out) < min(limit, MAX_HISTORY):
            commit = self.read_commit(sha)
            out.append(commit)
            sha = commit.parents[0] if commit.parents else ""
        return out

    def is_ancestor(self, old: str, new: str) -> bool:
        """True when commit `old` is `new` itself or somewhere in its past."""
        seen, todo = set(), [_check_sha(new)]
        while todo and len(seen) <= MAX_HISTORY:
            sha = todo.pop()
            if sha == old:
                return True
            if sha not in seen:
                seen.add(sha)
                todo.extend(self.read_commit(sha).parents)
        return False

    def merge(self, into: str, source: str, message: str, author: Person, when: int) -> str:
        """Merge branch `source` into branch `into` with a merge commit (two parents).
        Only when nothing else has changed `into` since `source` was started, so there is never a conflict
        to resolve: otherwise nothing is merged."""
        base, tip = self.branch(into), self.branch(source)
        if base is None or tip is None:
            raise GitRepoError("One of the two branches does not exist.")
        if base == tip:
            raise GitRepoError("That branch holds nothing new. Nothing was merged.")
        if not self.is_ancestor(base, tip):
            raise GitRepoError("The branch to merge into has changed since this change was made. Nothing was merged.")
        sha = self.write_commit(self.read_commit(tip).tree, (base, tip), author, when, message)
        self.set_branch(into, sha, base)
        return sha


# ---------------------------------------------------------------------- what changed between two texts

@dataclass(frozen=True)
class Spot:
    """One changed place: lines old_start..old_end (not included) of the old text became
    lines new_start..new_end of the new text. Counted from 0."""
    old_start: int
    old_end: int
    new_start: int
    new_end: int

    @property
    def removed(self) -> int:
        return self.old_end - self.old_start

    @property
    def added(self) -> int:
        return self.new_end - self.new_start


def _lines(text: str) -> list[str]:
    """The lines of a text as git counts them, each with its line break: only a line feed ends a line.
    (str.splitlines also splits at form feeds and a few other marks, which shifts every later line number
    and gives a patch git cannot apply. Keeping the line break means a changed last line break counts too.)"""
    parts = text.split("\n")
    return [part + "\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _matcher(old: list[str], new: list[str]) -> difflib.SequenceMatcher:
    # autojunk=False matters. With the default, in a file of 200 lines or more, lines that appear very often
    # (blank lines) are skipped when the two texts are lined up. The long unchanged part above a change is then
    # cut into pieces, and a block added right after a line it also ends with (a second `return ...` after the
    # first) is shown one line too early, with the old line marked as new. With it off, the texts are lined up
    # around their longest unchanged part and the demo change comes out exactly as git shows it (tested).
    # This is not git's own method: a change that can be shown in more than one way may still be placed
    # differently from git for other texts. The patch applies either way.
    return difflib.SequenceMatcher(None, old, new, autojunk=False)


def changed_spots(old: str, new: str) -> list[Spot]:
    a, b = _lines(old), _lines(new)
    return [Spot(i1, i2, j1, j2) for tag, i1, i2, j1, j2 in _matcher(a, b).get_opcodes() if tag != "equal"]


def count_changes(old: str, new: str) -> tuple[int, int]:
    """(lines added, lines removed)."""
    spots = changed_spots(old, new)
    return sum(s.added for s in spots), sum(s.removed for s in spots)


def _range(start: int, stop: int) -> str:
    length = stop - start
    if length == 1:
        return str(start + 1)
    return f"{start + 1 if length else start},{length}"


def unified_diff(old: bytes, new: bytes, name: str, context: int = 3) -> str:
    """The change to one file, written the way `git diff` writes it, so that git can apply it."""
    check_file_name(name)
    try:
        a, b = _lines(old.decode("utf-8")), _lines(new.decode("utf-8"))
    except UnicodeDecodeError:
        raise GitRepoError("This app only shows changes to text files.") from None
    out = [f"diff --git a/{name} b/{name}\n", f"index {blob_id(old)[:7]}..{blob_id(new)[:7]} 100644\n",
           f"--- a/{name}\n", f"+++ b/{name}\n"]
    for group in _matcher(a, b).get_grouped_opcodes(context):
        out.append(f"@@ -{_range(group[0][1], group[-1][2])} +{_range(group[0][3], group[-1][4])} @@\n")
        for tag, i1, i2, j1, j2 in group:
            for sign, lines in ((" ", a[i1:i2] if tag == "equal" else []), ("-", a[i1:i2] if tag in ("replace", "delete") else []),
                                ("+", b[j1:j2] if tag in ("replace", "insert") else [])):
                for line in lines:
                    out.append(sign + line if line.endswith("\n") else sign + line + "\n\\ No newline at end of file\n")
    return "".join(out) if len(out) > 4 else ""


def _stat_line(name: str, added: int, removed: int) -> str:
    return f" {name} | {added + removed} {'+' * added}{'-' * removed}\n"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def format_patch(commit: Commit, old_files: dict[str, bytes], new_files: dict[str, bytes], footer: str) -> str:
    """One commit as a patch file in the layout `git format-patch` uses; `git am` and `git apply` accept it."""
    changed = [n for n in sorted(set(old_files) | set(new_files)) if old_files.get(n) != new_files.get(n)]
    if any(n not in old_files or n not in new_files for n in changed):
        raise GitRepoError("This app only writes patches for changes to files that already exist.")
    diffs, stats, added_all, removed_all = [], [], 0, 0
    for name in changed:
        added, removed = count_changes(old_files[name].decode("utf-8", "replace"), new_files[name].decode("utf-8", "replace"))
        stats.append(_stat_line(name, added, removed))
        added_all, removed_all = added_all + added, removed_all + removed
        diffs.append(unified_diff(old_files[name], new_files[name], name))
    when = datetime.fromtimestamp(commit.author_time, tz=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    title, _, body = commit.message.partition("\n")
    summary = f" {_plural(len(changed), 'file')} changed"
    if added_all:
        summary += f", {_plural(added_all, 'insertion')}(+)"
    if removed_all:
        summary += f", {_plural(removed_all, 'deletion')}(-)"
    return "".join([
        f"From {commit.sha} Mon Sep 17 00:00:00 2001\n",
        f"From: {commit.author.name} <{commit.author.email}>\n",
        f"Date: {when}\n",
        f"Subject: [PATCH] {title}\n\n",
        (body.strip("\n") + "\n") if body.strip() else "",
        "---\n", *stats, summary + "\n\n", *diffs, "-- \n", footer.strip() + "\n\n",
    ])
