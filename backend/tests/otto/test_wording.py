"""The 5c fixes: no sentence says what Otto did (19 November 2026).

A sentence says what is proposed or written, in short sentences ("A change was written for CVE-2022-21449", "Why it
is proposed"), never who did it ("Otto wrote", "Otto proposes", "in Otto's words"). The tag "From Otto" stays on every
proposal, and Claude's own writing is labelled once.

This test reads the code, not one walk of the app, so it holds for every state a screen can be in:
  - every piece of text the backend can put into an answer (the string constants of `backend/app` and of the verify
    command, `backend/evidence`; a docstring is a note for developers and is not read),
  - the reasons the pack builder writes into a test pack (`backend/ottolab/build.py`): Advisories shows them as they
    are, for every pack built from now on (the two shipped packs are never rebuilt, and hold none of these), and
  - every piece of text the screens hold themselves (`frontend/src` outside its comments and its tests).
"""

import ast
import functools
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# The phrases Kevin listed, and the same verbs in another tense.
BANNED = (
    "Otto wrote",
    "Otto writes",
    "Otto proposes",
    "Otto proposed",
    "in Otto's words",
    "In Otto's words",
    "Why Otto proposes it",
    "Otto found",
    "Otto finds",
    "Otto has",
    "Otto's proposal",
    "Otto asked",
    "Otto asks",
    "Otto no longer",
    # Not on the list, but the same thing: sentences that named Otto as the one acting. They were found by the
    # separate reviewer of the 5c fixes and reworded too ("Only the answers recorded during the build are used.").
    "Otto works",
    "Otto needs",
    "Otto adds",
    "Otto goes on",
    "Otto could not",
    "Otto's own change",
    "made by Otto",
    "Otto uses",
    "Otto designs",
    "Otto reads",
    "Otto tries",
    "Otto looks",
    "Otto decides",
    "Otto runs",
    "Otto installs",
    "Otto sends",
)
# The one sentence with such a phrase that stays, word for word.
KEPT = ("Otto has no say in any result.",)
# What stays as it is, and must not have been swept away with the rest.
STILL_THERE = (
    "From Otto",
    "Written by Otto",
    "Not written yet",
    "Live Otto",
    "Otto in this project",
    "Otto ledger entries",
    "No recorded answer: this needs Live Otto.",
    "Otto is not installed on this computer",
    # ("Otto has no say in any result." is put together when the sentence is worded: tests/otto/test_otto_fix.py reads it whole)
    " has no say in any result.",
)
# A record, not a sentence on a screen: what the assessment's Otto ledger keeps about a proposal's decisions. It is
# written into the ledger with the first decision and is never shown by the app (the screens word a ledger entry
# themselves). It stays as it was, so a ledger written today reads like one written by the 5c build.
RECORDS = {("backend/app/otto/assurance.py", "Every decision a person records on Otto's proposal “")}


def _backend_texts(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    notes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                notes.add(id(body[0].value))
    found: list[tuple[int, str]] = []

    class Reader(ast.NodeVisitor):
        def visit_JoinedStr(self, node):  # an f-string: its fixed pieces, with a gap where a value goes
            found.append(
                (
                    node.lineno,
                    "".join(
                        v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "{…}"
                        for v in node.values
                    ),
                )
            )

        def visit_Constant(self, node):
            if isinstance(node.value, str) and id(node) not in notes:
                found.append((node.lineno, node.value))

    Reader().visit(tree)
    return found


def _screen_texts(path: Path) -> list[tuple[int, str]]:
    source = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), path.read_text(encoding="utf-8"), flags=re.S)
    return [(n, re.sub(r"(?<![:\"'`])//.*$", "", line)) for n, line in enumerate(source.splitlines(), 1)]


@functools.lru_cache(maxsize=1)
def _everything() -> tuple[tuple[str, int, str], ...]:
    return tuple(_read_everything())


def _read_everything() -> list[tuple[str, int, str]]:
    out = []
    for folder in ("backend/app", "backend/evidence"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            out += [(str(path.relative_to(ROOT)), line, text) for line, text in _backend_texts(path)]
    # (of the research side only the pack builder: its other scripts are pinned by their fingerprints in the research
    # ledger, and what they hold is a prompt or a record, not a sentence on a screen)
    out += [
        ("backend/ottolab/build.py", line, text) for line, text in _backend_texts(ROOT / "backend/ottolab/build.py")
    ]
    for path in sorted((ROOT / "frontend/src").rglob("*.ts*")):
        if "test" in path.parts or path.name.endswith(".gen.ts"):
            continue
        out += [(str(path.relative_to(ROOT)), line, text) for line, text in _screen_texts(path)]
    return out


def test_no_sentence_says_what_otto_did():
    said = []
    for where, line, text in _everything():
        cleaned = text
        for kept in KEPT:
            cleaned = cleaned.replace(kept, "")
        # ("Live Otto" is the name of a setting: "Live Otto needs an API key" says what the setting needs)
        cleaned = cleaned.replace("Live Otto", "the Live setting")
        if any(where == file and start in text for file, start in RECORDS):
            continue
        for phrase in BANNED:
            if phrase in cleaned:
                said.append(f"{where}:{line}: “{phrase}” in: {' '.join(text.split())[:160]}")
    assert said == [], "\n".join(said)


def test_what_stays_is_still_there():
    """The tag, the labels and the standing lines were not reworded with the rest."""
    whole = "\n".join(text for _, _, text in _everything())
    missing = [phrase for phrase in STILL_THERE if phrase not in whole]
    assert missing == []


def test_the_reader_of_this_test_sees_a_sentence_and_skips_a_note(tmp_path):
    """The test above is only worth something if its reader finds a sentence in code and passes over a docstring."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        '"""Otto proposes this in a note for developers."""\n'
        'def f(name):\n    """Otto wrote nothing here."""\n'
        '    return f"Otto found {name} here", "plain"\n',
        encoding="utf-8",
    )
    texts = [text for _, text in _backend_texts(sample)]
    assert "Otto found {…} here" in texts and not any("note for developers" in t or "wrote nothing" in t for t in texts)
    screen = tmp_path / "Sample.tsx"
    screen.write_text(
        "/** Otto proposes: a note. */\nconst a = <p>Why Otto proposes it</p>; // Otto asked\n", encoding="utf-8"
    )
    lines = [text for _, text in _screen_texts(screen)]
    assert any("Why Otto proposes it" in t for t in lines) and not any(
        "a note" in t or "Otto asked" in t for t in lines
    )
