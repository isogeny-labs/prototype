"""The engine socket since phase 5c: Otto's wrapper sits in front of the rule engine. Everything but a code change is
passed straight to the rule engine, under the rule engine's own id, so nothing that was graded before moves. These
tests need no Otto: the wrapper is in the socket whether Otto is installed or not."""
from app.engine import research
from app.otto.engine import OttoEngine


def test_the_wrapper_keeps_the_rule_engines_id_and_passes_its_parts_through(lab):
    engine = lab.engine
    assert isinstance(engine, OttoEngine) and isinstance(engine.rules, research.RuleEngine)
    assert engine.engine_id == engine.rules.engine_id == "isogeny.rule-engine/1"
    for part in ("propose_tests", "design_test", "dig_deeper", "review"):
        assert getattr(engine, part) == getattr(engine.rules, part)
    # with nothing of Otto's in the request, a code change is the rule engine's answer, word for word
    request = {"component": {"name": "acme-sign", "version": "9.9.9"}, "failed": [], "files": {}}
    assert engine.propose_change(request) == engine.rules.propose_change(request)


def test_swapping_a_part_of_the_rule_engine_reaches_the_rule_engine(lab, monkeypatch):
    """The rule engine calls its parts on itself, not on the wrapper: a part swapped through the socket must be seen there."""
    original = lab.engine.rules._pq_readiness
    monkeypatch.setattr(lab.engine, "_pq_readiness", lambda claims, target=None: "swapped")
    assert "_pq_readiness" in vars(lab.engine.rules) and "_pq_readiness" not in vars(lab.engine)
    assert lab.engine.rules._pq_readiness([]) == "swapped" == lab.engine._pq_readiness([])
    monkeypatch.undo()
    assert lab.engine.rules._pq_readiness == original


def test_swapping_the_code_change_swaps_the_one_the_app_calls(lab, monkeypatch):
    monkeypatch.setattr(lab.engine, "propose_change", lambda request: "swapped")
    assert lab.engine.propose_change({}) == "swapped"
    assert "propose_change" not in vars(lab.engine.rules)     # the rule engine's own answer is untouched
    monkeypatch.undo()
    assert lab.engine.propose_change.__func__ is OttoEngine.propose_change
