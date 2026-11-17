"""Phase 5c, step 2: Otto's Claude client. Recorded answers replay exactly; a missing one is refused; the live path
is exercised with a stand-in for the network and a made-up key, so no real call is ever made by a test. The key
never appears in a step, an error or a file."""
import json
import random
import time

import pytest

import otto_fuzz
from app.otto import model

FAKE_KEY = "made-up-key-for-tests-0123456789"     # not a real key: nothing in a test ever reaches the API
PROMPT = "Read this advisory and answer with one JSON object."
ANSWER = '{"plain_name": "Blank signature accepted"}'
HOW = "Recorded during the build, not through the API"


def _api(answer=ANSWER, status=200, stop="end_turn", usage=None, served="claude-opus-5-5", calls=None, fail_first=()):
    """A stand-in for the Messages API. `calls` collects every request; `fail_first` answers the first requests with errors."""
    queue = list(fail_first)

    def transport(body, headers, timeout):
        if calls is not None:
            calls.append({"body": json.loads(body), "headers": dict(headers), "timeout": timeout})
        if queue:
            code, text = queue.pop(0)
            if code is OSError:
                raise OSError("no route")
            return code, json.dumps({"type": "error", "error": {"type": "x_error", "message": text}}).encode()
        data = {"model": served, "stop_reason": stop, "content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": answer}],
                "usage": usage or {"input_tokens": 1000, "output_tokens": 200}}
        return status, json.dumps(data).encode()
    return transport


def _live(tmp_path, **more):
    more.setdefault("environ", {model.KEY_ENV: FAKE_KEY})
    more.setdefault("sleep", lambda seconds: None)
    return model.OttoModel(recorded_dirs=(tmp_path,), live=True, **more)


# ---------------------------------------------------------------- recorded answers

def test_a_recorded_answer_replays_exactly_and_makes_no_call(tmp_path):
    path = model.write_recorded(tmp_path, "read_advisory", PROMPT, ANSWER, "2026-11-17T12:00:00Z", HOW)
    assert path.name == f"read_advisory-{model.sha256_text(PROMPT)[:16]}.json"

    def never(*args):
        raise AssertionError("a recorded answer must not reach the network")
    otto = model.OttoModel(recorded_dirs=(tmp_path,), live=False, transport=never, environ={model.KEY_ENV: FAKE_KEY})
    first, second = otto.ask("read_advisory", PROMPT), otto.ask("read_advisory", PROMPT)
    assert first == second and first.answer == ANSWER and first.source == "recorded" and first.model is None
    assert first.prompt_sha256 == model.sha256_text(PROMPT) and first.answer_sha256 == model.sha256_text(ANSWER)
    assert (first.cost_nano_usd, first.input_tokens, first.output_tokens) == (0, 0, 0) and first.how == HOW
    assert otto.budget.spent_nano == 0 and otto.budget.calls == 0
    record = first.record()
    assert record["prompt"] == PROMPT and record["source"] == "recorded" and FAKE_KEY not in json.dumps(record)


def test_a_prompt_with_no_recorded_answer_is_refused_and_nothing_is_made_up(tmp_path):
    model.write_recorded(tmp_path, "read_advisory", PROMPT, ANSWER, "2026-11-17T12:00:00Z", HOW)
    otto = model.OttoModel(recorded_dirs=(tmp_path,), live=False, environ={})
    for step, prompt in (("read_advisory", PROMPT + " "), ("design_test", PROMPT)):   # one character more; another step
        with pytest.raises(model.NoRecordedAnswer) as refused:
            otto.ask(step, prompt)
        assert str(refused.value) == "No recorded answer: this needs Live Otto."
    with pytest.raises(model.ModelError):
        otto.ask("delete_everything", PROMPT)
    with pytest.raises(model.ModelError):
        otto.ask("read_advisory", "")


def test_a_recorded_answer_that_was_changed_is_not_used(tmp_path):
    path = model.write_recorded(tmp_path, "read_advisory", PROMPT, ANSWER, "2026-11-17T12:00:00Z", HOW)
    data = json.loads(path.read_text())
    for field, value in (("answer", '{"plain_name": "Something else"}'), ("prompt", PROMPT + "!"), ("step", "write_fix"),
                         ("schema", "other"), ("extra", 1)):
        path.write_text(json.dumps({**data, field: value}))
        assert model.read_recorded(path) is None or field == "step"
        with pytest.raises(model.NoRecordedAnswer):
            model.OttoModel(recorded_dirs=(tmp_path,), environ={}).ask("read_advisory", PROMPT)
    path.write_text(json.dumps(data))
    assert model.OttoModel(recorded_dirs=(tmp_path,), environ={}).ask("read_advisory", PROMPT).answer == ANSWER


