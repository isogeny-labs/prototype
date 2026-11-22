# Real libraries (phase 4c)

This folder holds the small **wrappers** that let Evidence Lab test real crypto libraries written by
others, in exact versions. A wrapper only translates the app's one-line JSON contract
(see [docs/ADAPTER.md](../../docs/ADAPTER.md)) into the library's own calls. It holds no crypto of its own.

The libraries' own files are **not stored in this repository**. Only `cd backend && .venv/bin/python -m app.prepare`
downloads and builds anything: it fetches each pinned file once, checks it by fingerprint, and builds one
locked-down image per family (no network inside, not root). The app itself never downloads. The libraries run
only in isolated mode (Docker). Where each file comes from, and its fingerprint, is pinned in
`backend/app/real_libraries.py`.

Each family has its own folder with a wrapper, a `Dockerfile` and a `subjects.json` (the image's own fixed table
of what can run).

| Folder | Library and versions | Where its files come from | Wrapper |
|---|---|---|---|
| `java/` | Java (OpenJDK, Temurin build) 17.0.2 and 17.0.3 | Two pinned Eclipse Temurin images, one per version | `EcdsaAdapter.java` |
| `python-ecdsa/` | python-ecdsa 0.13.2 and 0.13.3 | Two pinned wheels from PyPI, checked by SHA-256 | `ecdsa_adapter.py` |
| `elliptic/` | elliptic (npm) 6.5.6 and 6.5.7 | Pinned npm files for elliptic and its seven dependencies, checked by their npm integrity values, run by Node from a pinned Node image | `elliptic_adapter.js` |
| `openssl/` | OpenSSL 3.5.9 (ECDSA P-256, ML-DSA-65, ML-KEM-768) | `libcrypto` copied from a pinned OpenSSL image | `openssl_adapter.py` (and `pq_controls.py`, the deliberately broken copies the post-quantum exams use as controls) |

To try them: upload `demo/real-libraries.csv` on the **1. Import** step (not Demo data), or run one by hand with
`cd backend && .venv/bin/python tools/try_real_library.py <name> <version>`.

## Licences

The libraries are other people's software, used under their own licences, as recorded when they were chosen:

| Library | Licence |
|---|---|
| python-ecdsa | MIT |
| elliptic | MIT |
| elliptic's seven npm dependencies (`bn.js`, `brorand`, `hash.js`, `hmac-drbg`, `inherits`, `minimalistic-assert`, `minimalistic-crypto-utils`) | MIT or ISC (`inherits` and `minimalistic-assert` are ISC) |
| OpenJDK | GPLv2 with the Classpath Exception |
| OpenSSL | Apache-2.0 |
