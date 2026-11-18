"""Build Otto's test packs:  cd backend && .venv/bin/python -m ottolab.build ship|next|audit ...

    ship    The two packs shipped with the app, from the dated snapshot under research/snapshot/: read each advisory,
            design a test, try it on public copies, propose the publisher's fix and try that too, all recorded in the
            Otto lab under research/lab/ by Adam's harness; then sign research/packs/<version>.json. The signing key
            is made for this build and its private half is thrown away at the end; the public half goes into the
            app's trusted keys. A pack that is already there is never rebuilt.

    next    The next pack, built on this computer from advisory files you put in an inbox folder (each a snapshot
            file). With --live and a key in ANTHROPIC_API_KEY, Otto asks Claude for real, within --limit US dollars
            for the run. The pack is signed with a key made on this computer, goes into the data folder's updates,
            and is shown in the app as made here.

    audit   Otto's own audit of the research ledger, with every pinned checker run again.

Trials need the pinned Otto harness (./run-demo.sh fetches it) and, for real libraries, Docker with the prepared
images (isolated mode). Nothing here decides a test result or judges a trial: the reviewer and Otto's harness do.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.canonical import canonical_bytes, sha256_hex
from app.config import REPO_ROOT, load_settings
from app.otto import designs, harness, model, packs
from ottolab import research, snapshot

RESEARCH = REPO_ROOT / "research"
SNAPSHOT = RESEARCH / "snapshot" / "2026-11-17" / "advisories.json"
RECORDED = RESEARCH / "recorded"
LAB = RESEARCH / "lab"
PACKS = RESEARCH / "packs"
BACKEND = Path(__file__).resolve().parents[1]
# The two shipped packs: which advisories of the snapshot each one holds.
SHIP_PLAN = (("2026.11.1", ("CVE-2022-21449", "CVE-2019-14859", "CVE-2019-14853")),
             ("2026.11.2", ("CVE-2024-42460", "CVE-2024-42461", "CVE-2024-42459")))
SHIP_SIGNER = "Isogeny Labs demo pack key (made when the packs were built; its private half was thrown away)"
LOCAL_SIGNER = "A key made on this computer by the live research command"
LOCAL_KEY_PEM = "otto-local-pack-key.pem"
MAX_STEPS = 400


def say(text: str) -> None:
    print(text, flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _public_hex(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def sign(pack: dict, key: Ed25519PrivateKey) -> bytes:
    """The exact bytes of a pack file: canonical JSON of {pack, fingerprint, public_key, signature}."""
    fingerprint = sha256_hex(pack)
    signature = key.sign(packs.SIGNING_CONTEXT + fingerprint.encode("ascii")).hex()
    return canonical_bytes({"pack": pack, "fingerprint": fingerprint, "public_key": _public_hex(key), "signature": signature})


# ---------------------------------------------------------------- the loop, on Adam's harness

def run_loop(lab, snapshot_path: Path, recorded: Path, live: bool, limit_nano: int, spent_file: Path, earlier_file: Path) -> str:
    """Adam's research loop on this lab: his harness runs, judges, replays and verifies; our agent command does the
    steps that need judgement. The model judge of his loop is never used (its command is set to one that fails)."""
    os.environ.update({research.ENV_SNAPSHOT: str(snapshot_path), research.ENV_RECORDED: str(recorded),
                       research.ENV_LIVE: "1" if live else "0", research.ENV_LIMIT: str(limit_nano), research.ENV_SPENT: str(spent_file),
                       research.ENV_EARLIER: str(earlier_file),
                       "EVIDENCE_LAB_BACKEND": str(BACKEND), "OTTO_JUDGE_CMD": "false",
                       "PYTHONPATH": os.pathsep.join([str(BACKEND)] + [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p])})
    agent = f"{shlex.quote(sys.executable)} -m ottolab.agent"
    return harness.module("loop").loop(lab, MAX_STEPS, research.EXECUTOR, research.VALIDATOR, agent, log=lambda line: say("  " + str(line)))


def research_advisories(lab, snap: dict, snapshot_sha256: str, ids: tuple[str, ...], **loop_args) -> None:
    """Everything the research side does for these advisories: the test questions and their trials first, then a fix
    question for every advisory whose test held, and those trials."""
    for advisory_id in ids:
        advisory = snapshot.advisory_of(snap, advisory_id)
        if research.find_question(lab.state(), advisory_id, "test") is None:
            lab.add(research.test_question(advisory, snap, snapshot_sha256), research.COORDINATOR)
    say("  tests: read, design, try on public copies")
    run_loop(lab, **loop_args)
    asked = False
    for advisory_id in ids:
        st = lab.state()
        trials = [hid for hid, _ in research.trials_of(st, advisory_id, "test", lab) if research.held(st, lab, hid)]
        if trials and research.find_question(st, advisory_id, "fix") is None:
            lab.add(research.fix_question(snapshot.advisory_of(snap, advisory_id), trials[-1]), research.COORDINATOR)
            asked = True
    if asked:
        say("  fixes: the publisher's fixed version, tried on public copies")
        run_loop(lab, **loop_args)


# ---------------------------------------------------------------- from the ledger to a pack

def _arm_figures(st, hid: str, hyp: dict) -> dict:
    out = {}
    for arm, spec in hyp["arms"].items():
        command = spec["command"]
        figures: dict = {}
        for flag, name in (("--library", "library"), ("--version", "version")):
            if flag in command:
                figures[name] = command[command.index(flag) + 1]
        run = next((r for _, r in st.runs(hid) if r["arm"] == arm and r["status"] == "completed"), None)
        figures.update((run or {}).get("metrics") or {})
        if not figures:
            figures = {"status": "not run"}
        out[arm] = figures
    return out


def _trial(st, lab, hid: str, hyp: dict) -> dict | None:
    decision = st.decision(hid)
    if decision is None:
        return None
    replayed = any(a["hypothesis_id"] == hid and a["replayed"] and not a["mismatches"] and a["code_ok"]
                   and a["author"] not in {r["author"] for _, r in st.runs(hid)} for _, a in st.of("audit"))
    return {"hypothesis": hid, "decision": decision[0], "outcome": decision[1]["outcome"], "replayed": bool(replayed),
            "arms": _arm_figures(st, hid, hyp)}


def _entry_words(kind: str, record: dict) -> str:
    """One plain line about a ledger entry. It repeats what the entry holds; it words no result of a test."""
    if kind == "question":
        return "Question asked: " + record["title"]
    if kind == "objective":
        return "A Claude step to be checked: " + record["verifier"].get("params", {}).get("step", "a step")
    if kind == "claim":
        step = record["artifact"]["step"]
        return f"Claude step recorded: {step['step']}, answer {record['artifact']['outcome']} ({step['source']})"
    if kind == "verdict":
        return f"The pinned checker's verdict on the step record: {record['status']}"
    if kind == "hypothesis":
        return "Trial registered before any run: " + record["title"]
    if kind == "run":
        figures = ", ".join(f"{k} {v}" for k, v in sorted(record["metrics"].items())) or record["status"].replace("_", " ")
        return f"Trial run, arm {record['arm']}: {figures}"
    if kind == "decision":
        return f"Otto's harness judged the trial against its frozen thresholds: {record['outcome'].replace('_', ' ')}"
    if kind == "audit":
        return (f"Replayed in a separate step under a second author's name (the same build, on the same computer): "
                f"{record['replayed']} runs, {len(record['mismatches'])} mismatches")
    if kind == "fact":
        return ("Dead end recorded: " if record["kind"] == "dead_end" else "Fact recorded: ") + record["statement"]
    if kind == "correction":
        return "Note: " + record["note"]
    return kind


def _ledger_entries(lab, st, advisory_id: str) -> list[dict]:
    """The research ledger's entries about one advisory, oldest first: {"seq", "kind", "id", "at", "what"}."""
    mine: set[str] = set()
    questions = {qid for qid, q in st.of("question") if (research.question_about(q) or (None,))[0] == advisory_id}
    mine |= questions
    for rid in st.order:
        r = st.by_id[rid]
        t = r["type"]
        if t in ("objective", "hypothesis") and r.get("question_id") in mine:
            mine.add(rid)
        elif t == "claim" and r["objective_id"] in mine:
            mine.add(rid)
        elif t == "verdict" and r["claim_id"] in mine:
            mine.add(rid)
        elif t in ("run", "decision", "audit") and r["hypothesis_id"] in mine:
            mine.add(rid)
        elif t == "fact" and set(r["backing"]) & mine:
            mine.add(rid)
        elif t == "correction" and r["target"] in mine:
            mine.add(rid)
    out = []
    for entry in lab.ledger.entries():
        rid = lab.ledger.record_id(entry)
        if rid in mine:
            out.append({"seq": entry["seq"], "kind": entry["kind"], "id": rid, "at": entry["ts"], "what": _entry_words(entry["kind"], entry["payload"])[:300]})
    return out


