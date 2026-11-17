"""Otto's use of Claude (phase 5c): one seam, two sources.

    recorded   the answer stored for exactly this prompt (looked up by the prompt's SHA-256). Tests, screenshots and
               the answer key use only these, so they repeat exactly and need no key.
    live       one HTTPS request to the Messages API, with the key from the ANTHROPIC_API_KEY environment variable.

What comes back is a Step: the full prompt, the full answer, where the answer came from, the model, the tokens and
the cost. A Step is DATA. The caller checks its shape and puts whatever it describes through the same locked path
as everything else; nothing here decides a result, and nothing an answer says is ever run.

The key: read from the environment at the moment of a live call, sent only as that request's header, and never
kept on an object, written to a Step, a log, an error text or a file. Every text that leaves this module passes
through redact(), which removes the key's value should it ever appear (an API error that echoes a header).

The live call uses the Python standard library (urllib): adding Anthropic's official package would be a new
dependency, which needs the owner's OK first (CLAUDE.md, Safety).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

KEY_ENV = "ANTHROPIC_API_KEY"
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2026-10-21"
FALLBACK_BETA = "server-side-fallback-2026-07-01"   # a declined request is retried on the model Anthropic recommends
RECORDED_SCHEMA = "isogeny.recorded-answer/1"
STEPS = ("read_advisory", "design_test", "propose_fix", "write_fix")

# One model for every step, changed in one place (or with EVIDENCE_LAB_OTTO_MODEL).
DEFAULT_MODEL = "claude-opus-5-5"
MODEL_ENV = "EVIDENCE_LAB_OTTO_MODEL"
EFFORT = {"read_advisory": "medium", "design_test": "high", "propose_fix": "medium", "write_fix": "high"}
MAX_OUTPUT_TOKENS = 16000
MAX_PROMPT_BYTES = 400_000
REQUEST_TIMEOUT_SECONDS = 600
RETRY_STATUS = (429, 500, 502, 503, 529)
RETRY_WAITS = (2.0, 8.0)

# The price list: US dollars per million tokens (input, output), as integers of one billionth of a dollar per token,
# so every sum is exact. A model that is not listed here is never called.
NANO = 1_000_000_000
PRICE_SOURCE = {"title": "Anthropic price list", "url": "https://platform.claude.com/docs/en/about-claude/pricing",
                "as_of": "2026-11-03"}
PRICES_NANO_PER_TOKEN = {
    "claude-opus-5-5": (4_000, 20_000),      # $4 / $20 per million tokens
    "claude-sonnet-5-5": (2_000, 10_000),    # $2 / $10
    "claude-haiku-5-5": (500, 2_500),        # $0.10 / $0.50 up to 100K prompt tokens, $0.50 / $2.50 above: the higher pair
    "claude-fable-5-2": (8_000, 40_000),     # $8 / $40
    # models a declined request may be retried on (priced at their own, higher or equal, rates)
    "claude-opus-5": (5_000, 25_000),
    "claude-opus-4-8": (5_000, 25_000),
    "claude-sonnet-5": (3_000, 15_000),
}
FALLBACK_MODELS = ("claude-opus-5", "claude-opus-4-8", "claude-sonnet-5")
DEFAULT_LIMIT_NANO = 2 * NANO               # 2 US dollars per run, until the owner changes it in Settings


class ModelError(Exception):
    """Otto could not get an answer. str(exc) is one plain sentence, safe to show."""


class NoRecordedAnswer(ModelError):
    """This exact prompt has no recorded answer, and Live Otto is off or has no key."""


class SpendingLimitReached(ModelError):
    """The next call could pass the spending limit for this run, so it was not made."""


class LiveCallFailed(ModelError):
    """The live call did not give a usable answer (no key, the network, the API, a cut-off answer)."""


class ModelRefused(ModelError):
    """Claude declined the request. Nothing is made up in its place."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def key_present(environ: dict | None = None) -> bool:
    """Is an API key set on this computer? Says yes or no; never returns the key."""
    return bool(str((environ if environ is not None else os.environ).get(KEY_ENV) or "").strip())


def redact(text: object, environ: dict | None = None) -> str:
    """The text with the API key's value removed, should it be in there."""
    out = str(text)
    key = str((environ if environ is not None else os.environ).get(KEY_ENV) or "").strip()
    if key:
        out = out.replace(key, "[API key removed]")
    return out


