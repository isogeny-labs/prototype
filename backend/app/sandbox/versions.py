"""Sandbox research: versions, by fixed rules (no package of ours or anyone's is asked).

Three questions:
  - which of a library's published versions are plainly released ones, in order (a pre-release is never picked);
  - which versions a trial runs on, given what the advisory's own ranges say: the fixed version, the last release
    before it, the version the file names, and up to two more on each side;
  - does a version fit what a library states it needs of a helper library. Two small readers, one for PyPI's
    form (">=1.9.0,<2") and one for npm's ("^1.2.3", "~1.2", "1.x", ">=1.0.0 <2.0.0", "a || b"). What they can't read
    is said to be unreadable (None), never guessed.
"""

from __future__ import annotations

import re
from typing import cast

from app.knowledge.versions import key as version_key
from app.knowledge.versions import read_version

MAX_MORE = 2  # further versions on each side of a trial


def order(version: object) -> tuple | None:
    """A key to sort released versions by, or None for anything that is not plainly a released version."""
    read = read_version(version)
    return version_key(read) if read is not None else None


def released(versions: list[dict]) -> list[dict]:
    """The plainly released versions of a registry's list ([{"version", "published"}]), oldest first, each once."""
    seen: dict[tuple, dict] = {}
    for entry in versions:
        key = order(entry.get("version"))
        if key is not None and key not in seen:
            seen[key] = entry
    return [seen[k] for k in sorted(seen)]


class NoVersions(Exception):
    """A trial can't be put together; the message is one plain sentence."""


def choose(ranges: list[dict], releases: list[dict], yours: list[str]) -> dict:
    """The versions a trial runs on: {"fixed", "affected", "yours": [...], "more_affected": [...], "more_fixed": [...],
    "after_last_affected": bool}. `ranges` are the advisory's own ([{"introduced", "fixed", "last_affected"}]), `releases`
    the registry's list, `yours` the versions the assessment names. Raises NoVersions with the reason."""
    listed = released(releases)
    keys = cast(
        "list[tuple]", [order(r["version"]) for r in listed]
    )  # (released() keeps only versions that have a key)
    mine = cast("list[tuple]", [order(v) for v in yours if order(v) is not None])

    def holds(r: dict, key: tuple) -> bool:
        low = order(r.get("introduced")) if r.get("introduced") not in ("0", "", None) else None
        if low is not None and key < low:
            return False
        if r.get("fixed"):
            top = order(r["fixed"])
            return top is not None and key < top
        if r.get("last_affected"):
            top = order(r["last_affected"])
            return top is not None and key <= top
        return True  # no end is named

    ended = [r for r in ranges if r.get("fixed") or r.get("last_affected")]
    if not ended:
        raise NoVersions("the source names no fixed version")
    # the range the file's own version lies in, or else the one with the newest end
    chosen = next((r for r in ended if any(holds(r, k) for k in mine)), None)
    if chosen is None:
        chosen = max(ended, key=lambda r: order(r.get("fixed") or r.get("last_affected")) or ())
    after_last = not chosen.get("fixed")
    if after_last:
        last = order(chosen["last_affected"])
        if last is None:
            raise NoVersions("the last affected version the source names could not be read")
        later = [r for r, k in zip(listed, keys, strict=True) if k > last]
        if not later:
            raise NoVersions(
                f"no version after {chosen['last_affected']} is published, so there is no fixed version to try"
            )
        fixed = later[0]["version"]
    else:
        fixed = next((r["version"] for r, k in zip(listed, keys, strict=True) if k == order(chosen["fixed"])), None)
        if fixed is None:
            raise NoVersions(f"the fixed version {chosen['fixed']} is not among the versions the registry lists")
    fixed_key = order(fixed)
    assert fixed_key is not None
    inside = [r["version"] for r, k in zip(listed, keys, strict=True) if k < fixed_key and holds(chosen, k)]
    if not inside:
        raise NoVersions(f"no affected version is published before {fixed}")
    affected = inside[-1]  # the last release before the fix: the closest pair
    # (the file's own affected versions, each once. All of them go into the copy set, so an accepted check can run on
    #  each; the trial itself has room for MAX_MORE further versions, the file's own first: see ottolab/sandbox.register)
    own = [v for v in dict.fromkeys(yours) if v in inside and v != affected]
    more_affected = [v for v in reversed(inside[:-1]) if v not in own][: max(0, MAX_MORE - len(own))]
    still_affected = [r for r in ranges if r is not chosen]
    after = [
        r["version"]
        for r, k in zip(listed, keys, strict=True)
        if k > fixed_key and not any(holds(r2, k) for r2 in still_affected)
    ]
    more_fixed = list(dict.fromkeys(after[:1] + after[-1:]))[:MAX_MORE]
    return {
        "fixed": fixed,
        "affected": affected,
        "yours": own,
        "more_affected": more_affected,
        "more_fixed": more_fixed,
        "after_last_affected": after_last,
    }