def advisory_entry(lab, st, advisory: dict) -> tuple[dict, dict | None]:
    """One advisory as a pack holds it, and its design when its test is ready."""
    aid, package = advisory["id"], advisory["package"]["name"]
    steps, reading, refused = [], None, None
    for cid, claim in research.step_claims(st, aid):
        art, step = claim["artifact"], claim["artifact"]["step"]
        accepted = lab._accepted(cid, st)
        used = art["outcome"] == "used" and accepted
        steps.append({"step": step["step"], "source": step["source"], "model": step["model"], "prompt_sha256": step["prompt_sha256"],
                      "answer": step["answer"], "answer_sha256": step["answer_sha256"], "input_tokens": step["input_tokens"],
                      "output_tokens": step["output_tokens"], "cost_nano_usd": step["cost_nano_usd"], "at": step["at"], "how": step["how"],
                      "outcome": "used" if used else "refused",
                      "refusal": None if used else (art.get("refusal") or "The pinned checker did not accept the record of this step."),
                      "claim": cid})
        if step["step"] == "read_advisory":
            reading, refused = (art["parsed"], None) if used else (None, steps[-1]["refusal"])
    if reading is None and refused is None:
        refused = "Otto has no answer for this advisory yet."
    design, design_note = None, None
    found = research.used_step(st, lab, aid, "design_test")
    if found is not None:
        design_note = found[1]["artifact"]["parsed"]
    test_trials = research.trials_of(st, aid, "test", lab)
    test: dict = {"state": "none", "reason": "", "design_sha256": None, "trial": None}
    if reading is None:
        test["reason"] = "No test yet: " + str(refused)
    elif design_note is None:
        note_refusal = next((s["refusal"] for s in steps if s["step"] == "design_test" and s["outcome"] == "refused"), None)
        test["reason"] = "No test yet: " + (note_refusal or "Otto has no design for this advisory yet.")
    elif design_note["decision"] == "no_test":
        test["reason"] = "No test yet: " + design_note["reason"]
    else:
        made = designs.check_design(design_note["design"])
        test["design_sha256"] = designs.design_sha256(made)
        if not test_trials:
            test.update(state="not_offered", reason=f"Not offered: this app has no public copies of an affected and a fixed version of {package} to try the design on.")
        else:
            hid, hyp = test_trials[-1]
            trial = _trial(st, lab, hid, hyp)
            test["trial"] = trial
            arms = (trial or {}).get("arms") or {}
            affected, fixed = arms.get("affected", {}), arms.get("fixed", {})
            if trial is None:
                test.update(state="not_offered", reason="Not offered: its trial on public copies did not finish.")
            elif trial["outcome"] == "supported" and trial["replayed"]:
                design = made
                test.update(state="ready", reason=ready_reason(package, affected, fixed))
            elif trial["outcome"] == "supported":
                test.update(state="not_offered", reason="Not offered: its trial on public copies did not repeat when it was run again in a "
                                                        "separate replay step.")
            elif trial["outcome"] == "refuted":
                test.update(state="not_offered", reason=(
                    f"Not offered: the design failed its own trial. {package} {affected.get('version')}, the affected version, got all "
                    f"{affected.get('total')} selected cases right, so this check would not catch it."))
            else:
                test.update(state="not_offered", reason=("Not offered: its trial on public copies gave no usable outcome ("
                                                         + trial["outcome"].replace("_", " ") + ")."))
    fix: dict = {"state": "none", "reason": "", "kind": None, "library": None, "version": None, "quote": None, "summary": None, "trial": None}
    proposed = research.used_step(st, lab, aid, "propose_fix")
    if test["state"] != "ready":
        fix["reason"] = "No fix is offered: there is no test for this advisory to prove one with."
    elif proposed is None:
        refusal = next((s["refusal"] for s in steps if s["step"] == "propose_fix" and s["outcome"] == "refused"), None)
        fix["reason"] = "No fix is offered: " + (refusal or "Otto has no proposal for this advisory yet.")
    elif proposed[1]["artifact"]["parsed"]["fix"] == "none":
        fix["reason"] = "No fix is offered: " + proposed[1]["artifact"]["parsed"]["reason"]
    else:
        answer = proposed[1]["artifact"]["parsed"]
        fix.update(kind="update", library=package, version=answer["version"], quote=answer["quote"], summary=answer["summary"])
        fix_trials = research.trials_of(st, aid, "fix", lab)
        trial = _trial(st, lab, *fix_trials[-1]) if fix_trials else None
        fix["trial"] = trial
        arms = (trial or {}).get("arms") or {}
        before, after = arms.get("affected", {}), arms.get("fixed", {})
        if trial is None:
            fix.update(state="not_proven", reason=f"Not proven: the update to {package} {answer['version']} was not tried on public copies.")
        elif trial["outcome"] == "supported" and trial["replayed"]:
            fix.update(state="proven", reason=(
                f"Proven on public copies: on {package} {after.get('version')} this advisory's check passed and all {after.get('tests')} "
                f"pass-or-fail tests read Passed ({before.get('failing')} failed on {before.get('version')}). Speed was not part of the trial."))
        elif trial["outcome"] == "refuted":
            fix.update(state="not_proven", reason=(
                f"Not proven: on public copies {after.get('failing')} of {after.get('tests')} pass-or-fail tests still did not pass on "
                f"{package} {after.get('version')}, and a fix is offered as proven only when every locked test passes."))
        else:
            fix.update(state="not_proven", reason=("Not proven: the trial of the update gave no outcome that held ("
                                                   + trial["outcome"].replace("_", " ") + (", replayed" if trial["replayed"] else ", not replayed") + ")."))
    entry = {"id": aid, "aliases": list(advisory["aliases"]), "package": dict(advisory["package"]), "published": advisory["published"],
             # `url` is the page a person would open; `read_from` is the address the quoted bytes came from on that day
             "sources": [{"label": snapshot.source_label(i), "title": s["title"], "publisher": s["publisher"], "url": s["url"],
                          "read_from": s["fetched_from"], "fetched": s["fetched"]}
                         for i, s in enumerate(advisory["sources"])],
             "reading": reading, "reading_refused": refused, "test": test, "fix": fix, "steps": steps, "ledger": _ledger_entries(lab, st, aid)}
    return entry, design