def test_damaged_recorded_answers_are_read_or_left_out(tmp_path):
    """Seeded fuzz on the reader: a damaged copy is either a valid recorded answer or no answer; never an error."""
    path = model.write_recorded(tmp_path, "design_test", PROMPT, ANSWER, "2026-11-17T12:00:00Z", HOW)
    original = path.read_bytes()
    doc = json.loads(original)
    rng = random.Random(20261118)
    kept = 0
    for n in range(300):
        path.write_bytes(otto_fuzz.damage_bytes(rng, original) if n % 2 else json.dumps(otto_fuzz.damage_json(rng, doc)).encode())
        start = time.monotonic()
        got = model.read_recorded(path)
        assert time.monotonic() - start < 2.0
        if got is not None:
            kept += 1
            assert model.sha256_text(got["prompt"]) == got["prompt_sha256"] and model.sha256_text(got["answer"]) == got["answer_sha256"]
    assert kept < 150


# ---------------------------------------------------------------- the Live Otto switch, with no key

def test_live_on_with_no_key_works_on_the_recorded_answers_and_says_so(tmp_path):
    model.write_recorded(tmp_path, "read_advisory", PROMPT, ANSWER, "2026-11-17T12:00:00Z", HOW)

    def never(*args):
        raise AssertionError("no key: no call may be made")
    otto = model.OttoModel(recorded_dirs=(tmp_path,), live=True, transport=never, environ={})
    assert not otto.live_ready and not model.key_present({}) and not model.key_present({model.KEY_ENV: "   "})
    assert otto.ask("read_advisory", PROMPT).source == "recorded"
    with pytest.raises(model.NoRecordedAnswer) as refused:
        otto.ask("read_advisory", "another prompt")
    assert "no API key is set on this computer" in str(refused.value) and model.KEY_ENV in str(refused.value)


# ---------------------------------------------------------------- the live call, with a stand-in for the network

def test_a_live_call_sends_the_prompt_once_and_records_what_came_back(tmp_path):
    calls = []
    otto = _live(tmp_path, transport=_api(calls=calls))
    step = otto.ask("design_test", PROMPT)
    assert step.source == "live" and step.model == "claude-opus-5-5" and step.answer == ANSWER
    assert (step.input_tokens, step.output_tokens) == (1000, 200)
    assert step.cost_nano_usd == 1000 * 5_000 + 200 * 25_000 == otto.budget.spent_nano   # counted at the dearest price that could apply
    sent = calls[0]
    assert len(calls) == 1 and sent["body"]["model"] == "claude-opus-5-5" and sent["body"]["max_tokens"] == model.MAX_OUTPUT_TOKENS
    assert sent["body"]["messages"] == [{"role": "user", "content": PROMPT}] and sent["body"]["output_config"] == {"effort": "high"}
    assert sent["body"]["fallbacks"] == "default" and sent["headers"]["anthropic-beta"] == model.FALLBACK_BETA
    assert sent["headers"]["x-api-key"] == FAKE_KEY and sent["headers"]["anthropic-version"] == model.API_VERSION
    assert "temperature" not in sent["body"] and "top_p" not in sent["body"]
    # the key is in the request header and nowhere else
    assert FAKE_KEY not in json.dumps(step.record()) and FAKE_KEY not in json.dumps(sent["body"]) and FAKE_KEY not in repr(otto)


def test_a_live_answer_is_used_even_when_a_recorded_one_exists(tmp_path):
    model.write_recorded(tmp_path, "read_advisory", PROMPT, ANSWER, "2026-11-17T12:00:00Z", HOW)
    step = _live(tmp_path, transport=_api(answer='{"plain_name": "Live answer"}')).ask("read_advisory", PROMPT)
    assert step.source == "live" and "Live answer" in step.answer


def test_the_spending_limit_stops_the_next_call_before_it_is_sent(tmp_path):
    calls = []
    otto = _live(tmp_path, transport=_api(calls=calls, usage={"input_tokens": 20_000, "output_tokens": 12_000}),
                 budget=model.Budget(limit_nano=model.NANO))        # 1 US dollar for this run
    otto.ask("design_test", PROMPT)                                 # costs 20000*5000 + 12000*25000 nano = $0.40
    assert otto.budget.spent_nano == 400_000_000 and model.dollars(otto.budget.spent_nano) == "$0.40"
    otto.ask("design_test", PROMPT)                                 # $0.80 spent
    with pytest.raises(model.SpendingLimitReached) as stopped:      # the next one could cost about $0.40 more
        otto.ask("design_test", PROMPT)
    assert len(calls) == 2 and "$1.00" in str(stopped.value) and "$0.80" in str(stopped.value) and "was not sent" in str(stopped.value)
    assert otto.budget.calls == 2
    tiny = _live(tmp_path, transport=_api(calls=calls), budget=model.Budget(limit_nano=1000))
    with pytest.raises(model.SpendingLimitReached):
        tiny.ask("read_advisory", PROMPT)
    assert len(calls) == 2


