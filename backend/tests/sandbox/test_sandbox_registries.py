"""Sandbox research: a registry's answer is data, held to the shape the registry documents. Nothing here reaches a
registry: answers are written in the test, or read from the recorded documents in demo/sandbox/registry."""

from __future__ import annotations

import base64
import hashlib
import json
import random
import urllib.error

import pytest

from app.config import DEMO_DIR
from app.sandbox import registries

RECORDED = DEMO_DIR / "sandbox" / "registry"
SHA = "a" * 64


def _pypi(files: list[dict] | None = None, version: str = "1.0.0") -> bytes:
    files = (
        files
        if files is not None
        else [
            {
                "filename": f"thing-{version}.tar.gz",
                "url": f"https://files.pythonhosted.org/packages/x/thing-{version}.tar.gz",
                "packagetype": "sdist",
                "size": 10,
                "digests": {"sha256": SHA},
                "upload_time_iso_8601": "2021-01-02T03:04:05.000000Z",
                "yanked": False,
            }
        ]
    )
    return json.dumps({"info": {"name": "thing"}, "releases": {version: files, "0.9": []}}).encode()


def _npm(integrity: str = "sha512-" + base64.b64encode(b"x" * 64).decode(), scripts: dict | None = None) -> bytes:
    return json.dumps(
        {
            "name": "thing",
            "time": {"1.0.0": "2021-01-02T03:04:05.000Z"},
            "versions": {
                "1.0.0": {
                    "dist": {"tarball": "https://registry.npmjs.org/thing/-/thing-1.0.0.tgz", "integrity": integrity},
                    "dependencies": {"bn.js": "^4.11.9", "bad name!": "1"},
                    "scripts": scripts or {},
                }
            },
        }
    ).encode()


def test_the_recorded_pypi_documents_read_as_the_live_ones_would():
    source = registries.RecordedRegistry(RECORDED)
    raw = source.project("pypi", "starkbank-ecdsa")
    listed = registries.read_versions("pypi", raw)
    assert {"version": "2.0.1", "published": "2021-11-04"} in listed and len(listed) > 15
    release = registries.read_release(
        "pypi", "starkbank-ecdsa", "2.0.1", raw, source.release("pypi", "starkbank-ecdsa", "2.0.1")
    )
    assert (
        release.file.filename == "starkbank-ecdsa-2.0.1.tar.gz" and release.file.kind == "sdist" and release.needs == []
    )
    assert release.file.sha256 == "fe7e36b580da097cc8c0a120e3b7ba335e3901b970a484fd5ce856c026ef7714"
    newest = registries.read_release(
        "pypi", "starkbank-ecdsa", "2.3.1", raw, source.release("pypi", "starkbank-ecdsa", "2.3.1")
    )
    assert newest.file.kind == "wheel"  # a wheel for every computer is taken before the source package


def test_a_version_with_no_file_was_never_published_and_a_withdrawn_file_is_not_used():
    assert [v["version"] for v in registries.read_versions("pypi", _pypi())] == ["1.0.0"]
    yanked = json.loads(_pypi())
    yanked["releases"]["1.0.0"][0]["yanked"] = True
    with pytest.raises(registries.RegistryError, match="no plain-Python file"):
        registries.read_release("pypi", "thing", "1.0.0", json.dumps(yanked).encode(), None)


