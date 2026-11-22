# What a public package registry says, kept as data

Recorded answers of **PyPI** (pypi.org) about the package `starkbank-ecdsa`, read on 22 November 2026. They stand in
for the registry in the tests, the walks and a demo with no internet (`EVIDENCE_LAB_REGISTRY_SOURCE`), so none of those
reads the network. Nothing in them runs.

Each document was **cut down to the fields the app reads** (`backend/app/sandbox/registries.py`); everything else PyPI
answers (the long description, the people behind the project, download counts) was left out:

| File | From | What was kept |
|---|---|---|
| `pypi/starkbank-ecdsa.json` | `https://pypi.org/pypi/starkbank-ecdsa/json` | The list of releases; for each file its name, address, size, kind, upload time, whether it was withdrawn, and PyPI's own SHA-256. |
| `pypi/starkbank-ecdsa/<version>.json` (six versions) | `https://pypi.org/pypi/starkbank-ecdsa/<version>/json` | The name, the version, and what the release says it needs (`requires_dist`, `requires_python`). |

The package files themselves are **not** in the repository. `backend/tools/research_demo.py --sandbox DIR` fetches the
six a trial uses once from `files.pythonhosted.org`, checks each against the SHA-256 pinned in that tool (the value PyPI
gives in the document above), and keeps them in `data/downloads/` like the pinned library files.
