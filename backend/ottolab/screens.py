"""The screen of a piece of asking code, by fixed rules (sandbox research, a prototype).

Asking code is the one small file that knows a library: a refusal list, and `check_signature(public_key, message,
signature)`, which passes a question on to the library and hands the library's own answer back. When Otto (Claude)
writes it, it is data until this screen has let it through.

The rules allow one thing: STRAIGHT-LINE calls into the library on the three inputs.
  - It loads only the library under test (and, for Python, SHA-256 from the standard library, which some libraries
    take as an argument).
  - No `if`, no loop, no comparison, no `try`, no function inside a function, no class, no arithmetic.
  - Nothing that picks one value out of several by something worked out: a part of a value is taken only at a fixed
    place (`public_key[1:33]`), never at a place that depends on anything.
  - Of the language's own, only the plain conversions (bytes to text or hex, bytes to a number). Every other method a
    text, a number or a list has of its own (count, replace, startswith, join, ...) is refused wherever it is named,
    because with those a yes or a no can be put together without the library.
  - Nothing of the library is replaced: a name is given a value once, and only a plain name.
  - No file, network, process, clock, randomness or environment; no name or text that reads a version or a path.
  - No free text: no comment, no description, only short one-word texts (a curve's name, "utf-8"). The code is shown
    to a person as it is, so it holds code only.
  - What comes back is what a call into the library gave back, and that call was given all three inputs (followed
    through the names in between).
  - It is short.
For Python the rules are checked on the parsed program. For JavaScript the standard library has no parser, so they are
checked on the words of the text, which is weaker (there is no following of the three inputs to the answer).

The screen is a filter for honest mistakes and plain tricks. It is NOT a proof that the code decides nothing: a library
may hold a function of its own that the code could misuse, and the screen does not know what the library's functions
do. The weight is carried by the locked container, by the fact that the right answers never reach this code, by the
known-answer check, and by a second version of the code written apart that must agree on every case.

A refusal is one plain sentence (`Refused`); the draft is then not used, and the reason goes back to its author.
"""
from __future__ import annotations

import ast
import hashlib
import io
import re
import tokenize
import warnings
from pathlib import Path

MAX_LINES, MAX_CHARS = 60, 4000
MAX_TEXT_CONSTANT = 24                    # a fixed text is one short word (a curve's name, "utf-8"), nothing longer
MAX_BYTES_CONSTANT = 4
PYTHON_EXTRA_MODULES = {"hashlib": {"sha256"}}       # what may be loaded besides the library: only SHA-256's name
INPUTS = ("public_key", "message", "signature")
# Of Python's own, the code may name two converters, each in one form (int.from_bytes, bytes.fromhex) ...
_OWN_CONVERTERS = {"int": "from_bytes", "bytes": "fromhex"}
# ... and these methods of a value. Every other method or field that a text, a number, a list or a table has of its own
# is refused by name, wherever it stands: with them a yes or a no can be put together without the library.
_OWN_METHODS = frozenset({"decode", "encode", "hex", "from_bytes", "fromhex", "update"})
_PYTHON_OWN = frozenset(name for kind in (str, bytes, bytearray, int, bool, float, complex, list, tuple, dict, set, frozenset, memoryview,
                                          range, slice, object, type(None))
                        for name in dir(kind) if not name.startswith("__")) - _OWN_METHODS
_FORBIDDEN_WORDS = re.compile(r"(?i)(version|__file__|__path__|__name__|__dict__|__class__|__subclasses__|__globals__|__builtins__|environ|"
                              r"argv|platform|hostname|getcwd)")
# Words this app never says about a system, and words of a result. In the code itself (a name it gives, a fixed text) no
# such word stands anywhere, also not inside a longer name. In an author's notes, which are sentences, the words this
# app never says are refused as whole words ("the message is passed on" is plain English and is let through).
NEVER_WORDS = ("secure", "severity", "critical", "score", "passed", "failed", "proven", "verdict", "vulnerab", "exploit", "cve-", "ghsa-")
_NEVER_SAID = re.compile(r"(?i)\b((in)?secure(ly)?|(in)?security|severity|severe|critical(ly)?|scores?|scored|rating|rated|vulnerab\w*|exploit\w*|"
                         r"cve-\S*|ghsa-\S*)\b")
