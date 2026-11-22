# Sandbox copies: what every image is built from (ours)

Sandbox research (a prototype for Isogeny's own sandbox) makes a container image for a public copy of a library: a few
exact published versions, unpacked as data, and one piece of **asking code**. Everything in this folder is ours and is
the same for every library; the research command copies it into each image. No step of a build needs the network, and
no step runs anything of the library.

| File | What it is |
|---|---|
| `python/Dockerfile`, `node/Dockerfile` | The build recipe: the pinned base image, our test harness and controls, and a folder that was put together beforehand. It has no `RUN` step. |
| `python/asking.py`, `node/asking.js` | The asking program. It reads one question (a public key, a message, a signature) and writes one answer. It holds no cryptography. |
| `python/dummy_yes/`, `python/dummy_no/`, `node/dummy_yes/`, `node/dummy_no/` | Two deliberately useless pieces of asking code: one says yes to everything, one says no. They are the control of the known-answer check: every time asking code is checked, these two go through the same check and must be refused. |

The part that knows a library is **`asking_code.py`** (or `asking_code.js`): a refusal list and one function,
`check_signature(public_key, message, signature)`, made of straight-line calls into the library. For a library the app
had no asking code for, that one small file is written by Otto (Claude), checked by fixed rules before it is used
(`backend/ottolab/screens.py`), and shown in full with the proof of every test that uses it. It decides nothing: it
passes a question on and hands the library's own answer back. The right answers never enter the container.
