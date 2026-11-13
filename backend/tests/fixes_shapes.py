"""The shapes of the Fixes views, written out by hand from the frontend's types (frontend/src/api.ts, the part
that came from the build contract). `problems(value, SHAPE)` lists every place where a value does not have
exactly the keys and the kinds of value the frontend expects; an empty list means it fits.

A shape is: a type (str, bool, int, NUMBER); Lit(...) for one of a few fixed values; Opt(shape) for "or null";
[shape] for a list; Fixed(n, shape) for a list of exactly n; a dict for an object with exactly those keys; or
By(key, {...}) for an object whose shape depends on one of its values."""
from __future__ import annotations


class Lit:
    def __init__(self, *values):
        self.values = values


class Opt:
    def __init__(self, shape):
        self.shape = shape


class Fixed:
    def __init__(self, length: int, shape):
        self.length, self.shape = length, shape


class By:
    def __init__(self, key: str, shapes: dict):
        self.key, self.shapes = key, shapes


NUMBER = (int, float)


def problems(value, shape, path: str = "view") -> list[str]:
    if isinstance(shape, Opt):
        return [] if value is None else problems(value, shape.shape, path)
    if isinstance(shape, Lit):
        ok = any(value == v and type(value) is type(v) for v in shape.values)
        return [] if ok else [f"{path}: {value!r} is not one of {list(shape.values)}"]
    if isinstance(shape, By):
        if not isinstance(value, dict) or value.get(shape.key) not in shape.shapes:
            return [f"{path}: no known {shape.key!r} in {value!r:.80}"]
        return problems(value, shape.shapes[value[shape.key]], f"{path}[{value[shape.key]}]")
    if isinstance(shape, Fixed):
        if not isinstance(value, list) or len(value) != shape.length:
            return [f"{path}: not a list of {shape.length}"]
        return [p for i, item in enumerate(value) for p in problems(item, shape.shape, f"{path}[{i}]")]
    if isinstance(shape, list):
        if not isinstance(value, list):
            return [f"{path}: not a list ({type(value).__name__})"]
        return [p for i, item in enumerate(value) for p in problems(item, shape[0], f"{path}[{i}]")]
    if isinstance(shape, dict):
        if not isinstance(value, dict):
            return [f"{path}: not an object ({type(value).__name__})"]
        out = [f"{path}: key {key!r} is missing" for key in shape if key not in value]
        out += [f"{path}: key {key!r} is not in the frontend's type" for key in value if key not in shape]
        return out + [p for key in shape if key in value for p in problems(value[key], shape[key], f"{path}.{key}")]
    # a plain type; True and False are not numbers here
    ok = isinstance(value, bool) if shape is bool else (isinstance(value, shape) and not isinstance(value, bool))
    return [] if ok else [f"{path}: {value!r:.60} is not {getattr(shape, '__name__', 'a number')}"]


TONE = Lit("pass", "fail", "neutral", "warn")
KIND = Lit("tls_versions", "certificate", "official_vectors", "bad_signatures", "speed_size", "pq_readiness", "mldsa_compare")
RICH = [{"t": Lit("text", "mono", "tag", "time", "demo"), "v": str}]
STATUS_KEYS = ("not_connected", "proving", "ready", "failed", "waiting", "ready_to_merge", "merged", "text_only")
ACTIONS = ("connect", "run_proof_again", "open_pull_request", "merge", "download_patch", "retest_now")

FIX_LINE = {"fix_id": str, "lead": str, "rest": str, "look": Lit("plain", "pass", "fail", "dashed"), "busy": bool, "button": str}

STRONG_LABEL = {"lead": str, "strong": str, "rest": str}
DIFF_LINE = {"n": int, "mark": Lit(" ", "-", "+"), "text": str}
CHANGE_PART = {"title": str, "why": str, "before_label": STRONG_LABEL, "before": [DIFF_LINE], "after_label": STRONG_LABEL,
               "after": [DIFF_LINE]}
PROOF_CELL = {"label": str, "tone": TONE, "short": str}
PROOF_ROW = {"kind": KIND, "title": str, "before": Opt(PROOF_CELL), "proof": Opt(PROOF_CELL),
             "waiting": Opt({"text": str, "detail": Opt(str), "percent": Opt(NUMBER)}), "control": str,
             "check": {"ok": Opt(bool), "text": str}}
PROOF_TABLE = {"heading": str, "tag": str, "need": str, "columns": Fixed(4, str), "rows": [PROOF_ROW]}
PROOF_VERDICT = {"tone": Lit("pass", "fail"), "title": str, "checks": [{"ok": bool, "text": str}], "shows_title": Opt(str),
                 "shows": [str]}
