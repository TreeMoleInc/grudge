"""The restricted `__builtins__` dict that player code actually executes against.

This is assigned directly as `player_globals["__builtins__"]` — it is NOT a copy of
the real `builtins` module, just an explicit allowlist dict. Anything not present
here is a plain NameError for player code, regardless of what the AST validator
does or doesn't catch syntactically.

Two of these wrappers exist specifically to close gaps the *static* AST validator
can't reliably catch (see ast_validator.py docstring):
  - `getattr`/`hasattr` check the actual runtime string value, catching a
    dynamically-built dunder name like `getattr(x, '__' + 'class__')` that would
    look like an ordinary Call node to the AST layer.
  - `type` rejects more than one argument, blocking `type(name, bases, ns)` dynamic
    class creation while leaving the common 1-arg `type(obj)` usage intact.
`setattr`/`delattr` are simply omitted entirely — no legitimate strategy need.
"""

from __future__ import annotations

import builtins as _real_builtins
import importlib
from collections.abc import Callable
from typing import Any

from grudge_engine.ast_validator import WHITELISTED_MODULES, is_dunder_name

_SAFE_BUILTIN_NAMES = (
    "abs",
    "all",
    "any",
    "bool",
    "bytes",
    "chr",
    "dict",
    "divmod",
    "enumerate",
    "filter",
    "float",
    "format",
    "frozenset",
    "hash",
    "hex",
    "int",
    "isinstance",
    "issubclass",
    "iter",
    "len",
    "list",
    "map",
    "max",
    "min",
    "next",
    "object",
    "oct",
    "ord",
    "pow",
    "range",
    "repr",
    "reversed",
    "round",
    "set",
    "slice",
    "sorted",
    "str",
    "sum",
    "super",
    "tuple",
    "zip",
    # exception types safe to expose/catch
    "ArithmeticError",
    "AssertionError",
    "AttributeError",
    "BaseException",
    "Exception",
    "FloatingPointError",
    "IndexError",
    "KeyError",
    "LookupError",
    "NameError",
    "NotImplementedError",
    "OverflowError",
    "RecursionError",
    "RuntimeError",
    "StopIteration",
    "TypeError",
    "ValueError",
    "ZeroDivisionError",
)


def _safe_getattr(obj: Any, name: str, *default: Any) -> Any:
    if isinstance(name, str) and is_dunder_name(name):
        raise AttributeError(f"access to dunder attribute {name!r} is not allowed")
    return _real_builtins.getattr(obj, name, *default)


def _safe_hasattr(obj: Any, name: str) -> bool:
    if isinstance(name, str) and is_dunder_name(name):
        return False
    return _real_builtins.hasattr(obj, name)


def _safe_type(*args: Any) -> Any:
    if len(args) > 1:
        raise TypeError("dynamic class creation via type(name, bases, namespace) is not allowed")
    return _real_builtins.type(*args)


def _safe_import(
    name: str,
    globals: dict | None = None,
    locals: dict | None = None,
    fromlist: tuple = (),
    level: int = 0,
) -> Any:
    top = name.split(".")[0]
    if level != 0 or top not in WHITELISTED_MODULES:
        raise ImportError(f"import of module '{name}' is not allowed")
    return importlib.import_module(name)


def build_restricted_builtins(print_fn: Callable[..., None]) -> dict[str, Any]:
    """`print_fn` is supplied by the caller (the shim) so this module has no I/O
    concerns of its own — the shim binds it to the real stderr, keeping player
    print() output off the stdout protocol stream (see shim/runtime.py).
    """
    ns: dict[str, Any] = {name: getattr(_real_builtins, name) for name in _SAFE_BUILTIN_NAMES}
    ns["getattr"] = _safe_getattr
    ns["hasattr"] = _safe_hasattr
    ns["type"] = _safe_type
    ns["__import__"] = _safe_import
    ns["print"] = print_fn
    return ns