_WORD = re.compile(r"[A-Za-z0-9_-]*")
_OWN_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,23}")
_STATEMENTS = (ast.Import, ast.ImportFrom, ast.Assign, ast.FunctionDef)
_EXPRESSIONS = (ast.Constant, ast.Name, ast.Load, ast.Attribute, ast.Call, ast.keyword, ast.Subscript, ast.Slice, ast.Tuple, ast.List,
                ast.UnaryOp, ast.USub)
_ALLOWED_NODES = (ast.Module, ast.Expr, ast.alias, ast.Store, ast.arguments, ast.arg, ast.Return, *_STATEMENTS, *_EXPRESSIONS)
_WHAT = {"If": "an if", "IfExp": "an if", "For": "a loop", "While": "a loop", "Try": "a try", "Compare": "a comparison",
         "BoolOp": "an and/or", "Lambda": "a lambda", "ClassDef": "a class", "With": "a with", "ListComp": "a loop",
         "GeneratorExp": "a loop", "DictComp": "a loop", "SetComp": "a loop", "Raise": "a raise", "Global": "a global",
         "Nonlocal": "a nonlocal", "Assert": "an assert", "Delete": "a del", "JoinedStr": "a formatted text", "Starred": "a star",
         "Dict": "a dictionary", "Set": "a set", "Await": "an await", "AsyncFunctionDef": "an async function", "BinOp": "arithmetic",
         "AugAssign": "arithmetic", "AnnAssign": "an annotation", "Not": "a not", "Invert": "arithmetic", "UAdd": "arithmetic",
         "NamedExpr": "an assignment inside an expression", "Match": "a match", "Pass": "a pass", "Yield": "a yield"}


class Refused(Exception):
    """The draft is not let through. str(exc) is one plain sentence for its author."""


def fingerprint() -> str:
    """The SHA-256 of these rules, as they stand: kept with every screened draft."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def never_word(text: str) -> str | None:
    """The first word in a sentence that this app never says about a system, or None. For an author's notes."""
    found = _NEVER_SAID.search(text)
    return found.group(0) if found else None


def _code_word(text: str) -> str | None:
    """In a name the code gives or a fixed text it holds: the first piece that this app never says about a system, or
    that words a result, wherever it stands."""
    low = text.lower()
    return next((word for word in NEVER_WORDS if word in low), None)


def _size(source: str) -> None:
    if not isinstance(source, str) or not source.strip():
        raise Refused("The asking code is empty.")
    if len(source) > MAX_CHARS or len(source.splitlines()) > MAX_LINES:
        raise Refused(f"The asking code is longer than {MAX_LINES} lines. It should be a few straight-line calls into the library.")
    if not source.isascii():
        raise Refused("The asking code holds characters outside plain ASCII.")


def _library_name(name: str) -> None:
    """A name of the library that the code loads: any of the library's own, but none that reads a version or a path."""
    if _FORBIDDEN_WORDS.search(name) or name.startswith("__"):
        raise Refused(f"The asking code uses the name {name}. Asking code may not read a version, a path or the environment.")


def _own_name(name: str) -> None:
    """A name the code itself gives (a value's name, or the second name of something it loads): short and plain, and no
    word of a result."""
    _library_name(name)
    word = _code_word(name)
    if word:
        raise Refused(f"The asking code names something with \"{word}\". The code is shown to a person as it is, and it words no result.")
    if not _OWN_NAME.fullmatch(name):
        raise Refused(f"The asking code names a value {name}. A name of its own is short: letters, digits and _.")


def _root(node: ast.AST) -> ast.AST:
    """What a chain of calls, fields and parts starts from: `a` in `a.b(c)[0].d(e)`."""
    while isinstance(node, (ast.Call, ast.Attribute, ast.Subscript)):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node