def test_a_file_is_used_only_if_its_bytes_have_the_registrys_own_fingerprint():
    data = b"the bytes of a package"
    good = registries.File(
        "thing-1.0.0.tar.gz",
        "https://files.pythonhosted.org/x",
        "sdist",
        len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    assert good.holds(data) and not good.holds(data + b"!")
    npm = registries.File(
        "thing-1.0.0.tgz",
        "https://registry.npmjs.org/x",
        "tgz",
        None,
        sha512_base64=base64.b64encode(hashlib.sha512(data).digest()).decode(),
    )
    assert npm.holds(data) and not npm.holds(b"other") and npm.registry_fingerprint.startswith("sha512:")
    assert not registries.File("x.tgz", "https://registry.npmjs.org/x", "tgz", None).holds(
        data
    )  # no fingerprint: never used


def test_npm_gives_the_file_its_fingerprint_and_what_it_needs_and_an_install_script_changes_nothing():
    release = registries.read_release("npm", "thing", "1.0.0", _npm(scripts={"postinstall": "node evil.js"}), None)
    assert release.file.filename == "thing-1.0.0.tgz" and release.published == "2021-01-02"
    assert release.needs == [("bn.js", "^4.11.9")] and release.unreadable_needs == ["bad name!"]
    with pytest.raises(registries.RegistryError, match="no SHA-512 fingerprint"):
        registries.read_release("npm", "thing", "1.0.0", _npm(integrity="sha1-abc"), None)


def test_an_npm_entry_whose_install_scripts_are_not_a_table_reads_the_same():
    """What an entry says about install scripts is never read, whatever is there: a number in that place used to stop
    the read with an error of the program's own, not a refusal."""
    plain = registries.read_release("npm", "thing", "1.0.0", _npm(), None)
    for odd in (7, True, ["postinstall"], "postinstall", None, {"install": 5}):
        doc = json.loads(_npm())
        doc["versions"]["1.0.0"]["scripts"] = odd
        assert registries.read_release("npm", "thing", "1.0.0", json.dumps(doc).encode(), None) == plain


def test_what_a_python_release_needs_is_read_and_a_condition_is_never_guessed():
    release_doc = json.dumps(
        {"info": {"requires_dist": ["six (>=1.9.0)", "gmpy2 ; extra == 'gmpy2'", "typing ; python_version < '3.5'", 7]}}
    ).encode()
    release = registries.read_release("pypi", "thing", "1.0.0", _pypi(), release_doc)
    assert release.needs == [("six", ">=1.9.0")]  # an optional extra is not needed to run the library
    assert len(release.unreadable_needs) == 2  # a condition on the computer, and a line that is no text


def test_only_the_registrys_own_hosts_are_ever_asked():
    asked = []

    def transport(url, timeout, limit):
        asked.append(url)
        return b"{}"

    live = registries.LiveRegistry(transport)
    live.project("pypi", "thing")
    live.project("npm", "@scope/thing")
    assert asked == ["https://pypi.org/pypi/thing/json", "https://registry.npmjs.org/@scope%2Fthing"]
    elsewhere = registries.File("thing-1.0.0.tar.gz", "https://example.com/thing-1.0.0.tar.gz", "sdist", 1, sha256=SHA)
    with pytest.raises(registries.RegistryError, match="not one of the registry's own hosts"):
        live.file("pypi", elsewhere)
    assert len(asked) == 2  # nothing was sent for it
    for bad in ("../etc/passwd", "a b", "", "x" * 200, 7):
        with pytest.raises(registries.RegistryError):
            live.project("pypi", bad)  # type: ignore[arg-type]


def test_a_redirect_is_not_followed_so_only_the_listed_hosts_are_ever_reached(monkeypatch):
    """The separate review of 22 November 2026: the host list held for the first address only, because the reader
    followed redirects. It follows none now, as the advisory source's reader never did; a redirect then comes back as
    the HTTP status it is, which is a stop."""
    import urllib.error
    import urllib.request

    assert (
        registries._NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://elsewhere.example/x") is None
    )
    built: list = []

    class _Opener:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(
                request.full_url, 302, "Found", {}, None
            )  # what a redirect that is not followed comes back as

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: (built.append(handlers), _Opener())[1])
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("urlopen follows redirects"))
    )
    own = registries._http.the_readers_own  # (the suite keeps a refusal in its place: tests/conftest.py)
    with pytest.raises(urllib.error.HTTPError):
        own("https://pypi.org/pypi/thing/json", 5.0, 1000)
    assert built == [(registries._NoRedirect,)]
    live = registries.LiveRegistry(transport=own)
    with pytest.raises(registries.RegistryError, match="answered with an error \\(HTTP 302\\)") as stop:
        live.project("pypi", "thing")
    assert stop.value.later is True


