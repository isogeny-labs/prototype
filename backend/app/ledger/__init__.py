"""Phase 5b: one list of every check in an assessment, the four work groups, and the links between related items.

Nothing in here runs a check or decides a result. Every result is worded by the same function each page already uses
for that run (`Lab._result`), every fix status by the Fixes view, every Verify answer by Verify. This folder only
gathers them, sorts them into groups and links them. It never imports the reviewer (`tests/ledger` checks that).
"""
