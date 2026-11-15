"""Try one real library by hand, through the same runner and batch driver the app uses (isolated mode only):

    cd backend && .venv/bin/python tools/try_real_library.py openjdk 17.0.2

It prints: what the wrapper says it is, one keygen-sign-verify round trip checked by the app's reference library,
how many of the 484 Wycheproof ECDSA P-256 cases and of our 16 bad-signature cases it gets wrong, the notes its
wrapper passed on, and a short bench next to its slowed control. It decides nothing and stores nothing."""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import reference, runner, vectors                      # noqa: E402
from app.components import component_key                        # noqa: E402
from app.config import load_settings                            # noqa: E402
from app.real_libraries import family_of                        # noqa: E402


def main(name: str, version: str) -> int:
    family = family_of(name, version)
    if family is None:
        print("not a registered real library")
        return 2
    mode = runner.detect_mode(load_settings())
    run = runner.ComponentRunner(mode)
    key = component_key(name, version)
    print("mode:", mode.name, "| image:", mode.real_images.get(family))
    info = run.run_job({"op": "call", "subject": key, "command": "info", "input": {}}, family=family)
    print("info:", info.problem or info.lines[0].get("out") or info.lines[0].get("error"))
    if not info.ok:
        return 1
    trip = run.run_job({"op": "roundtrip", "subject": key, "message": "616263"}, family=family)
    steps = {line.get("step"): line for line in trip.lines}
    print("round trip:", [(s, steps[s].get("error")) for s in steps])
    if "verify" in steps and not steps["verify"].get("error"):
        public, signature = steps["keygen"]["out"]["public_key"], steps["sign"]["out"]["signature"]
        print("  component says valid:", steps["verify"]["out"]["valid"],
              "| reference library says valid:", reference.verify_ecdsa_p256(public, "616263", signature),
              "| public key bytes:", len(public) // 2, "| signature bytes:", len(signature) // 2)
    for label, cases in (("Wycheproof ECDSA P-256", vectors.load_wycheproof("ecdsa_p256").cases),
                         ("our bad-signature list", vectors.load_bad_signatures().cases)):
        job = {"op": "verify_batch", "subjects": [key, "control-accept-all"],
               "cases": [{"id": c.id, "public_key": c.public_key, "message": c.message, "signature": c.signature} for c in cases]}
        result = run.run_job(job, time_limit=300, family=family)
        if not result.ok:
            print(label, "PROBLEM:", result.problem, result.stderr_tail[-300:])
            continue
        mine = result.lines[:len(cases)]
        wrong, no_answer, notes = [], [], collections.Counter()
        for case, line in zip(cases, mine):
            if line.get("note"):
                notes[line["note"]] += 1
            if case.expected == "acceptable":
                continue
            if line.get("valid") is None:
                no_answer.append((case.id, line.get("error")))
            elif line["valid"] != (case.expected == "valid"):
                wrong.append(f"{case.id} ({'accepted' if line['valid'] else 'rejected'}; should be {case.expected})")
        control_wrong = sum(1 for case, line in zip(cases, result.lines[len(cases):]) if case.expected == "invalid" and line.get("valid") is True)
        print(f"{label}: {len(cases)} cases, wrong {len(wrong)}, no answer {len(no_answer)}, took {result.duration_ms / 1000:.0f} s")
        print("  wrong:", ", ".join(wrong) or "none")
        if no_answer:
            print("  no answer:", no_answer[:5])
        print("  notes passed on by the wrapper:", dict(notes) or "none")
        print(f"  control accepted {control_wrong} of {sum(1 for c in cases if c.expected == 'invalid')} invalid cases (must be all)")
    bench = run.run_job({"op": "bench_rounds", "keygen_with": key, "subjects": [key, f"control-slow:{key}"], "rounds": 2,
                         "repeats": 5, "message": "616263"}, time_limit=120, family=family)
    for line in bench.lines:
        out = line.get("out") or {}
        print("bench:", line.get("subject") or ("keygen with " + str(line.get("keygen"))), line.get("error") or "",
              {k: out.get(k) for k in ("sign_ms", "verify_ms", "signature_bytes", "public_key_bytes", "all_verified", "clock") if k in out})
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
