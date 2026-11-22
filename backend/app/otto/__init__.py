"""Otto in Evidence Lab (phase 5c): the adapter between this app and Adam's Otto harness.

Adam's code is never copied into this repository. One exact commit of it is named in backend/otto.lock.json,
fetched by the prepare step into backend/.otto/<commit>/ (ignored by git), checked against its fingerprint and
loaded from there (harness.py). Everything in this package only adapts: it reads signed test packs (packs.py),
puts their tests into the engine socket (engine.py), keeps the hash-chained record of every loop run with Otto's
own ledger (assurance.py) and asks Claude for a fix to your own code (model.py), recorded or live.

Nothing here decides a result: that stays in engine/reviewer.py.
"""