def test_every_attempt_of_a_retried_request_is_counted():
    body = {"model": "claude-opus-5", "usage": {"input_tokens": 100, "output_tokens": 50,
                                                "iterations": [{"type": "message", "input_tokens": 100, "output_tokens": 10},
                                                               {"type": "fallback_message", "input_tokens": 100, "output_tokens": 50}]}}
    assert model.cost_of("claude-opus-5-5", body) == (200, 60, 200 * 5_000 + 60 * 25_000)
    assert model.cost_of("claude-opus-5-5", {"model": "a-model-with-no-price", "usage": {"input_tokens": 1, "output_tokens": 1}})[2] == 8_000 + 40_000
    assert model.cost_of("claude-opus-5-5", {"usage": {"input_tokens": True, "output_tokens": -5}}) == (0, 0, 0)


def test_a_model_without_a_price_is_never_called(tmp_path):
    def never(*args):
        raise AssertionError("no price: no call")
    otto = _live(tmp_path, transport=never, environ={model.KEY_ENV: FAKE_KEY, model.MODEL_ENV: "some-new-model"})
    with pytest.raises(model.LiveCallFailed) as failed:
        otto.ask("read_advisory", PROMPT)
    assert "no price" in str(failed.value)


@pytest.mark.parametrize("fail_first, calls_made", [
    ([(529, "overloaded")], 2), ([(429, "slow down"), (500, "oops")], 3), ([(OSError, "")], 2)])
def test_a_busy_api_is_tried_again(tmp_path, fail_first, calls_made):
    calls, waits = [], []
    step = _live(tmp_path, transport=_api(calls=calls, fail_first=fail_first), sleep=waits.append).ask("read_advisory", PROMPT)
    assert step.answer == ANSWER and len(calls) == calls_made and len(waits) == calls_made - 1


def test_an_account_that_does_not_take_the_fallback_option_is_asked_once_more_without_it(tmp_path):
    calls = []
    refused = (400, "Unexpected value(s) `server-side-fallback-2026-07-01` for the `anthropic-beta` header.")
    step = _live(tmp_path, transport=_api(calls=calls, fail_first=[refused])).ask("read_advisory", PROMPT)
    assert step.answer == ANSWER and len(calls) == 2
    assert "fallbacks" not in calls[1]["body"] and "anthropic-beta" not in calls[1]["headers"]


@pytest.mark.parametrize("fail_first, words", [
    ([(401, f"invalid x-api-key {FAKE_KEY}")], "answered with an error (401"),
    ([(400, "max_tokens: too large")], "answered with an error (400"),
    ([(429, "monthly spend limit reached")], "answered with an error (429"),
    ([(529, "a"), (529, "b"), (529, "c")], "answered with an error (529"),
    ([(OSError, ""), (OSError, ""), (OSError, "")], "could not be reached"),
])
def test_a_failed_call_says_so_plainly_and_never_shows_the_key(tmp_path, fail_first, words):
    otto = _live(tmp_path, transport=_api(fail_first=fail_first))
    with pytest.raises(model.LiveCallFailed) as failed:
        otto.ask("read_advisory", PROMPT)
    assert words in str(failed.value) and FAKE_KEY not in str(failed.value) and "Nothing was changed" in str(failed.value)


def test_a_declined_or_cut_off_or_empty_answer_is_not_used(tmp_path):
    with pytest.raises(model.ModelRefused) as declined:
        _live(tmp_path, transport=_api(stop="refusal", answer="")).ask("write_fix", PROMPT)
    assert "Nothing was made up" in str(declined.value)
    for transport in (_api(stop="max_tokens"), _api(answer="   ")):
        otto = _live(tmp_path, transport=transport)
        with pytest.raises(model.LiveCallFailed):
            otto.ask("write_fix", PROMPT)
        assert otto.budget.spent_nano > 0                      # it was still paid for, and counts against the limit


def test_the_key_is_removed_from_any_text_that_holds_it():
    env = {model.KEY_ENV: FAKE_KEY}
    assert model.redact(f"error: bad key {FAKE_KEY}!", env) == "error: bad key [API key removed]!"
    assert model.redact("nothing to remove", env) == "nothing to remove" and model.redact("x", {}) == "x"
    assert model.key_present(env) is True                      # yes or no, never the key itself


def test_an_answer_must_be_one_json_object():
    assert model.parse_json_answer(' {"a": 1} ') == {"a": 1}
    assert model.parse_json_answer('```json\n{"a": 1}\n```') == {"a": 1} == model.parse_json_answer('```\n{"a": 1}\n```')
    for bad in ("", "Here you go: {\"a\": 1}", "[1]", "```python\nprint(1)\n```", '{"a": 1} and more', "```json\n{\"a\": 1}"):
        with pytest.raises(model.ModelError):
            model.parse_json_answer(bad)


def test_amounts_read_as_dollars():
    assert model.dollars(2 * model.NANO) == "$2.00" and model.dollars(0) == "$0.00"
    assert model.dollars(400_000_000) == "$0.40" and model.dollars(1_500_000) == "$0.002"