def checks_of(pack: dict) -> list[dict]:
    """The checks a pack ships, as the duplicate rule compares them: for each ready test its advisory, the library
    that advisory is about, the pack's version and the published cases it uses."""
    about = {a["id"]: f"{a['package']['ecosystem']}/{a['package']['name']}" for a in pack["advisories"]}
    return [{"advisory": t["design"]["advisory"], "package": about[t["design"]["advisory"]], "pack": pack["version"],
             "file": t["design"]["cases"]["file"], "sha256": t["design"]["cases"]["sha256"], "ids": sorted(t["design"]["cases"]["ids"])}
            for t in pack["tests"]]


def ready_reason(package: str, affected: dict, fixed: dict) -> str:
    """What a pack says about a test that is ready, from its trial's numbers. One case is "1 case". (Pack 2026.11.2
    was signed with "1 of 1 cases wrong"; a signed pack stays as it is.)"""
    total = affected.get("total")
    return (f"Test ready: tried on public copies before this pack was signed. {package} {affected.get('version')} got "
            f"{affected.get('wrong')} of {total} {'case' if total == 1 else 'cases'} wrong, {package} {fixed.get('version')} got none wrong, "
            "and the control that must fail did.")


def same_check_twice(checks: list[dict]) -> str | None:
    """Two checks for one library that use exactly the same published cases, as one plain sentence, or None. The
    research step refuses such a design before it is tried; this is the last look before a pack is signed."""
    seen: dict[tuple, dict] = {}
    for check in checks:
        key = (check["package"], check["file"], check["sha256"], tuple(sorted(check["ids"])))
        if key in seen:
            first = seen[key]
            return (f"The check for {check['advisory']} uses exactly the published cases of the check for {first['advisory']} "
                    f"(test pack {first['pack']}), and both advisories are about the same library. That would be one check under two "
                    "names, so no pack was signed.")
        seen[key] = check
    return None


