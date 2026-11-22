# Published advisory records, kept as data

Three records of the **GitHub Advisory Database** (github.com/github/advisory-database), exactly as that database
publishes them in the OSV format, read on 22 November 2026. They are licensed CC-BY-4.0 by GitHub. Nothing in them
runs, and no rating of how serious a weakness is is read from them.

| File | About | What it is used for |
|---|---|---|
| `GHSA-wj6h-64fc-37mp.json` (CVE-2024-23342) | python-ecdsa (`ecdsa` on PyPI) | A published weakness for which the record names **no fixed version** (`"introduced": "0"` and no end). The Watch list's example of "No fix yet". |
| `GHSA-92vm-mxjf-jqf3.json` (CVE-2021-43572) | `starkbank-ecdsa` on PyPI | A published weakness **with** a fixed version (2.0.1). The example for a test proven on public copies with asking code that was written for it. |
| `GHSA-9wx7-jrvc-28mm.json` | `starkbank-ecdsa` (the same weakness, listed a second time for several packages) | Shows what the app says about a second record for the same weakness. |

SHA-256 of each file as read:

```
0e7abfa52214fe7a2967a10ba07b18b94ebef162aa37b64fb11a387e560cffcd  GHSA-92vm-mxjf-jqf3.json
05ae74823d7e9532efdf19295a1564f21917cebeefe74eb89c087da3cca3b6dc  GHSA-9wx7-jrvc-28mm.json
020148c72902fd56a3e7e29fa8b1868d724b9cf7b97252455b4dfb8d351b8375  GHSA-wj6h-64fc-37mp.json
```

They stand in for the public source (OSV, `api.osv.dev`), which gives records in this same format: `backend/app/sandbox/demo.py`
writes them into a folder of recorded answers (`EVIDENCE_LAB_ADVISORY_SOURCE`), so the tests, the walks and a demo with no
internet read them and never the network. They were **not** recorded from `api.osv.dev` itself.

One of the recorded answers that module can write is **Demo data**: the `starkbank-ecdsa` record as it would have read
before its fixed version was named (the fixed version is taken out, and its title says "Demo data"). It exists only to
show, with no internet, what the Watch list does on the day a fix is published. The record as published is the other one.
