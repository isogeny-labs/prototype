"""Sandbox research: a run that was made on a sandbox copy says so by its own record.

The separate review of 22 November 2026: with the switch turned off again a sandbox copy is no longer listed, and a
stored run on one was then tagged "demo", on screen and in the signed report; with the switch on, the report said "real
software" and never "sandbox copy". The tag is now read from the stored run itself (the command it ran names its
image), so it reads the same whatever the switch says today."""
from __future__ import annotations

from sandbox_fixtures import copy_set

from app.present import real

IMAGE = copy_set("a")["image"]["tag"]
COMPONENT = {"name": "starkbank-ecdsa", "version": "2.0.0"}
RUN = {"component": COMPONENT, "mode": "isolated",
       "raw": {"batch": {"command": f"docker run --rm -i --pull never --network none {IMAGE} /usr/local/bin/python asking.py"}}}


def test_a_stored_run_names_its_sandbox_image_and_that_is_what_the_tag_is_read_from():
    assert real.ran_on_sandbox_copy(RUN) and not real.ran_on_sandbox_copy({**RUN, "raw": {"batch": {"command": "docker run evidence-lab-real-elliptic:abc"}}})
    assert not real.ran_on_sandbox_copy(None) and not real.ran_on_sandbox_copy({"component": COMPONENT})
    # no store of copies is registered here: the app lists no sandbox copy at all, as with the switch off
    assert real.is_real(COMPONENT) is False                      # (asked about a component alone, it is not listed)
    assert real.is_real(COMPONENT, RUN) is True                  # the stored run says what it ran on
    assert real.tag_of(COMPONENT, RUN) == "sandbox copy" and real.tag_of(COMPONENT, RUN) == real.SANDBOX_TAG
    words = real.code_words("starkbank-ecdsa", "2.0.0", sandbox=True)
    assert words.startswith("starkbank-ecdsa 2.0.0 (sandbox copy): the library's own files from its public package registry")


def test_a_run_on_a_pinned_library_or_a_demo_component_is_tagged_as_before():
    pinned = {"name": "elliptic", "version": "6.5.6"}
    run = {"component": pinned, "raw": {"batch": {"command": "docker run evidence-lab-real-elliptic:d60d2f0de37432d6 node"}}}
    assert real.is_real(pinned, run) and real.tag_of(pinned, run) == real.REAL_TAG
    demo = {"name": "acme-sign", "version": "1.4.2"}
    assert not real.is_real(demo, {"component": demo, "raw": {"command": "python acme_sign.py"}})


def test_the_result_and_the_report_say_sandbox_copy_with_the_switch_off():
    """Through the words of a result, with nothing listed: the Component and Code lines are tagged sandbox copy, never
    demo, and the report's line says so too."""
    import inspect

    from app.evidence import export
    from app.present import results
    source = inspect.getsource(results.lab_result)
    assert "present_real.is_real(run.get(\"component\"), run)" in source and "\"sandbox_copy\": bool(on_sandbox_copy)" in source
    line = inspect.getsource(export)
    assert "'sandbox copy' if r.get('sandbox_copy') else 'real software' if r.get('real') else 'demo'" in line
    assert '**({"sandbox_copy": True} if r.get("sandbox_copy") else {})' in line