def assemble(lab, snap: dict, snapshot_sha256: str, version: str, ids: tuple[str, ...], previous: str | None, signer: str,
             earlier: list[dict] | None = None) -> dict:
    st = lab.state()
    entries, tests = [], []
    for advisory_id in ids:
        entry, design = advisory_entry(lab, st, snapshot.advisory_of(snap, advisory_id))
        entries.append(entry)
        if design is not None:
            tests.append({"design": design, "design_sha256": designs.design_sha256(design)})
    twice = same_check_twice(list(earlier or []) + checks_of({"version": version, "advisories": entries, "tests": tests}))
    if twice is not None:
        raise research.ResearchError(twice)
    sources = {step["source"] for entry in entries for step in entry["steps"]}
    answers = "live" if sources == {"live"} else "recorded" if sources <= {"recorded"} else "mixed"
    recorded_at = sorted(step["at"] for entry in entries for step in entry["steps"] if step["source"] == "recorded")
    note = {"recorded": f"Answers recorded during the build, {_day(recorded_at[0]) if recorded_at else 'no answers'}",
            "live": "Live: Claude, through the API key on the computer that built this pack",
            "mixed": "Some answers recorded during the build, some live from Claude"}[answers]
    lock = harness.read_lock()
    return {"schema": packs.PACK_SCHEMA, "version": version, "built_at": _now(), "previous": previous, "signer": signer,
            "research": {"snapshot": snap["snapshot"], "snapshot_sha256": snapshot_sha256, "answers": answers, "answers_note": note},
            "otto": {"repository": lock.repository, "commit": lock.commit, "version": lock.version, "ledger": lab.ledger.head(),
                     "scripts": {research.TRIAL: research.file_sha256(Path(lab.root) / research.TRIAL),
                                 research.CHECKER: research.file_sha256(Path(lab.root) / research.CHECKER),
                                 "ottolab/agent.py": research.file_sha256(Path(__file__).with_name("agent.py")),
                                 "ottolab/research.py": research.file_sha256(Path(__file__).with_name("research.py")),
                                 "ottolab/prompts.py": research.file_sha256(Path(__file__).with_name("prompts.py"))}},
            "advisories": entries, "tests": tests}


