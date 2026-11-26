"""The Observatory (design refactor, section 5): a map of the customer's systems as their files describe them, where
the cryptography is, and what each check found there.

The rule: the map draws no box, line, tie or word that the files or a check do not support. Where the files are
silent it says so in a list of gaps; it never guesses.

It reads only. Nothing in this folder runs a check, decides a result, writes a row or starts a job, and it words no
result of its own: every result word comes from the view of the page the result lives on (Verify, Evidence, the
Migration plan, Dependencies), every tag from present/source.py, every link from the pages' own. The map is worked out
from the records on every read and keeps no copy of its own.

- match.py: the one new matching rule (the scanner file's service and the dependency list's are one box).
- layout.py: from the files alone (claims, the scanner file's structure, the dependency list and its ties) to boxes,
  the places cryptography sits in each, the cryptography lane, the lines and what the files don't say. No results.
- build.py: reads the files and the pages' views from the Lab, lays the checks' own words on the layout, and gives the
  three answers of web/observatory.py: the map, one box's panel, and where a result sits on the map.
"""