def test_an_answer_that_is_not_what_the_registry_documents_is_a_stop_never_no_such_copy():
    """A go-between's error page, for one: nothing was learned about the package."""
    for raw in (b"<html>502 Bad Gateway</html>", b"[1, 2]", b'{"releases": 7}'):
        with pytest.raises(registries.RegistryError) as stop:
            registries.read_versions("pypi", raw)
        assert stop.value.later is True, raw
    with pytest.raises(registries.RegistryError) as stop:
        registries.read_versions("npm", b'{"versions": []}')
    assert stop.value.later is True
    # (what the registry does say about a package is an answer: settled)
    with pytest.raises(registries.RegistryError, match="lists no plain-Python file") as settled:
        registries.read_release("pypi", "thing", "1.0.0", _pypi(files=[]), None)
    assert settled.value.later is False


def test_could_not_be_reached_is_a_stop_and_not_there_is_an_answer():
    def down(url, timeout, limit):
        raise OSError("no network")

    def missing(url, timeout, limit):
        raise urllib.error.HTTPError(url, 404, "nope", None, None)  # type: ignore[arg-type]

    def broken(url, timeout, limit):
        raise urllib.error.HTTPError(url, 503, "busy", None, None)  # type: ignore[arg-type]

    with pytest.raises(registries.RegistryError) as stop:
        registries.LiveRegistry(down).project("pypi", "thing")
    assert (
        stop.value.later is True and "could not be reached" in str(stop.value) and "no network" not in str(stop.value)
    )
    with pytest.raises(registries.RegistryError) as gone:
        registries.LiveRegistry(missing).project("pypi", "thing")
    assert gone.value.later is False
    with pytest.raises(registries.RegistryError) as busy:
        registries.LiveRegistry(broken).project("pypi", "thing")
    assert busy.value.later is True


def test_the_recorded_folder_is_never_left(tmp_path):
    (tmp_path / "pypi").mkdir()
    (tmp_path / "secret.json").write_text("{}")
    source = registries.RecordedRegistry(tmp_path / "pypi")
    with pytest.raises(registries.RegistryError):
        source.file(
            "pypi", registries.File("../secret.json", "https://files.pythonhosted.org/x", "sdist", 1, sha256=SHA)
        )
    with pytest.raises(registries.RegistryError):
        source.project("pypi", "..")


def test_seeded_fuzz_of_damaged_registry_answers_is_a_plain_refusal_or_a_normal_read():
    rng = random.Random(20261122)
    seeds = [_pypi(), _npm(), (RECORDED / "pypi" / "starkbank-ecdsa.json").read_bytes()]
    for _ in range(600):
        raw = bytearray(rng.choice(seeds))
        for _ in range(rng.randint(1, 6)):
            at = rng.randrange(len(raw))
            how = rng.random()
            if how < 0.4:
                raw[at] = rng.randrange(256)
            elif how < 0.7:
                del raw[at : at + rng.randint(1, 30)]
            else:
                raw[at:at] = bytes(rng.randrange(256) for _ in range(rng.randint(1, 8)))
        for registry in ("pypi", "npm"):
            try:
                listed = registries.read_versions(registry, bytes(raw))
                assert isinstance(listed, list)
                for name in ("1.0.0", "2.0.1"):
                    try:
                        release = registries.read_release(registry, "thing", name, bytes(raw), None)
                        assert release.file.filename and release.version == name
                    except registries.RegistryError as refused:
                        assert str(refused)
            except registries.RegistryError as refused:
                assert str(refused)


def test_no_test_can_reach_a_registry():
    """The suite puts a refusal where the reader's own transport stands (tests/conftest.py): a reader made with no
    stand-in can't be used to reach the network by mistake."""
    from conftest import ReachedTheNetwork

    with pytest.raises(ReachedTheNetwork):
        registries.LiveRegistry().project("pypi", "thing")