def _day(stamp: str) -> str:
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return stamp[:10]
    return f"{when.day} {when.strftime('%B %Y')}"


def build_pack(lab, snap: dict, snapshot_path: Path, version: str, ids: tuple[str, ...], previous: str | None, key: Ed25519PrivateKey,
               signer: str, out_dir: Path, recorded: Path, live: bool, limit_nano: int, spent_file: Path,
               earlier: list[dict] | None = None) -> packs.Pack:
    """`earlier`: the checks of the packs built before this one (`checks_of` each), so that a design which only repeats
    one of them for the same library is refused, also when that pack came out of another lab."""
    snapshot_sha256 = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    say(f"Pack {version}: {', '.join(ids)}")
    earlier_file = spent_file.with_name(f"earlier-checks-{version}.json")
    earlier_file.write_text(json.dumps(list(earlier or [])), encoding="utf-8")
    research_advisories(lab, snap, snapshot_sha256, ids, snapshot_path=snapshot_path, recorded=recorded, live=live, limit_nano=limit_nano,
                        spent_file=spent_file, earlier_file=earlier_file)
    problems = lab.audit()
    if problems:
        raise research.ResearchError("Otto's audit of the research ledger found a problem: " + "; ".join(problems[:3]))
    raw = sign(assemble(lab, snap, snapshot_sha256, version, ids, previous, signer, earlier), key)
    made = packs.read_envelope(raw, {_public_hex(key): (signer, False)})   # the builder reads its own pack back exactly as the app will
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{version}.json").write_bytes(raw + b"\n")
    for entry in made.pack["advisories"]:
        say(f"  {entry['id']}: {entry['test']['reason']}")
        say(f"    fix: {entry['fix']['reason']}")
    say(f"  signed: {out_dir / (version + '.json')} (fingerprint {made.fingerprint[:16]}...)")
    return made


def _spent_line(spent_file: Path, limit_nano: int) -> str:
    spent, calls, unanswered = research._spent(str(spent_file))
    maybe = (f" Up to {model.dollars(unanswered)} more may have been billed for requests that got no answer; that counted against the "
             "limit too." if unanswered else "")
    return (f"Claude: {calls} live {'call' if calls == 1 else 'calls'}, {model.dollars(spent)} spent of a limit of "
            f"{model.dollars(limit_nano)} for this run.{maybe}")


# ---------------------------------------------------------------- the commands

