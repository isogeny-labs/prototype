"""Reading a version number from a dependency list (phase 4d, docs/SPEC.md section 7e).

A distribution's own package version is read as its upstream version: distro backports bring security fixes,
not new features. So Debian's "3.0.17-1~deb12u2" reads as 3.0.17. Anything that is not plainly a released
version (a pre-release, a commit id, "devel") reads as None: "Couldn't tell the version". Never a guess.
"""
from __future__ import annotations

import re

_EPOCH = re.compile(r"^\d+:")
_PRE = re.compile(r"(?i)[-.~_+]?(alpha|beta|rc|ea|pre|dev|snapshot)\d*")
_PLAIN = re.compile(r"^(\d{1,6})(?:\.(\d{1,6})){0,3}([a-z])?$")

Version = tuple[tuple[int, ...], str]


def read_version(text: object) -> Version | None:
    """The upstream version as ((numbers...), letter), or None when it can't be told."""
    if not isinstance(text, str):
        return None
    v = text.strip()
    if not v or len(v) > 80:
        return None
    v = _EPOCH.sub("", v)
    if v[:1] in ("v", "V"):
        v = v[1:]
    elif v.startswith("go"):
        v = v[2:]
    v = v.split("+", 1)[0]                      # a build number
    upstream = re.split(r"[-~]", v, maxsplit=1)[0]
    rest = v[len(upstream):]
    if _PRE.search(upstream) or (rest and _PRE.match(rest.lstrip("-~"))):
        return None                             # a pre-release is not the released version
    m = _PLAIN.match(upstream)
    if not m:
        return None
    numbers = tuple(int(n) for n in re.findall(r"\d+", upstream.rstrip("abcdefghijklmnopqrstuvwxyz")))
    return numbers, (m.group(3) or "")


def key(v: Version) -> tuple:
    """For comparing: missing parts count as 0, and 1.1.1w comes after 1.1.1."""
    numbers, letter = v
    return tuple(numbers) + (0,) * (4 - len(numbers)), letter


def shown(v: Version) -> str:
    numbers, letter = v
    return ".".join(str(n) for n in numbers) + letter


def at_least(v: Version, floor: str) -> bool:
    f = read_version(floor)
    if f is None:
        raise ValueError(f"not a version: {floor!r}")
    return key(v) >= key(f)
