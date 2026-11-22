"""The screen of a piece of asking code, by fixed rules (sandbox research, a prototype).

Asking code is the one small file that knows a library: a refusal list, and `check_signature(public_key, message,
signature)`, which passes a question on to the library and hands the library's own answer back. When Otto (Claude)
writes it, it is data until this screen has let it through, and it decides nothing even then.

The rules allow one thing: STRAIGHT-LINE calls into the library on the three inputs. So the code cannot treat one input
differently from another, cannot look at which copy it runs in, and cannot do the checking itself:
  - it loads only the library under test (and, for Python, SHA-256 from the standard library, which some libraries
    take as an argument);
  - no `if`, no loop, no comparison, no `try`, no function inside a function, no class;
  - no file, network, process, clock, randomness or environment; nothing built from text at run time;
  - no name that reads a version or a path; no long fixed value; no arithmetic on numbers;
  - it is short.
For Python the rules are checked on the parsed program. For JavaScript the standard library has no parser, so they are
checked on the words of the text, which is weaker. The screen is a filter for honest mistakes and plain tricks. It is
not a proof: the weight is carried by the locked container, by the fact that the right answers never reach this code,
by the known-answer check, and by a second version of the code written apart that must agree on every case.

A refusal is one plain sentence (`Refused`); the draft is then not used, and the reason goes back to its author.
"""
from __future__ import annotations

import ast
import hashlib
import re
import warnings
from pathlib import Path

MAX_LINES, MAX_CHARS = 60, 4000
MAX_TEXT_CONSTANT = 40                    # a longer fixed text or byte value has no place in asking code
PYTHON_EXTRA_MODULES = {"hashlib": {"sha256"}}       # what may be loaded besides the library: only SHA-256's name
_FORBIDDEN_NAMES = {"open", "exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr", "globals", "locals", "vars", "dir",
                    "input", "print", "breakpoint", "exit", "quit", "help", "memoryview", "type", "super", "object", "id", "hash",
                    "callable", "iter", "next", "map", "filter", "sorted", "reversed", "enumerate", "zip", "range", "pow", "divmod"}
_FORBIDDEN_WORDS = re.compile(r"(?i)(version|__file__|__path__|__name__|__dict__|__class__|__subclasses__|__globals__|__builtins__|environ|"
                              r"argv|platform|hostname|getcwd)")
_ALLOWED_NODES = (ast.Module, ast.Expr, ast.Constant, ast.Import, ast.ImportFrom, ast.alias, ast.Assign, ast.AnnAssign, ast.Name, ast.Load, ast.Store,
                  ast.Tuple, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Call, ast.Attribute, ast.keyword, ast.Subscript, ast.Slice,
                  ast.BinOp, ast.Add, ast.UnaryOp, ast.USub, ast.List)


class Refused(Exception):
    """The draft is not let through. str(exc) is one plain sentence for its author."""