def ship(args) -> int:
    snap = snapshot.read_snapshot(SNAPSHOT)
    existing = sorted(p.stem for p in PACKS.glob("*.json") if packs._VERSION.match(p.stem)) if PACKS.is_dir() else []
    todo = [(version, ids) for version, ids in SHIP_PLAN if version not in existing]
    if not todo:
        say("Both shipped packs are already built, and a shipped pack is never rebuilt. New advisories go into the next pack "
            "(python -m ottolab.build next --inbox DIR).")
        return 0
    if existing:
        say("Some shipped packs exist and some do not. They are signed together, with one key whose private half is thrown away, so "
            "the missing ones can't be added now. Nothing was built.")
        return 1
    lab = open_lab(LAB)
    key = Ed25519PrivateKey.generate()
    previous = None
    with tempfile.TemporaryDirectory(prefix="ottolab-") as scratch:
        spent_file = Path(scratch) / "spent.json"
        earlier: list[dict] = []
        for version, ids in todo:
            made = build_pack(lab, snap, SNAPSHOT, version, ids, previous, key, SHIP_SIGNER, PACKS, RECORDED, args.live, args.limit_nano,
                              spent_file, earlier)
            previous = made.fingerprint
            earlier = earlier + checks_of(made.pack)
        say(_spent_line(spent_file, args.limit_nano))
    packs.TRUSTED_KEYS_FILE.write_text(json.dumps({"schema": packs.KEYS_SCHEMA, "keys": [
        {"public_key": _public_hex(key), "label": SHIP_SIGNER, "made": _now()[:10]}]}, indent=1) + "\n", encoding="utf-8")
    del key   # the private half is never written anywhere
    say(f"The public key is in {packs.TRUSTED_KEYS_FILE.relative_to(REPO_ROOT)}. The private half was thrown away.")
    return 0


def _local_key(data_dir: Path) -> Ed25519PrivateKey:
    """This computer's own pack key: made on first use, kept in the data folder (for this user only)."""
    path = data_dir / LOCAL_KEY_PEM
    if not path.exists():
        pem = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(pem)
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise research.ResearchError("This computer's pack key could not be read.")
    (data_dir / packs.LOCAL_KEY_FILE).write_text(_public_hex(key) + "\n", encoding="ascii")
    return key


def next_pack(args) -> int:
    settings = load_settings()
    data_dir = Path(args.data_dir).resolve() if args.data_dir else settings.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    inbox = Path(args.inbox)
    files = sorted(p for p in inbox.glob("*.json")) if inbox.is_dir() else []
    if not files:
        say(f"No advisory files in {inbox}. Put one snapshot file there (the shape of research/snapshot/*/advisories.json).")
        return 1
    if len(files) > 1:
        say("One snapshot file at a time: the inbox holds more than one .json file.")
        return 1
    snap = snapshot.read_snapshot(files[0])
    keys = packs.trusted_keys(data_dir)
    updates = data_dir / "otto-updates"
    shipped, _ = packs.found_in(Path(args.shipped) if args.shipped else PACKS, keys)
    local, _ = packs.found_in(updates, keys)
    chain = sorted(shipped + local, key=lambda p: packs.version_key(p.version))
    newest = chain[-1] if chain else None
    now = datetime.now(timezone.utc)
    number = 1
    if newest is not None:
        year, month, last = packs.version_key(newest.version)
        if (year, month) == (now.year, now.month):
            number = last + 1
        elif (year, month) > (now.year, now.month):
            now, number = now.replace(year=year, month=month, day=1), last + 1
    version = f"{now.year}.{now.month}.{number}"
    seen = {a["id"] for pack in chain for a in pack.pack["advisories"]}
    ids = tuple(a["id"] for a in snap["advisories"] if a["id"] not in seen)
    if not ids:
        say("Every advisory in the inbox is already in an earlier pack.")
        return 1
    lab = open_lab(data_dir / "otto-research-lab")
    recorded = Path(args.recorded) if args.recorded else RECORDED
    with tempfile.TemporaryDirectory(prefix="ottolab-") as scratch:
        spent_file = Path(scratch) / "spent.json"
        if args.live and not model.key_present():
            say(f"--live was given, but no API key is set on this computer ({model.KEY_ENV}). Only recorded answers are used.")
        build_pack(lab, snap, files[0], version, ids, newest.fingerprint if newest else None, _local_key(data_dir), LOCAL_SIGNER, updates,
                   recorded, args.live, args.limit_nano, spent_file, [check for pack in chain for check in checks_of(pack.pack)])
        say(_spent_line(spent_file, args.limit_nano))
    say("In the app: Settings, Test packs, Check for updates. The pack is shown as made on this computer.")
    return 0


