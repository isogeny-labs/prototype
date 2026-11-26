"""The one new matching rule of the Observatory (design refactor, sections 5 and 9).

The scanner file names the thing it describes (its top component), and so can the dependency list. The map draws the
two as ONE box only when both give a name and a version and both are the same; the box then says "Named in both
files, with the same name and version". In every other case the dependency list's own software is listed apart and
nothing is merged.

"The same" is the rule Dependencies already uses to tie a top entry to a signing program (dependencies/tree.py): the
name compared without regard to capital letters, the version letter for letter. Runs of spaces count as one space,
because both readers already keep names that way. A file that gives no version is never matched: no version is not
"the same version".
"""

from __future__ import annotations


def _name(value: object) -> str:
    return " ".join(str(value).split()).casefold() if isinstance(value, str) else ""


def _version(value: object) -> str:
    return " ".join(str(value).split()) if isinstance(value, str) else ""


def same_service(scanner: tuple[object, object] | None, listed: tuple[object, object] | None) -> bool:
    """Are the scanner file's top component and the thing the dependency list describes one and the same?
    Each is (name, version), or None when its file does not name one."""
    if scanner is None or listed is None:
        return False
    a_name, a_version = _name(scanner[0]), _version(scanner[1])
    b_name, b_version = _name(listed[0]), _version(listed[1])
    return bool(a_name and a_version) and a_name == b_name and a_version == b_version


__all__ = ["same_service"]