def check_python(source: str, modules: set[str]) -> None:
    """Raises Refused unless the draft is straight-line calls into the library. `modules`: the top-level names the
    copy's own files can be loaded by."""
    _size(source)
    try:
        with warnings.catch_warnings():              # (a draft's odd escapes are its author's business, not this program's log)
            warnings.simplefilter("ignore")
            tree = ast.parse(source)
            comments = [t for t in tokenize.generate_tokens(io.StringIO(source).readline) if t.type == tokenize.COMMENT]
    except (SyntaxError, ValueError, RecursionError, MemoryError, tokenize.TokenError):
        raise Refused("The asking code is not valid Python.") from None
    if comments:
        raise Refused("The asking code holds a comment. It is shown to a person as it is, so it holds code only.")
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if [f.name for f in functions] != ["check_signature"]:
        raise Refused("The asking code must define exactly one function, check_signature(public_key, message, signature).")
    function = functions[0]
    args = function.args
    if [a.arg for a in args.args] != list(INPUTS) or args.vararg or args.kwarg or args.kwonlyargs or args.defaults \
            or args.posonlyargs or function.decorator_list or function.returns is not None or any(a.annotation is not None for a in args.args):
        raise Refused("check_signature must take exactly public_key, message and signature, with no defaults, no annotations and no decorator.")

    # ---- every piece of the program is one of the few kinds that are let through
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            what = _WHAT.get(type(node).__name__, type(node).__name__)
            raise Refused(f"The asking code holds {what}. Only straight-line calls into the library are let through.")
        if isinstance(node, ast.FunctionDef) and node is not function:
            raise Refused("The asking code holds a function inside a function.")
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node not in tree.body:
            raise Refused("The asking code loads something inside its function.")
        if isinstance(node, ast.Expr) and not isinstance(node.value, ast.Call):
            raise Refused("The asking code holds a text or a value that stands by itself (a description, for one). It is shown to a person "
                          "as it is, so it holds code only.")
        if isinstance(node, ast.UnaryOp) and not (isinstance(node.operand, ast.Constant) and type(node.operand.value) is int):
            raise Refused("The asking code holds arithmetic. Only straight-line calls into the library are let through.")
        if isinstance(node, ast.keyword) and node.arg is None:
            raise Refused("The asking code holds a star. Only straight-line calls into the library are let through.")
        if isinstance(node, ast.Call) and not isinstance(node.func, (ast.Name, ast.Attribute)):
            raise Refused("The asking code calls something it worked out. Only straight-line calls into the library are let through.")
        if isinstance(node, ast.Subscript):
            _fixed_place(node.slice)
        if isinstance(node, ast.Attribute):
            if _FORBIDDEN_WORDS.search(node.attr) or node.attr.startswith("__"):
                raise Refused(f"The asking code reads .{node.attr}. Asking code may not read a version, a path or the environment.")
            if node.attr in _PYTHON_OWN:
                raise Refused(f"The asking code uses .{node.attr}, which is Python's own and not the library's. Of Python's own it may use "
                              f"only {', '.join('.' + m for m in sorted(_OWN_METHODS))}.")
        if isinstance(node, ast.Constant):
            _fixed_value(node.value)

    if not all(isinstance(node, _STATEMENTS) for node in tree.body):
        raise Refused("Outside its function the asking code may only load the library, give OWN_REFUSALS and set up something of the library.")

    # ---- what is loaded: the library, and SHA-256's name
    library_names: set[str] = set()            # names that stand for something of the library
    other_names: set[str] = set()              # sha256
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                raise Refused("The asking code loads something by a relative name.")
            top = node.module.split(".")[0]
            names = [a.name for a in node.names]
            if "*" in names:
                raise Refused("The asking code loads everything of a module at once.")
            if top in PYTHON_EXTRA_MODULES:
                if node.module != top or not set(names) <= PYTHON_EXTRA_MODULES[top] or any(a.asname for a in node.names):
                    raise Refused(f"From {top} the asking code may load only {', '.join(sorted(PYTHON_EXTRA_MODULES[top]))}, under its own name.")
                other_names.update(names)
                continue
            if top not in modules:
                raise Refused(f"The asking code loads {top}, which is not the library under test.")
            for part in (*node.module.split("."), *names):
                _library_name(part)
            for a in node.names:
                if a.asname:
                    _own_name(a.asname)
            library_names.update(a.asname or a.name for a in node.names)
        elif isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                if top not in modules:
                    raise Refused(f"The asking code loads {top}, which is not the library under test.")
                for part in a.name.split("."):
                    _library_name(part)
                if a.asname:
                    _own_name(a.asname)
                library_names.add(a.asname or top)
    taken = library_names | other_names | set(INPUTS) | set(_OWN_CONVERTERS) | {"check_signature"}

    def from_library(value: ast.AST) -> bool:
        """A call into the library, or something of the library read by its name."""
        root = _root(value)
        return isinstance(root, ast.Name) and root.id in library_names

    def give(target: ast.AST, where: str) -> list[str]:
        """The plain names a line gives a value to; each is new."""
        parts = [target] if isinstance(target, ast.Name) else list(target.elts) if isinstance(target, ast.Tuple) and where == "local" else None
        names = [n for n in parts or [] if isinstance(n, ast.Name)]
        if parts is None or len(names) != len(parts):
            raise Refused("The asking code gives a value to something that is not a plain name of its own. Nothing of the library is replaced.")
        for name in names:
            if name.id in taken:
                raise Refused(f"The asking code gives {name.id} a new value. A name is given a value once, and nothing it was handed is replaced.")
            if name.id != "OWN_REFUSALS":
                _own_name(name.id)
            taken.add(name.id)
        return [n.id for n in names]

    # ---- the lines outside the function: the refusal list, and things of the library set up once
    refusals = 0
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            raise Refused("The asking code gives one value to several names at once.")
        (name,) = give(node.targets[0], "module") if isinstance(node.targets[0], ast.Name) else (None,)
        if name is None:
            raise Refused("The asking code gives a value to something that is not a plain name of its own. Nothing of the library is replaced.")
        if name == "OWN_REFUSALS":
            refusals += 1
            if not isinstance(node.value, (ast.Tuple, ast.List)) or not all(isinstance(e, (ast.Name, ast.Attribute)) and from_library(e)
                                                                           for e in node.value.elts):
                raise Refused("OWN_REFUSALS must be a plain list of the library's own error classes (it may be empty).")
        else:
            if not from_library(node.value):
                raise Refused(f"Outside its function the asking code may only set up something of the library; {name} is not that.")
            library_names.add(name)
    if refusals != 1:
        raise Refused("The asking code must give OWN_REFUSALS once: the library's own error classes that mean \"not a valid signature\" (it may be empty).")

    # ---- the function, line by line: which of the three inputs each name was made from
    made_from: dict[str, set[str]] = {name: {name} for name in INPUTS}
    answers: set[str] = set()                  # names that hold what a call into the library gave back

    def carries(value: ast.AST) -> set[str]:
        return set().union(*(made_from.get(n.id, set()) for n in ast.walk(value) if isinstance(n, ast.Name)))

    body = function.body
    if not body or not isinstance(body[-1], ast.Return) or sum(isinstance(n, ast.Return) for n in ast.walk(function)) != 1:
        raise Refused("check_signature must end with its one return, and hold no other.")
    for line in body[:-1]:
        if isinstance(line, ast.Assign):
            if len(line.targets) != 1:
                raise Refused("The asking code gives one value to several names at once.")
            names = give(line.targets[0], "local")
            for name in names:
                made_from[name] = carries(line.value)
            if from_library(line.value):
                library_names.update(names)
                if isinstance(line.value, ast.Call):
                    answers.update(names)
        elif isinstance(line, ast.Expr):               # a call that stands by itself, such as verifier.update(message)
            root = _root(line.value)
            if not from_library(line.value) or not isinstance(root, ast.Name):
                raise Refused("A call that stands by itself must be a call into the library.")
            made_from.setdefault(root.id, set()).update(carries(line.value))
        else:
            raise Refused("Inside check_signature only a value given to a name, a call into the library, and the return are let through.")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in taken:
                raise Refused(f"The asking code uses {node.id}, which it neither loads from the library nor is given.")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in _OWN_CONVERTERS \
                and node.attr != _OWN_CONVERTERS[node.value.id]:
            raise Refused(f"Of {node.value.id} the asking code may use only {node.value.id}.{_OWN_CONVERTERS[node.value.id]}.")
    _converters_only_as_converters(tree)
    answer = body[-1].value
    if not (isinstance(answer, ast.Call) and from_library(answer)) and not (isinstance(answer, ast.Name) and answer.id in answers):
        raise Refused("check_signature must return the library's own answer: what a call into the library gave back, not a fixed value "
                      "and not something the code put together.")
    missing = [name for name in INPUTS if name not in carries(answer)]
    if missing:
        raise Refused(f"The answer check_signature returns was not made from {' or '.join(missing)}, so it can't be the library's answer "
                      "to the question.")