DETAIL_FACT = {"label": str, "value": RICH, "fingerprint": bool}
RAN_ON = {"title": str, "text": RICH, "fingerprints": [{"label": str, "value": str, "tag": str}], "note": str}
TEXT_SUGGESTION = {
    "intro": [str],
    "warning": Opt({"title": str, "text": str}),
    "where": Opt({"title": str, "note": str, "columns": Fixed(3, str),
                  "rows": [{"place": str, "setting": str, "lead": str, "code": str}], "after": [str]}),
    "options": Opt({"title": str, "items": [{"title": str, "when": str, "steps": [str], "note": str}]}),
    "exact": Opt({"title": str, "note": str, "blocks": [{"place": str, "code": str}]}),
}
SECTION = By("key", {
    "change": {"key": str, "title": str, "line": str, "open": bool, "intro": str, "parts": [CHANGE_PART]},
    "proof": {"key": str, "title": str, "line": str, "open": bool, "intro": str, "tables": [PROOF_TABLE], "verdict": Opt(PROOF_VERDICT)},
    "details": {"key": str, "title": str, "line": str, "open": bool, "facts": [DETAIL_FACT], "note": str, "ran_on": Opt(RAN_ON)},
    "suggestion": {"key": str, "title": str, "line": str, "open": bool, "suggestion": TEXT_SUGGESTION},
})
APPROVERS = {
    "text": Opt(str),
    "options": Opt([{"id": str, "name": str, "note": Opt(str), "demo": bool, "checked": bool}]),
    "rows": Opt([{"id": str, "name": str, "note": Opt(str), "demo": bool, "approved_at": Opt(str), "approved_text": Opt(str),
                  "approve_label": Opt(str), "primary": bool}]),
    "footnote": Opt(str),
}
FIX_DETAIL = {
    "id": str, "kind": Lit("code", "text"), "title": str, "list_source": str, "source": RICH,
    "status": {"key": Lit(*STATUS_KEYS), "word": str, "busy": bool},
    "labels": [str], "is_demo": bool,
    "what": {"label": str, "paragraphs": [RICH], "server_line": Opt(str)},
    "proof": {"state": Lit("none", "not_started", "running", "passed", "failed"), "badge": Opt({"label": str, "tone": TONE}),
              "text": str, "muted": Opt(str)},
    "pull_request": Opt({"title": str, "text": RICH}),
    "approvers": APPROVERS,
    "actions": {"buttons": [{"action": Lit(*ACTIONS), "label": str, "primary": bool, "enabled": bool}], "note": Opt(str)},
    "patch": Opt({"url": str, "filename": str}),
    "merge_dialog": Opt({"title": str, "paragraphs": [RICH], "confirm": str, "cancel": str}),
    "sections": [SECTION], "sections_note": Opt(str),
}
FIXES_VIEW = {"plan_id": int, "is_demo": bool, "title": str, "subline": str, "disclaimer": str, "list_title": str,
              "empty_text": Opt(str), "fixes": [FIX_DETAIL], "busy": bool}

# Evidence Lab (the phase 2 view with the phase 3a additions: fix_line, code_line and the four new column fields)
META = [dict]  # label, value, tag and sometimes time or href: checked where a test needs it
LAB_RESULT = {
    "run_id": int, "component": Opt(str), "mode": Lit("demo", "isolated"), "finished_at": str, "duration_ms": int,
    "code": str, "label": str, "tone": TONE, "summary": str, "short": str,
    "control": {"outcome": Lit("as_expected", "not_as_expected", "errored", "not_run"), "line": str, "text": str},
    "what_happened": [str], "shows_title": str, "shows": [str], "evidence": [dict],
    "run_record": {"title": str, "command": str, "outputs": [{"title": str, "text": str}], "meta": META},
    "locked_test": {"title": str, "fields": [{"label": str, "lines": [str]}], "locked_at": str, "locked_text": str,
                    "fingerprint_label": str, "fingerprint": str, "note": str},
    "fix_title": str, "suggested_fix": Opt(str), "fix_line": Opt(FIX_LINE),
    "reviewed": Opt({"at": str, "text": str}), "research": Opt(dict),
}
ROW_STATUS = {"status": Lit("not_run", "waiting", "running", "done"), "status_text": str,
              "progress": Opt({"text": str, "percent": Opt(NUMBER)})}
LAB_VIEW = {
    "plan_id": int, "is_demo": bool, "view": Lit("results", "before_after"), "subline": RICH, "code_line": Opt(RICH), "disclaimer": str,
    "columns": Opt({"test": str, "before": str, "after": str, "before_note": RICH, "after_note": RICH, "before_heading": str,
                    "after_heading": str}),
    "rows": [{"item_id": int, "kind": KIND, "title": str, "control_line": str, "result": Opt(LAB_RESULT),
              "result_status": Opt(ROW_STATUS), "after": Opt(LAB_RESULT), "after_status": Opt(ROW_STATUS)}],
    "retest": {"can_start": bool, "blocked_reason": Opt(str), "running": bool, "progress_text": Opt(str), "menu_title": str,
               "versions": [{"version": str, "label": str, "tag": str, "note": str}], "menu_note": str},
    "download": {"can_start": bool, "blocked_reason": Opt(str)},
    "busy": bool,
}


def texts(value) -> list[str]:
    """Every piece of text in a view, in order (the keys are not included): what a test of the wording reads."""
    if isinstance(value, dict):
        return [text for item in value.values() for text in texts(item)]
    if isinstance(value, list):
        return [text for item in value for text in texts(item)]
    return [value] if isinstance(value, str) else []


def plain(rich: list[dict]) -> str:
    """A rich text as one plain sentence (a time is left as its ISO text, the Demo data label as its words)."""
    return "".join(part["v"] for part in rich)


def fix(view: dict, fix_id: str) -> dict:
    return next(f for f in view["fixes"] if f["id"] == fix_id)


def section(detail: dict, key: str) -> dict:
    return next(s for s in detail["sections"] if s["key"] == key)