def dollars(nano: int) -> str:
    """An amount as the screens and logs show it: US dollars, to the cent (or to a tenth of a cent below one cent)."""
    cents = nano / (NANO / 100)
    return f"${nano / NANO:.2f}" if cents >= 1 or nano == 0 else f"${nano / NANO:.3f}"


def model_name(environ: dict | None = None) -> str:
    return str((environ if environ is not None else os.environ).get(MODEL_ENV) or DEFAULT_MODEL).strip() or DEFAULT_MODEL


@dataclass(frozen=True)
class Step:
    """One Claude step, exactly as it happened. This is what goes into Otto's ledger."""
    step: str
    source: str                 # "recorded" | "live"
    model: str | None           # the model that answered a live call; None for a recorded answer (no API call was made)
    prompt: str
    answer: str
    prompt_sha256: str
    answer_sha256: str
    input_tokens: int
    output_tokens: int
    cost_nano_usd: int
    at: str                     # when a live call was made, or when the answer was recorded
    how: str                    # one plain line: where the answer came from

    def record(self) -> dict:
        """The step as a plain record (for a ledger entry, a pack or the evidence file)."""
        return {"step": self.step, "source": self.source, "model": self.model, "prompt": self.prompt, "answer": self.answer,
                "prompt_sha256": self.prompt_sha256, "answer_sha256": self.answer_sha256, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "cost_nano_usd": self.cost_nano_usd, "at": self.at, "how": self.how}


# ---------------------------------------------------------------- recorded answers

def recorded_path(folder: Path, step: str, prompt_sha256: str) -> Path:
    return folder / f"{step}-{prompt_sha256[:16]}.json"


def read_recorded(path: Path) -> dict | None:
    """One recorded answer, if the file is exactly what it must be; None otherwise (a damaged file is no answer)."""
    try:
        if path.stat().st_size > 4 * MAX_PROMPT_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(data, dict) or data.get("schema") != RECORDED_SCHEMA or set(data) != {
            "schema", "step", "prompt_sha256", "prompt", "answer", "answer_sha256", "recorded"}:
        return None
    recorded = data["recorded"]
    if data["step"] not in STEPS or not isinstance(data["prompt"], str) or not isinstance(data["answer"], str) \
            or not isinstance(recorded, dict) or set(recorded) != {"at", "how"} \
            or not isinstance(recorded["at"], str) or not isinstance(recorded["how"], str) or len(recorded["how"]) > 300:
        return None
    if sha256_text(data["prompt"]) != data["prompt_sha256"] or sha256_text(data["answer"]) != data["answer_sha256"]:
        return None   # the prompt or the answer was changed after it was recorded
    return data


def write_recorded(folder: Path, step: str, prompt: str, answer: str, at: str, how: str) -> Path:
    """Store one answer for one exact prompt (used when the recorded answers are made, never by the app)."""
    if step not in STEPS:
        raise ValueError("unknown step")
    digest = sha256_text(prompt)
    data = {"schema": RECORDED_SCHEMA, "step": step, "prompt_sha256": digest, "prompt": prompt, "answer": answer,
            "answer_sha256": sha256_text(answer), "recorded": {"at": at, "how": how}}
    folder.mkdir(parents=True, exist_ok=True)
    path = recorded_path(folder, step, digest)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- the spending limit of one run

@dataclass
class Budget:
    """What one run may spend, and what it has spent. A run is one research command, or one fix request in the app."""
    limit_nano: int = DEFAULT_LIMIT_NANO
    spent_nano: int = 0
    calls: int = 0

    def worst_case(self, model: str, prompt: str, max_tokens: int = MAX_OUTPUT_TOKENS) -> int:
        """The most one call could cost: every byte of the prompt counted as a token and a full-length answer, at the
        dearest price among this model and the models a declined request may be retried on."""
        price_in, price_out = _top_prices(model)
        return (len(prompt.encode("utf-8")) + 200) * price_in + max_tokens * price_out

    def check(self, model: str, prompt: str) -> None:
        could = self.worst_case(model, prompt)
        if self.spent_nano + could > self.limit_nano:
            raise SpendingLimitReached(
                f"The spending limit for this run is {dollars(self.limit_nano)}. {dollars(self.spent_nano)} is spent, and the next "
                f"request could cost up to {dollars(could)}, so it was not sent. Raise the limit in Settings to go on.")

    def add(self, nano: int) -> None:
        self.spent_nano += int(nano)
        self.calls += 1