def _converters_only_as_converters(tree: ast.Module) -> None:
    """`int` and `bytes` stand only in `int.from_bytes(...)` and `bytes.fromhex(...)`, never called or passed by themselves."""
    inside = {id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _OWN_CONVERTERS and id(node) not in inside:
            raise Refused(f"Of {node.id} the asking code may use only {node.id}.{_OWN_CONVERTERS[node.id]}.")


def _fixed_place(place: ast.AST) -> None:
    """A part of a value is taken at a fixed place only: value[3], value[1:33], value[-32:]."""
    def fixed(node: ast.AST | None) -> bool:
        if node is None:
            return True
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            node = node.operand
        return isinstance(node, ast.Constant) and type(node.value) is int
    whole = fixed(place) if not isinstance(place, ast.Slice) else (fixed(place.lower) and fixed(place.upper) and place.step is None)
    if not whole:
        raise Refused("The asking code takes a part of a value at a place it worked out. A part is taken only at a fixed place, "
                      "such as public_key[1:33].")


def _fixed_value(value: object) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if len(value) > MAX_TEXT_CONSTANT or not _WORD.fullmatch(value):
            raise Refused("The asking code holds a long fixed value or a text that is more than one plain word. A fixed text is one short "
                          "word of letters, digits, - and _ (a curve's name, \"utf-8\").")
        word = _code_word(value)
        if word:
            raise Refused(f"The asking code holds a text with \"{word}\". The code is shown to a person as it is, and it words no result.")
        if _FORBIDDEN_WORDS.search(value):
            raise Refused("The asking code holds a text that names a version, a path or the environment.")
        return
    if isinstance(value, bytes):
        if len(value) > MAX_BYTES_CONSTANT:
            raise Refused("The asking code holds a long fixed value. It may only pass on what it is given.")
        return
    if type(value) is not int or not -1 <= value <= 255:
        raise Refused("The asking code holds a number of its own. It may only pass on what it is given.")


# ---------------------------------------------------------------- JavaScript: the same rules, on the words of the text

_JS_STRING = re.compile(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"")
_JS_MARK = "§"                       # stands where a quoted text stood; the code is plain ASCII, so it holds none of its own
_JS_PLAIN = re.compile(r"[A-Za-z0-9_$\s(){}\[\];,.:=" + _JS_MARK + r"]*")
_JS_WORDS = frozenset({"const", "return", "new", "function", "module", "load", "true", "false", "null", "Buffer", "checkSignature",
                       "publicKey", "message", "signature"})
# Names that JavaScript's own values have (of every object, function, list, text, number and Buffer). After a dot, or
# as a key, each is refused: with them a yes or a no can be put together, or the program reached, without the library.
_JS_OWN = frozenset("""constructor prototype __proto__ __defineGetter__ __defineSetter__ __lookupGetter__ __lookupSetter__ hasOwnProperty
    isPrototypeOf propertyIsEnumerable valueOf toLocaleString call apply bind caller callee arguments length at concat copyWithin
    entries every fill filter find findIndex findLast findLastIndex flat flatMap forEach includes indexOf join keys lastIndexOf map pop
    push reduce reduceRight reverse shift some sort splice toReversed toSorted toSpliced unshift values with charAt charCodeAt
    codePointAt endsWith localeCompare match matchAll normalize padEnd padStart repeat replace replaceAll search split startsWith
    substring substr toLowerCase toUpperCase trim trimEnd trimStart raw toFixed toExponential toPrecision equals compare copy toJSON
    swap16 swap32 swap64 then catch finally mainModule require env argv execPath binding dlopen version versions platform""".split())
_JS_OWN_PATTERN = re.compile(r"(read|write)[A-Z]\w*")


def check_javascript(source: str, packages: set[str]) -> None:
    """The same rules, on the words of the text (weaker than the Python screen: see the top of this file). `packages`:
    the packages of the copy that `load` may be asked for."""
    _size(source)
    if "`" in source:
        raise Refused("The asking code holds a template text. Only plain quoted names are let through.")
    if _JS_MARK in source:
        raise Refused("The asking code holds characters outside plain ASCII.")
    strings = _JS_STRING.findall(source)
    code = _JS_STRING.sub(_JS_MARK, source)
    if "'" in code or '"' in code or "\\" in code:
        raise Refused("The asking code holds a quoted text this screen could not read.")
    if "//" in code or "/*" in code:
        raise Refused("The asking code holds a comment. It is shown to a person as it is, so it holds code only.")
    for mark, what in (("?", "a condition"), ("&", "an and"), ("|", "an or"), ("==", "a comparison"), ("<", "a comparison"),
                       (">", "a comparison or a function inside a function"), ("!", "a not"), ("+", "arithmetic"), ("-", "arithmetic"),
                       ("*", "arithmetic"), ("/", "arithmetic"), ("%", "arithmetic"), ("^", "arithmetic"), ("~", "arithmetic")):
        if mark in code:
            raise Refused(f"The asking code holds {what} ({mark}). Only straight-line calls into the library are let through.")
    odd = next((ch for ch in code if not _JS_PLAIN.fullmatch(ch)), None)
    if odd is not None:
        raise Refused(f"The asking code holds a sign ({odd}) that straight-line calls into the library have no use for.")
    if re.search(r"[\w$)\]" + _JS_MARK + r"]\s*\[", code):   # a[...]: a name worked out at run time (a plain list, [a, b], is let through)
        raise Refused("The asking code reads a part of something by a computed name (obj[name]). Only straight-line calls into the library "
                      "are let through.")
    # ---- every word: a word of the few the language lends, a name the code declared, or a name of the library after a dot
    declared: set[str] = set()
    for one, several in re.findall(r"\bconst\s+(?:([A-Za-z_$][\w$]*)|\{([^{}]*)\})\s*=", code):
        for name in ([one] if one else [part.strip() for part in several.split(",") if part.strip()]):
            if not re.fullmatch(r"[A-Za-z_$][\w$]*", name) or name in _JS_WORDS or name in _JS_OWN:
                raise Refused(f"The asking code declares {name or 'a name'}, which is not a plain name of its own.")
            word = _code_word(name)
            if word:
                raise Refused(f"The asking code names something with \"{word}\". The code is shown to a person as it is, and it words no result.")
            if name in declared:
                raise Refused(f"The asking code declares {name} twice. A name is given a value once.")
            declared.add(name)
    if len(re.findall(r"\bconst\b", code)) != len(re.findall(r"\bconst\s+(?:[A-Za-z_$][\w$]*|\{[^{}]*\})\s*=", code)):
        raise Refused("The asking code declares something in a form this screen does not read. Use: const name = ...;")
    for found in re.finditer(r"[A-Za-z_$][\w$]*", code):
        word = found.group(0)
        before = code[:found.start()].rstrip()[-1:]
        after = code[found.end():].lstrip()[:1]
        if before == "." or after == ":":                     # a name of the library after a dot, or a key
            if word in _JS_OWN or _JS_OWN_PATTERN.fullmatch(word) or _FORBIDDEN_WORDS.search(word):
                raise Refused(f"The asking code uses \"{word}\", which is JavaScript's own and not the library's. Only straight-line calls "
                              "into the library are let through.")
            continue
        if word not in _JS_WORDS and word not in declared:
            raise Refused(f"The asking code uses \"{word}\", which it neither declares nor is given. Only straight-line calls into the "
                          "library are let through.")
    if re.search(r"\bmodule\b(?!\s*\.\s*exports\s*=\s*function\b)", code) or len(re.findall(r"\bfunction\b", code)) != 1:
        raise Refused("The asking code must export one function, module.exports = function (load) { ... }, and hold no other.")
    if re.search(r"\bBuffer\b(?!\s*\.\s*from\s*\()", code):
        raise Refused("Of Buffer the asking code may use only Buffer.from(...).")
    if len(re.findall(r"\)\s*\{", code)) != 2:
        raise Refused("The asking code holds a function inside a function, or none. It holds the exported function and checkSignature only.")
    # ---- fixed values
    loaded = re.findall(r"\bload\(\s*" + _JS_MARK + r"\s*\)", code)
    asked = [name for _, name in re.findall(r"\bload\(\s*(['\"])([^'\"]*)\1\s*\)", source)]
    for name in asked:
        if name not in packages:
            raise Refused(f"The asking code loads {name}, which is not the library under test or one of its helper libraries.")
    if not asked:
        raise Refused("The asking code never loads the library under test.")
    if len(re.findall(r"\bload\b", code)) != len(loaded) + 1 or len(loaded) != len(asked):       # (+1: the exported function's own input)
        raise Refused("The asking code loads something by a name that is not written out, or passes load on.")
    for text in strings:
        inner = text[1:-1]
        if inner in asked or inner == "use strict":
            continue
        if len(inner) > MAX_TEXT_CONSTANT or not _WORD.fullmatch(inner):
            raise Refused("The asking code holds a long fixed text or one that is more than one plain word. A fixed text is one short word "
                          "of letters, digits, - and _ (a curve's name, 'hex').")
        word = _code_word(inner)
        if word:
            raise Refused(f"The asking code holds a text with \"{word}\". The code is shown to a person as it is, and it words no result.")
        if inner in _JS_OWN or _JS_OWN_PATTERN.fullmatch(inner) or _FORBIDDEN_WORDS.search(inner):
            raise Refused(f"The asking code holds the text \"{inner}\", a name of JavaScript's own.")
    for number in re.findall(r"(?<![A-Za-z_$.\d])\d[\dA-Fa-fxXn_.]*", code):
        if not re.fullmatch(r"\d{1,3}", number) or int(number) > 255:
            raise Refused("The asking code holds a number of its own. It may only pass on what it is given.")
    # ---- the shape: one exported function that gives back the refusal list and checkSignature
    if not re.search(r"\bownRefusals\s*:\s*\[", code) or len(re.findall(r"\bcheckSignature\s*\(\s*publicKey\s*,\s*message\s*,\s*signature\s*\)\s*\{", code)) != 1:
        raise Refused("The asking code must export one function that gives back ownRefusals: [...] and checkSignature(publicKey, message, signature).")
    body = code[code.find("checkSignature"):]
    missing = [name for name in ("publicKey", "message", "signature") if len(re.findall(rf"\b{name}\b", body)) < 2]
    if missing:
        raise Refused(f"checkSignature never passes {' or '.join(missing)} on to the library, so it can't be asking the library the question.")
    returns = re.findall(r"\breturn\b\s*([^;{}]*)", body)
    if len(returns) != 1 or not re.fullmatch(r"[A-Za-z_$][\w$.]*\s*\(.*\)\s*|[A-Za-z_$][\w$]*\s*", returns[0], re.S) \
            or returns[0].strip() in ("true", "false", "null", "publicKey", "message", "signature"):
        raise Refused("checkSignature must return the library's own answer: what a call into the library gave back, not a fixed value.")


def check(language: str, source: str, names: set[str]) -> None:
    if language == "python":
        check_python(source, names)
    elif language == "node":
        check_javascript(source, names)
    else:
        raise Refused("This version screens asking code in Python and JavaScript only.")
