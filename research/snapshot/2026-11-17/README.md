# Advisory snapshot, 2026-11-17

`advisories.json` holds six real, published security advisories, each with
pieces of its official source text copied word for word. It is a fixed, dated
copy for Evidence Lab to use in place of the live web pages, which can change.

## The rule

- Every excerpt is an exact piece of a page or file downloaded with `curl` on
  2026-11-17 (UTC). Nothing comes from search results, summaries or memory, and
  nothing was reworded.
- `sha256` is the fingerprint of the downloaded bytes. `url` is the page a
  person would open; `fetched_from` is the address the bytes came from.
- From the advisory database (JSON files) an excerpt is the text of a field
  (`summary`, `details`) or an exact piece of the raw file, such as
  `"fixed": "6.5.7"`. Web-page table rows keep their HTML tags so they stay
  exact (in the OpenJDK table, `&#8226;` is the dot that marks an affected
  version). Source code is quoted as whole lines, from the fixed release and,
  where the lines changed, from the release before it.

## The six advisories

"Published" is the date the source gives: the advisory database record's
`published` field or, for CVE-2022-21449, the date of the OpenJDK advisory.

| Advisory | Package | Published | Sources quoted | Licence |
|---|---|---|---|---|
| CVE-2022-21449 (GHSA-cj8x-r9fp-q656) | openjdk (OpenJDK) | 2022-04-19 | OpenJDK Vulnerability Advisory 2022/04/19; Oracle Critical Patch Update Advisory, April 2022 (Java SE risk matrix) and its text form; JDK source at tags `jdk-17.0.3+7` (fixed) and `jdk-17.0.2+8` (affected): `ECDSAOperations.java`, `make/conf/version-numbers.conf` | Pages: none recorded (`null`); JDK source: GPL-2.0-only WITH Classpath-exception-2.0 |
| CVE-2019-14859 (GHSA-8qxj-f9rh-9fg2) | python-ecdsa (PyPI) | 2020-04-01 | Advisory database record; `NEWS` at 0.13.3; `ecdsa/der.py` at tags `python-ecdsa-0.13.3` (fixed) and `python-ecdsa-0.13.2` (affected); `ecdsa/util.py` and `ecdsa/test_der.py` at 0.13.3 | Record: CC-BY-4.0; files: MIT |
| CVE-2019-14853 (GHSA-pwfw-mgfj-7g3g) | python-ecdsa (PyPI) | 2019-10-08 | Advisory database record; `NEWS` at 0.13.3; `ecdsa/keys.py`, `ecdsa/der.py`, `ecdsa/util.py` at the same two tags; `ecdsa/test_malformed_sigs.py` at 0.13.3 | Record: CC-BY-4.0; files: MIT |
| CVE-2024-42460 (GHSA-977x-g7h5-7qgw) | elliptic (npm) | 2024-08-02 | Advisory database record; `lib/elliptic/ec/signature.js` at tags `v6.5.7` (fixed) and `v6.5.6` (affected) | Record: CC-BY-4.0; files: MIT |
| CVE-2024-42461 (GHSA-49q7-c7j4-3p7m) | elliptic (npm) | 2024-08-02 | Advisory database record; `lib/elliptic/ec/signature.js` at the same two tags | Record: CC-BY-4.0; files: MIT |
| CVE-2024-42459 (GHSA-f7q4-pwc6-w24p) | elliptic (npm) | 2024-08-02 | Advisory database record; `lib/elliptic/eddsa/signature.js` at the same two tags | Record: CC-BY-4.0; files: MIT |

Things to know:

- python-ecdsa is published on PyPI as `ecdsa`; the advisory database records
  use that name. Its repository was `warner/python-ecdsa` (the advisory text
  still shows that address) and is now `tlsfuzzer/python-ecdsa`.
- The python-ecdsa release note for 0.13.3 names only CVE-2019-14853. It is
  also quoted under CVE-2019-14859 because it says the release fixes
  "signature malleability", the weakness that record describes. The two test
  files quoted are new in 0.13.3.
- None of the three pages quoted for CVE-2022-21449 names the fixed version.
  The JDK source shows it: the check is in the source tagged `jdk-17.0.3+7`
  and not in the source tagged `jdk-17.0.2+8`, and each tag's
  `version-numbers.conf` states its version.
- GHSA-cj8x-r9fp-q656, the advisory database's record for CVE-2022-21449, is
  listed as an alias but not quoted. It is marked unreviewed and lists more
  affected versions (Java SE 7u331, 8u321, 11.0.14; GraalVM 20.3.5) than
  Oracle's page does today. It was last changed on 2022-04-20; Oracle's page
  says the affected versions for this CVE were updated on 2022-April-21.