def fingerprint() -> str:
    """The SHA-256 of these rules, as they stand: kept with every screened draft."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _size(source: str) -> None:
    if not isinstance(source, str) or not source.strip():
        raise Refused("The asking code is empty.")
    if len(source) > MAX_CHARS or len(source.splitlines()) > MAX_LINES:
        raise Refused(f"The asking code is longer than {MAX_LINES} lines. It should be a few straight-line calls into the library.")
    if not source.isascii():
        raise Refused("The asking code holds characters outside plain ASCII.")


def check_python(source: str, modules: set[str]) -> None:
    """Raises Refused unless the draft is straight-line calls into the library. `modules`: the top-level names the
    copy's own files can be loaded by."""
    _size(source)
    try:
        with warnings.catch_warnings():              # (a draft's odd escapes are its author's business, not this program's log)
            warnings.simplefilter("ignore")
            tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        raise Refused("The asking code is not valid Python.") from None
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if [f.name for f in functions] != ["check_signature"]:
        raise Refused("The asking code must define exactly one function, check_signature(public_key, message, signature).")
    function = functions[0]
    args = function.args
    if [a.arg for a in args.args] != ["public_key", "message", "signature"] or args.vararg or args.kwarg or args.kwonlyargs or args.defaults \
            or args.posonlyargs or function.decorator_list or function.returns is not None:
        raise Refused("check_signature must take exactly public_key, message and signature, with no defaults and no decorator.")
    assigned = [t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)]
    if "OWN_REFUSALS" not in assigned:
        raise Refused("The asking code must give OWN_REFUSALS, the library's own error classes that mean \"not a valid signature\" (it may be empty).")
    imported: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            what = {"If": "an if", "IfExp": "an if", "For": "a loop", "While": "a loop", "Try": "a try", "Compare": "a comparison",
                    "BoolOp": "an and/or", "Lambda": "a lambda", "ClassDef": "a class", "With": "a with", "ListComp": "a loop",
                    "GeneratorExp": "a loop", "DictComp": "a loop", "SetComp": "a loop", "Raise": "a raise", "Global": "a global",
                    "Assert": "an assert", "Delete": "a del", "JoinedStr": "a formatted text", "Starred": "a star",
                    "Dict": "a dictionary", "Await": "an await", "AsyncFunctionDef": "an async function", "Mod": "arithmetic",
                    "Pow": "arithmetic", "Mult": "arithmetic", "Div": "arithmetic", "FloorDiv": "arithmetic", "BitXor": "arithmetic",
                    "BitAnd": "arithmetic", "BitOr": "arithmetic", "LShift": "arithmetic", "RShift": "arithmetic", "Sub": "arithmetic",
                    "Not": "a not", "Invert": "arithmetic", "NamedExpr": "an assignment inside an expression",
                    "Match": "a match"}.get(type(node).__name__, type(node).__name__)
            raise Refused(f"The asking code holds {what}. Only straight-line calls into the library are let through.")
        if isinstance(node, ast.FunctionDef) and node is not function:
            raise Refused("The asking code holds a function inside a function.")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if node not in tree.body:
                raise Refused("The asking code loads something inside its function.")
            names = [a.name for a in node.names]
            if isinstance(node, ast.ImportFrom):
                if node.level or not node.module:
                    raise Refused("The asking code loads something by a relative name.")
                top = node.module.split(".")[0]
                if top in PYTHON_EXTRA_MODULES:
                    if not set(names) <= PYTHON_EXTRA_MODULES[top]:
                        raise Refused(f"From {top} the asking code may load only {', '.join(sorted(PYTHON_EXTRA_MODULES[top]))}.")
                elif top not in modules:
                    raise Refused(f"The asking code loads {top}, which is not the library under test.")
                if "*" in names:
                    raise Refused("The asking code loads everything of a module at once.")
                imported.update(a.asname or a.name for a in node.names)
            else:
                for a in node.names:
                    top = a.name.split(".")[0]
                    if top not in modules:
                        raise Refused(f"The asking code loads {top}, which is not the library under test.")
                    imported.add((a.asname or a.name).split(".")[0])
        if isinstance(node, ast.Name):
            if node.id in _FORBIDDEN_NAMES or node.id.startswith("__"):
                raise Refused(f"The asking code uses {node.id}, which asking code has no use for.")
            if _FORBIDDEN_WORDS.search(node.id):
                raise Refused(f"The asking code uses the name {node.id}. Asking code may not read a version, a path or the environment.")
        if isinstance(node, ast.Attribute) and (_FORBIDDEN_WORDS.search(node.attr) or node.attr.startswith("__")):
            raise Refused(f"The asking code reads .{node.attr}. Asking code may not read a version, a path or the environment.")
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, (bytes, str)) and len(value) > MAX_TEXT_CONSTANT and node is not _docstring(tree):
                raise Refused("The asking code holds a long fixed value. It may only pass on what it is given.")
            if isinstance(value, bool) or value is None or isinstance(value, (bytes, str)):
                continue
            if not isinstance(value, int) or not -1 <= value <= 255:
                raise Refused("The asking code holds a number of its own. It may only pass on what it is given.")
        if isinstance(node, ast.arg) and node.annotation is not None:
            raise Refused("check_signature's inputs carry no annotations.")
    known = imported | {"public_key", "message", "signature", "OWN_REFUSALS", "check_signature", "True", "False", "None", "bytes", "str", "len",
                        "bool", "int", "tuple"} | set(assigned)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in known and node.id not in _locals(function):
            raise Refused(f"The asking code uses {node.id}, which it neither loads from the library nor is given.")
    returns = [n for n in ast.walk(function) if isinstance(n, ast.Return)]
    if not returns or not all(isinstance(r.value, (ast.Call, ast.Name)) for r in returns):
        raise Refused("check_signature must return the library's own answer: what a call into the library gave back, not a fixed value.")
    used = {n.id for n in ast.walk(function) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    missing = [name for name in ("public_key", "message", "signature") if name not in used]
    if missing:
        raise Refused(f"check_signature never passes {' or '.join(missing)} on to the library, so it can't be asking the library the question.")
    if not any(isinstance(n, ast.Call) for n in ast.walk(function)):
        raise Refused("check_signature never calls the library.")


def _docstring(tree: ast.Module) -> ast.AST | None:
    first = tree.body[0] if tree.body else None
    return first.value if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str) else None


