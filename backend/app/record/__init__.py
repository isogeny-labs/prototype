"""Evidence as the full record (design refactor, section 6; decisions H and I, 26 November 2026).

Reads only. This package puts the records an assessment already keeps into time order and says who did what:

- `reading.py` reads one assessment's records once: every run as its own page words it, every record of what people did,
  and the presses kept since names were kept (`actions`, `action_runs`);
- `entries.py` makes one timeline entry for each thing that happened (one entry for one press: the runs a press
  started are in its entry);
- `history.py` picks the history of one item (a check, a fix, a change, a system, an advisory) out of those entries;
- `views.py` (`RecordMixin`, mixed into `Lab`) holds the five reads the screens ask for;
- `part.py` makes the "who did what" part of the signed evidence file.

Nothing here decides, runs, writes or starts anything. Every result word shown is the one the reviewer's review or the
item's own page already gives (`Lab._result` through the ledger of `app/ledger/checks.py`, Verify's own words); every
other sentence is in `app/present/record.py`. A person is never shown as the decider of a result.
"""