def _top_prices(model: str, served: str | None = None) -> tuple[int, int]:
    """The dearest input and output price among the asked model, the model that answered and the fallback models.
    A model that has no price here is counted at the dearest price in the list."""
    names = [model, *FALLBACK_MODELS] + ([served] if served else [])
    known = [PRICES_NANO_PER_TOKEN[name] for name in names if name in PRICES_NANO_PER_TOKEN]
    if served is not None and served not in PRICES_NANO_PER_TOKEN:
        known = list(PRICES_NANO_PER_TOKEN.values())
    return max(p[0] for p in known), max(p[1] for p in known)


def _tokens(part: dict) -> tuple[int, int]:
    def count(name: str) -> int:
        value = part.get(name)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
    return count("input_tokens") + count("cache_creation_input_tokens") + count("cache_read_input_tokens"), count("output_tokens")


def cost_of(requested: str, body: dict) -> tuple[int, int, int]:
    """(input tokens, output tokens, cost) of one answered call, from the usage the API reports. Where a declined
    request was retried on another model, every attempt is counted, at the dearest of the prices that could apply."""
    usage: dict = body["usage"] if isinstance(body.get("usage"), dict) else {}
    served = body.get("model") if isinstance(body.get("model"), str) else None
    price_in, price_out = _top_prices(requested, served)
    iterations = usage.get("iterations")
    attempts = [_tokens(part) for part in iterations if isinstance(part, dict)] if isinstance(iterations, list) else []
    top = _tokens(usage)
    total_in = max(top[0], sum(a[0] for a in attempts))
    total_out = max(top[1], sum(a[1] for a in attempts))
    return total_in, total_out, total_in * price_in + total_out * price_out


# ---------------------------------------------------------------- the live call