def _locals(function: ast.FunctionDef) -> set[str]:
    return {t.id for n in ast.walk(function) if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)} | \
           {e.id for n in ast.walk(function) if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Tuple)
            for e in t.elts if isinstance(e, ast.Name)}


_JS_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_JS_STRING = re.compile(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"")
_JS_FORBIDDEN = re.compile(
    r"\b(if|else|for|while|do|switch|case|try|catch|finally|throw|class|function\s*\*|async|await|yield|import|require|process|global|globalThis|"
    r"window|eval|Function|Reflect|Proxy|Symbol|setTimeout|setInterval|setImmediate|Date|Math|fetch|XMLHttpRequest|WebSocket|Worker|"
    r"console|fs|child_process|__dirname|__filename|arguments|delete|with|typeof|instanceof|in|BigInt|crypto|version|versions|env|argv|"
    r"platform|constructor|prototype|__proto__)\b")


def check_javascript(source: str, packages: set[str]) -> None:
    """The same rules, on the words of the text (weaker than the Python screen: see the top of this file). `packages`:
    the packages of the copy that `load` may be asked for."""
    _size(source)
    if "`" in source:
        raise Refused("The asking code holds a template text. Only plain quoted names are let through.")
    bare = _JS_COMMENT.sub(" ", source)
    strings = _JS_STRING.findall(bare)
    code = _JS_STRING.sub(" S ", bare)
    if "'" in code or '"' in code or "\\" in code:
        raise Refused("The asking code holds a quoted text this screen could not read.")
    found = _JS_FORBIDDEN.search(code)
    if found:
        raise Refused(f"The asking code uses \"{found.group(0)}\". Only straight-line calls into the library are let through.")
    for mark, what in (("?", "a condition"), ("&&", "an and"), ("||", "an or"), ("==", "a comparison"), ("!=", "a comparison"), ("<", "a comparison"),
                       (">=", "a comparison"), ("%", "arithmetic"), ("**", "arithmetic"), ("^", "arithmetic"), ("~", "arithmetic"),
                       ("!", "a not")):
        if mark in code.replace("=>", "  "):
            raise Refused(f"The asking code holds {what} ({mark}). Only straight-line calls into the library are let through.")
    if re.search(r"[\w$)\]]\s*\[", code):          # a[...]: a name worked out at run time (a plain list, [a, b], is let through)
        raise Refused("The asking code reads a part of something by a computed name. Only straight-line calls into the library are let through.")
    for text in strings:
        inner = text[1:-1]
        if len(inner) > MAX_TEXT_CONSTANT or "\\" in inner:
            raise Refused("The asking code holds a long or escaped fixed text. It may only pass on what it is given.")
    asked = re.findall(r"\bload\(\s*(['\"])([^'\"]*)\1\s*\)", bare)
    for _, name in asked:
        if name not in packages:
            raise Refused(f"The asking code loads {name}, which is not the library under test or one of its helper libraries.")
    if not asked:
        raise Refused("The asking code never loads the library under test.")
    if len(re.findall(r"\bload\(", code)) != len(asked):
        raise Refused("The asking code loads something by a name that is not written out.")
    body = code[code.find("checkSignature"):]
    missing = [name for name in ("publicKey", "message", "signature") if len(re.findall(rf"\b{name}\b", body)) < 2]
    if missing:
        raise Refused(f"checkSignature never passes {' or '.join(missing)} on to the library, so it can't be asking the library the question.")
    if re.search(r"\breturn\s+(true|false|null|undefined|\d+|S)\s*;", body):
        raise Refused("checkSignature must return the library's own answer, not a fixed value.")
    if not re.search(r"module\.exports\s*=", code) or "checkSignature" not in code or "ownRefusals" not in code:
        raise Refused("The asking code must export one function that gives back ownRefusals and checkSignature(publicKey, message, signature).")
    for number in re.findall(r"(?<![A-Za-z_$.\d])\d[\dA-Fa-fxXn_.]*", code):
        if not re.fullmatch(r"\d{1,3}", number) or int(number) > 255:
            raise Refused("The asking code holds a number of its own. It may only pass on what it is given.")


def check(language: str, source: str, names: set[str]) -> None:
    if language == "python":
        check_python(source, names)
    elif language == "node":
        check_javascript(source, names)
    else:
        raise Refused("This version screens asking code in Python and JavaScript only.")