# ---------------------------------------------------------------- does a version fit what a library says it needs?

_CLAUSE = re.compile(r"^\s*(~=|==|!=|<=|>=|<|>)\s*([0-9][0-9A-Za-z.*]*)\s*$")


def fits_pypi(specifier: str, version: str) -> bool | None:
    """PyPI's form: clauses joined by commas, each an operator and a version ("" fits everything). None: not readable."""
    mine = order(version)
    if mine is None:
        return None
    for clause in [c for c in str(specifier).split(",") if c.strip()]:
        m = _CLAUSE.match(clause)
        if not m:
            return None
        op, text = m.groups()
        star = text.endswith(".*")
        base = order(text[:-2] if star else text)
        if base is None or (star and op not in ("==", "!=")):
            return None
        numbers = [int(n) for n in re.findall(r"\d+", text[:-2] if star else text)]
        if op in ("==", "!=") and star:
            same = list(mine[0][: len(numbers)]) == numbers
            ok = same if op == "==" else not same
        elif op == "==":
            ok = mine == base
        elif op == "!=":
            ok = mine != base
        elif op == "~=":
            if len(numbers) < 2:
                return None
            ok = mine >= base and list(mine[0][: len(numbers) - 1]) == numbers[:-1]
        else:
            ok = {"<": mine < base, "<=": mine <= base, ">": mine > base, ">=": mine >= base}[op]
        if not ok:
            return False
    return True


_PART = re.compile(r"^(\^|~|>=|<=|>|<|=)?v?(\d+|[xX*])(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?$")


def _npm_one(part: str, mine: tuple) -> bool | None:
    m = _PART.match(part)
    if not m:
        return None
    op, *raw = m.groups()
    numbers = []
    for n in raw:
        if n is None or n in ("x", "X", "*"):
            break
        numbers.append(int(n))
    mine_numbers = list(mine[0][:3])
    low = tuple(numbers + [0] * (3 - len(numbers)))

    def upper(keep: int) -> tuple:
        """The first version that no longer fits: the part at `keep` goes up by one."""
        head = numbers[: keep + 1] if len(numbers) > keep else numbers
        head = head[:-1] + [head[-1] + 1] if head else []
        return tuple(head + [0] * (3 - len(head)))

    here = tuple(mine_numbers)
    if len(numbers) == 0:
        return op in (None, "=", ">=", "<=", "^", "~")
    if op in (None, "="):
        return here == low if len(numbers) == 3 else low <= here < upper(len(numbers) - 1)
    if op == "^":
        first = next((i for i, n in enumerate(numbers) if n != 0), len(numbers) - 1)
        return low <= here < upper(first)
    if op == "~":
        return low <= here < upper(min(1, len(numbers) - 1))
    if op == ">=":
        return here >= low
    if op == ">":
        return here >= upper(len(numbers) - 1) if len(numbers) < 3 else here > low
    if op == "<":
        return here < low
    return here < upper(len(numbers) - 1) if len(numbers) < 3 else here <= low  # <=


def fits_npm(range_text: str, version: str) -> bool | None:
    """npm's form: alternatives joined by "||", each a list of parts that must all hold. None: not readable (a tag, an
    address, a pre-release, anything this small reader does not know)."""
    mine = order(version)
    text = str(range_text).strip()
    if mine is None or len(text) > 200:
        return None
    if text in ("", "*", "x", "latest"):
        return True if text != "latest" else None
    result = False
    for alternative in text.split("||"):
        words = alternative.split()
        if len(words) == 3 and words[1] == "-":  # "1.2.3 - 2.3.4"
            words = [">=" + words[0], "<=" + words[2]]
        if not words:
            return None
        ok = True
        for word in words:
            one = _npm_one(word, mine)
            if one is None:
                return None
            ok = ok and one
        result = result or ok
    return result