def _http_transport(request_body: bytes, headers: dict, timeout: float) -> tuple[int, bytes]:
    """One POST to the Messages API: (HTTP status, response bytes). Raises OSError when there is no answer at all."""
    request = urllib.request.Request(API_URL, data=request_body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:   # noqa: S310 (a fixed https address)
            return response.status, response.read(8 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(64 * 1024)


Transport = Callable[[bytes, dict, float], tuple[int, bytes]]


@dataclass
class OttoModel:
    """Asks Claude one step at a time. `recorded_dirs`: folders of recorded answers, looked through in order.
    `live`: may a live call be made at all (the Live Otto switch, or --live on the research command)? A live call
    also needs a key in the environment. With live off, or with no key, only recorded answers are used."""
    recorded_dirs: tuple[Path, ...] = ()
    live: bool = False
    budget: Budget = field(default_factory=Budget)
    # The function that makes the HTTPS request. None means this module's _http_transport, looked up at the moment of
    # the call (so the test suite can put a stand-in there once, for every client: no test ever reaches the network).
    transport: Transport | None = field(default=None, repr=False)
    # For tests; None means the real environment, read at call time. Never part of the object's printed form.
    environ: dict | None = field(default=None, repr=False)
    sleep: Callable[[float], None] = field(default=time.sleep, repr=False)
    use_fallback: bool = True

    def _env(self) -> dict:
        return self.environ if self.environ is not None else dict(os.environ)

    @property
    def live_ready(self) -> bool:
        return bool(self.live) and key_present(self._env())

    def recorded(self, step: str, prompt: str) -> Step | None:
        digest = sha256_text(prompt)
        for folder in self.recorded_dirs:
            data = read_recorded(recorded_path(Path(folder), step, digest))
            if data is not None and data["step"] == step and data["prompt_sha256"] == digest and data["prompt"] == prompt:
                return Step(step=step, source="recorded", model=None, prompt=prompt, answer=data["answer"], prompt_sha256=digest,
                            answer_sha256=data["answer_sha256"], input_tokens=0, output_tokens=0, cost_nano_usd=0,
                            at=data["recorded"]["at"], how=data["recorded"]["how"])
        return None

    def ask(self, step: str, prompt: str) -> Step:
        """The answer to this exact prompt. Live Otto on and a key present: a live call (within the spending limit).
        Otherwise the recorded answer, or NoRecordedAnswer: nothing is made up."""
        if step not in STEPS:
            raise ModelError("That is not a step Otto knows.")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
            raise ModelError("The request for Claude is empty or too long to send.")
        if self.live_ready:
            return self._live(step, prompt)
        found = self.recorded(step, prompt)
        if found is None:
            raise NoRecordedAnswer("No recorded answer: this needs Live Otto." if not self.live else
                                   f"No recorded answer, and no API key is set on this computer ({KEY_ENV}): this needs Live Otto with a key.")
        return found

    def _live(self, step: str, prompt: str) -> Step:
        env = self._env()
        model = model_name(env)
        if model not in PRICES_NANO_PER_TOKEN:
            raise LiveCallFailed(f"The model named in {MODEL_ENV} has no price in this version's price list, so it is not called.")
        self.budget.check(model, prompt)
        body = {"model": model, "max_tokens": MAX_OUTPUT_TOKENS, "output_config": {"effort": EFFORT[step]},
                "messages": [{"role": "user", "content": prompt}]}
        headers = {"content-type": "application/json", "anthropic-version": API_VERSION, "x-api-key": str(env.get(KEY_ENV) or "").strip()}
        fallback = self.use_fallback
        status, raw, waits = 0, b"", list(RETRY_WAITS)
        while True:
            send = dict(body, fallbacks="default") if fallback else body
            send_headers = dict(headers, **({"anthropic-beta": FALLBACK_BETA} if fallback else {}))
            try:
                status, raw = (self.transport or _http_transport)(json.dumps(send).encode("utf-8"), send_headers, REQUEST_TIMEOUT_SECONDS)
            except OSError as exc:
                if waits:
                    self.sleep(waits.pop(0))
                    continue
                raise LiveCallFailed(f"Claude could not be reached ({exc.__class__.__name__}). Nothing was changed.") from None
            if status == 400 and fallback and b"fallback" in raw.lower():
                fallback = False        # this account or model does not take the fallback option: ask once more without it
                continue
            if status in RETRY_STATUS and waits and not _spend_cap(raw):
                self.sleep(waits.pop(0))
                continue
            break
        at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        if status != 200:
            raise LiveCallFailed(redact(f"Claude's API answered with an error ({status}: {_error_words(raw)}). Nothing was changed.", env))
        try:
            data = json.loads(raw)
        except ValueError:
            raise LiveCallFailed("Claude's API gave an answer that could not be read. Nothing was changed.") from None
        if not isinstance(data, dict):
            raise LiveCallFailed("Claude's API gave an answer that could not be read. Nothing was changed.")
        tokens_in, tokens_out, cost = cost_of(model, data)
        self.budget.add(cost)           # a declined or cut-off answer was still paid for
        if data.get("stop_reason") == "refusal":
            raise ModelRefused("Claude declined this request, so Otto has no answer for it. Nothing was made up in its place.")
        if data.get("stop_reason") == "max_tokens":
            raise LiveCallFailed("Claude's answer was cut off before it ended, so it is not used. Nothing was changed.")
        blocks: list = data["content"] if isinstance(data.get("content"), list) else []
        answer = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))
        if not answer.strip():
            raise LiveCallFailed("Claude's answer held no text, so it is not used. Nothing was changed.")
        answer = redact(answer, env)
        served = data.get("model") if isinstance(data.get("model"), str) else model
        return Step(step=step, source="live", model=served, prompt=prompt, answer=answer, prompt_sha256=sha256_text(prompt),
                    answer_sha256=sha256_text(answer), input_tokens=tokens_in, output_tokens=tokens_out, cost_nano_usd=cost, at=at,
                    how=f"Live: Claude ({served}), through the API key on this computer")


def _spend_cap(raw: bytes) -> bool:
    """A 429 that says the account's own monthly spending cap is reached is not worth another try."""
    return b"spend" in raw.lower()


def _error_words(raw: bytes) -> str:
    try:
        data = json.loads(raw)
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            return f"{str(error.get('type'))[:60]}: {str(error.get('message'))[:300]}"
    except ValueError:
        pass
    return "no readable error text"


def parse_json_answer(answer: str) -> dict:
    """The one JSON object an answer must be. Accepts it bare or inside one ```json fence; anything else is refused."""
    text = answer.strip()
    if text.startswith("```"):
        first_line, _, rest = text.partition("\n")
        if first_line.strip() not in ("```", "```json") or not rest.rstrip().endswith("```"):
            raise ModelError("Claude's answer is not the JSON object that was asked for, so it is not used.")
        text = rest.rstrip()[:-3].strip()
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        raise ModelError("Claude's answer is not the JSON object that was asked for, so it is not used.") from None
    if not isinstance(data, dict):
        raise ModelError("Claude's answer is not the JSON object that was asked for, so it is not used.")
    return data