def names_only_our_checker(entries: list[dict]) -> str | None:
    """A research ledger is a file too. Asked to check entries again, Otto's harness starts the verifier an entry
    names, and finds that entry by its id whatever kind it is. So the audit command never asks it to: it runs the
    research side's own pinned checker itself. This is the look before that: does the ledger name anything to run
    but that checker, and does every claim and verdict point at an earlier entry of the right kind? One plain
    phrase, or None."""
    ours = research.file_sha256(research.PINNED / research.CHECKER)
    kinds: dict[str, str] = {}
    for entry in entries:
        record = entry.get("payload") if isinstance(entry, dict) else None
        if not isinstance(record, dict) or record.get("type") != entry.get("kind"):
            return "an entry does not hold a record of its own kind"
        if entry["kind"] == "objective":
            verifier = record.get("verifier")
            if not isinstance(verifier, dict) or set(verifier) != {"kind", "checker", "checker_sha256", "params", "timeout_seconds"} \
                    or verifier["kind"] != "certificate" or verifier["checker"] != research.CHECKER or verifier["checker_sha256"] != ours:
                return "an entry names something to run that is not the research side's own pinned checker"
        elif "verifier" in record:
            return "an entry that is not an objective carries something to run"
        if entry["kind"] == "claim" and kinds.get(str(record.get("objective_id"))) != "objective":
            return "a claim does not point at an earlier objective"
        if entry["kind"] == "verdict" and (kinds.get(str(record.get("objective_id"))) != "objective"
                                           or kinds.get(str(record.get("claim_id"))) != "claim"):
            return "a verdict does not point at an earlier claim and its objective"
        kinds[harness.module("canonical").digest(record)] = entry["kind"]
    return None


def _plain(value: object, limit: int = 300) -> str:
    """Text from a lab folder as it may be printed: printable characters only, and not too long."""
    text = " ".join("".join(ch if ch.isprintable() else "?" for ch in str(value)).split())
    return text if len(text) <= limit else text[:limit] + "..."


def only_regular_files(root: Path) -> str | None:
    """A lab holds folders and regular files, written by Otto's harness and by this build. A link in it could make
    one path read as one file here and as another to a program started in another folder, or make a write land
    somewhere else. One plain phrase about the first thing that is neither, or None."""
    if root.is_symlink():
        return "the lab folder is a link"
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs) + sorted(files):
            path = Path(folder) / name
            if path.is_symlink() or not (path.is_dir() or path.is_file()):
                return f"the lab folder holds something that is not a folder or a regular file ({_plain(path.relative_to(root), 120)})"
    return None


def open_lab(root: Path):
    """The research lab in this folder, opened only when the folder holds nothing but folders and regular files."""
    odd = only_regular_files(root) if root.exists() else None
    if odd is not None:
        raise research.ResearchError(f"{odd}. Nothing was done.")
    return research.open_lab(root)


def run_pinned_checker(params: object, artifact: object) -> str:
    """The research side's own pinned checker of a Claude step record, run on one entry: "accept", "reject", or
    "unavailable" when it gave no usable answer. The program started is always ottolab/pinned/check_model_step.py,
    with a fixed command, an empty folder to work in and a bare environment: never a file from the lab that is audited."""
    try:
        sent = json.dumps({"params": params, "artifact": artifact}).encode("utf-8")
        with tempfile.TemporaryDirectory(prefix="ottolab-check-") as empty:
            done = subprocess.run([sys.executable, "-I", str(research.PINNED / research.CHECKER)], input=sent, capture_output=True,
                                  cwd=empty, timeout=60, env={"PATH": os.environ.get("PATH", "")}, shell=False)
        if done.returncode != 0:
            return "unavailable"
        said = json.loads(done.stdout)
        status = said.get("status") if isinstance(said, dict) else None
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, RecursionError):
        return "unavailable"
    return status if status in ("accept", "reject") else "unavailable"


