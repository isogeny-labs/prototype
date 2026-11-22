# Fixtures of the sandbox tests

Made by one real run of the research command in locked containers on 22 November 2026 (`python -m ottolab.build next
--sandbox`, started through the app's own Design and prove tests), on recorded answers and the recorded registry of
`tools/research_demo.py --sandbox`: the advisory CVE-2021-43572 about starkbank-ecdsa.

- `pack-2026.11.3.json`: the signed test pack that run made (second format). It is signed with a key made for that
  run on the computer that ran it; a test trusts that key for itself, as "made on this computer".
- `lab/`: the files of that run's research lab that a trial's registration pins: the design, the chosen versions, each
  author's copy set, and each known-answer check.

They are data. A test that changes one does so on a copy. When the shape of a pack or of a copy set changes, they are
made again from a new real run (`tests/sandbox/test_sandbox_real.py`, slow set, makes the same run).