## Pinned versions

GitHub files were downloaded at an exact commit, so the same bytes can be
downloaded again. Tags were looked up with `git ls-remote`; each file was also
downloaded by tag name and gave the same bytes.

| Repository | Release tag | Commit |
|---|---|---|
| github/advisory-database | head of `main` on 2026-11-17, 18:37 UTC | `972e601381384328dcd350dafc6c03867686ad2a` |
| openjdk/jdk17u | `jdk-17.0.3+7` (also `jdk-17.0.3-ga`) | `c1a87498eac64a014786274e564e1b0b1e4afc51` |
| openjdk/jdk17u | `jdk-17.0.2+8` (also `jdk-17.0.2-ga`) | `6f0f42630eac1febf562062afc523fdf3d2a920a` |
| tlsfuzzer/python-ecdsa | `python-ecdsa-0.13.3` | `7add2213c992f51267eed8288b560f3f4108a28d` |
| tlsfuzzer/python-ecdsa | `python-ecdsa-0.13.2` | `bb359d32e93acc3eb4d216aff4ba0e7531599cfb` |
| indutny/elliptic | `v6.5.7` | `3e46a48fdd2ef2f89593e5e058d85530578c9761` |
| indutny/elliptic | `v6.5.6` | `03e06e135c8e44a2da560fa197d0ba1e1e2759e9` |

The npm registry records for elliptic 6.5.7 and 6.5.6 name the same two commits
(`gitHead`).

The two oracle.com pages embed scripts that change with every request, so a new
download has a different `sha256`. In a second download a few minutes later the
advisory part of both pages was byte for byte the same and every excerpt was
found again. To re-check an Oracle excerpt, look for its text in the page
instead of comparing the fingerprint. The openjdk.org page gave identical bytes
the second time.

## Licences and attribution

- **GitHub Advisory Database** (five records): its `LICENSE.md` at the commit
  above is the "Creative Commons Attribution 4.0 International Public License"
  (CC-BY-4.0).

  Attribution: this snapshot contains text from the GitHub Advisory Database
  (https://github.com/github/advisory-database), licensed under the Creative
  Commons Attribution 4.0 International Public License. Licence text:
  https://raw.githubusercontent.com/github/advisory-database/972e601381384328dcd350dafc6c03867686ad2a/LICENSE.md.
  Records used: GHSA-8qxj-f9rh-9fg2, GHSA-pwfw-mgfj-7g3g, GHSA-977x-g7h5-7qgw,
  GHSA-49q7-c7j4-3p7m and GHSA-f7q4-pwc6-w24p, each at
  `https://github.com/advisories/<id>`. The excerpts are unchanged pieces of
  those records. The licence gives no warranties (its section 5).
- **python-ecdsa** files: MIT (`setup.py` says `license="MIT"`). Its LICENSE
  file begins `"python-ecdsa" Copyright (c) 2010 Brian Warner`.
- **elliptic** files: MIT (`package.json` says `"license": "MIT"`). Its README
  says "Copyright Fedor Indutny, 2014."
- **JDK source** files: GNU General Public License version 2 only, with the
  "Classpath" exception, as each file's header says. Copyright Oracle and/or
  its affiliates.
- **openjdk.org and oracle.com pages**: no licence recorded (`null`). The
  openjdk.org footer shows "License: GPLv2", but the site's terms of use speak
  of GPLv2 as the licence for code, so it is not recorded for the advisory
  text. The oracle.com pages carry an Oracle copyright line and no open
  licence.

## Sites that could not be reached from the build machine

Nothing in the snapshot comes from these:

- Found blocked before the snapshot was built and not tried again: github.com
  web pages (including `github.com/advisories`), api.github.com,
  docs.github.com, nvd.nist.gov, cve.org, cveawg.mitre.org, osv.dev,
  security-tracker.debian.org.
- Tried once on 2026-11-17 and refused: mail.openjdk.org (the OpenJDK 17.0.3
  release announcement).

So the `url` addresses on github.com were written from the repository, tag and
file path and were not opened, and the further advisory-database terms that its
README points to on docs.github.com were not read.

## How it was checked

A script recomputed the fingerprint of every downloaded file and checked that
every excerpt is an exact piece of it. All 64 excerpts in 31 sources passed.
The downloaded files and the script are kept outside this repository, in the
scratch folder of the session that built the snapshot.