def audit_problems(root: Path) -> tuple[list[str], int]:
    """(the problems of the research ledger in this folder, how many entries it holds). The folder is read as data:
    nothing in it is started, and nothing is written into it. Otto's harness checks the chain and the records and
    derives every decision again from its runs, without running any verifier; the research side's own pinned
    checker is then run again, by this command, on every entry it once accepted or rejected."""
    if not (root / "ledger.jsonl").is_file() or (root / "ledger.jsonl").is_symlink():
        return ["there is no ledger file in this folder"], 0
    odd = only_regular_files(root)
    if odd is not None:
        return [f"{odd}. Nothing was run"], 0
    lab = harness.module("lab").Lab(str(root))
    entries = list(lab.ledger.entries())            # the harness checks the hash chain as it reads
    foreign = names_only_our_checker(entries)
    if foreign is not None:
        return [f"{foreign}. Nothing was run"], len(entries)
    problems = [str(problem) for problem in lab.audit(reverify=False)]      # never reverify=True on a folder: see names_only_our_checker
    digest = harness.module("canonical").digest
    records = {digest(entry["payload"]): entry["payload"] for entry in entries}
    for entry in entries:
        verdict = entry["payload"]
        if entry["kind"] != "verdict" or verdict.get("status") not in ("accept", "reject"):
            continue
        objective, claim = records[str(verdict.get("objective_id"))], records[str(verdict.get("claim_id"))]
        now = run_pinned_checker(objective["verifier"].get("params", {}), claim.get("artifact"))
        if now == "unavailable":
            problems.append(f"entry {entry.get('seq')} could not be checked again (the pinned checker gave no usable answer)")
        elif now != verdict["status"]:
            problems.append(f"entry {entry.get('seq')}: the stored verdict is {verdict['status']} but the pinned checker now says {now}")
    for name in (research.TRIAL, research.CHECKER):     # the lab's own copies of the two pinned scripts, compared as bytes
        if not (root / name).is_file() or (root / name).read_bytes() != (research.PINNED / name).read_bytes():
            problems.append(f"the lab's {name} is not the one in ottolab/pinned")
    return problems, len(entries)


def audit(args) -> int:
    """Otto's own audit of a research ledger, with the pinned checker run again on every checked entry. An entry that
    could not be checked again is a problem here, never a note beside a pass; so is a folder that can't be read."""
    root = Path(args.lab) if args.lab else LAB
    try:
        problems, height = audit_problems(root)
    except harness.OttoNotInstalled:
        raise
    except Exception as exc:        # a ledger that is not one, a record with a part missing: said plainly, never a traceback
        problems, height = [f"the lab could not be audited ({exc.__class__.__name__}: {exc})"], 0
    for problem in problems:
        say("PROBLEM: " + _plain(problem))
    if not problems:
        say(f"{height} entries; chain intact, every decision re-derived, every pinned checker run again.")
    return 1 if problems else 0


def _dollars(text: str) -> int:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError("the limit is a number of US dollars, for example 2") from None
    if not 0 < value <= 1000:
        raise argparse.ArgumentTypeError("the limit must be more than 0 and at most 1000 US dollars")
    return int(round(value * 100)) * (model.NANO // 100)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ottolab.build", description="Build Otto's signed test packs.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, run in (("ship", ship), ("next", next_pack)):
        one = sub.add_parser(name)
        one.add_argument("--live", action="store_true", help="ask Claude for real (needs a key in ANTHROPIC_API_KEY); default: recorded answers only")
        one.add_argument("--limit", dest="limit_nano", type=_dollars, default=model.DEFAULT_LIMIT_NANO,
                         help="the most this run may spend on Claude, in US dollars (default 2)")
        one.set_defaults(run=run)
        if name == "next":
            one.add_argument("--inbox", required=True, help="a folder holding one snapshot file of new advisories")
            one.add_argument("--data-dir", help="the app's data folder (default: this app's own)")
            one.add_argument("--recorded", help="a folder of recorded answers (default: research/recorded)")
            one.add_argument("--shipped", help="the folder of shipped packs (default: research/packs)")
    check = sub.add_parser("audit")
    check.add_argument("--lab", help="the Otto lab to audit (default: research/lab)")
    check.set_defaults(run=audit)
    args = parser.parse_args(argv)
    if not harness.status().installed:
        say(harness.status().sentence)
        return 1
    try:
        return args.run(args)
    except (research.ResearchError, snapshot.SnapshotError, packs.PackError, harness.OttoNotInstalled) as exc:
        say(f"Stopped: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
