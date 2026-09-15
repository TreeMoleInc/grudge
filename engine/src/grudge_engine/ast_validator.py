"""Static (AST-level) enforcement of the Grudge Python subset. This is the
*secondary* defense layer per CLAUDE.md ("OS-level isolation is primary... Python
subset restriction is secondary, simplicity-oriented") — it exists to give fast,
clear failures and to shrink the attack surface before code ever reaches a
sandboxed process, not as the actual security boundary.

Exact whitelist/blacklist per CLAUDE.md section 2. Two known gaps this module
deliberately does NOT try to close statically (because AST alone can't reliably
detect them) are closed instead at runtime in restricted_builtins.py:
  - `getattr(x, '__' + 'class__')` (dunder name built dynamically at runtime)
  - `type(name, bases, namespace)` (3-arg dynamic class creation)
"""

from __future__ import annotations

import ast

WHITELISTED_MODULES = frozenset(
    {
        "random",
        "math",
        "statistics",
        "collections",
        "itertools",
        "functools",
        "re",
        "copy",
        "enum",
    }
)

# Belt-and-suspenders: these are also simply absent from the restricted builtins
# dict (restricted_builtins.py), so referencing them at runtime is a NameError
# regardless. Rejecting the Call syntax here means the failure happens at
# validation time, before any sandbox process is even spawned.
FORBIDDEN_CALL_NAMES = frozenset(
    {
        "exec",
        "eval",
        "compile",
        "open",
        "__import__",
        "globals",
        "locals",
        "vars",
        "input",
        "breakpoint",
    }
)


def is_dunder_name(name: str) -> bool:
    """Shared by the static check below (visit_Attribute/visit_ImportFrom) and
    the runtime backstop in restricted_builtins.py (_safe_getattr/_safe_hasattr)
    - both layers must agree on exactly what counts as a blocked dunder name, so
    this lives in one place rather than three independent copies of the same
    string check.
    """
    return name.startswith("__") and name.endswith("__")


class ValidationError(Exception):
    """Raised when submitted code uses disallowed syntax. `.violations` holds one
    human-readable message per problem found (validation collects all of them
    rather than stopping at the first, for a better authoring experience).
    """

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__("; ".join(violations))


class _Validator(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[str] = []

    def _fail(self, node: ast.AST, message: str) -> None:
        lineno = getattr(node, "lineno", "?")
        self.violations.append(f"line {lineno}: {message}")

    def _check_decorators(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    ) -> None:
        if node.decorator_list:
            self._fail(node, "decorators are not allowed")

    # -- imports --------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top not in WHITELISTED_MODULES:
                self._fail(node, f"import of module '{alias.name}' is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level != 0:
            self._fail(node, "relative imports are not allowed")
        else:
            top = (node.module or "").split(".")[0]
            if top not in WHITELISTED_MODULES:
                self._fail(node, f"import from module '{node.module}' is not allowed")
        # `from module import name` binds `name` via CPython's IMPORT_FROM
        # bytecode, a direct attribute lookup on the imported module object that
        # never goes through the `getattr` builtin - restricted_builtins.py's
        # _safe_getattr override (the runtime dunder backstop) can't see or
        # block it. Unlike the two gaps that module's docstring says are
        # deliberately left to runtime (a dynamically-*computed* name string),
        # the name here is a literal in the AST, so it belongs in this static
        # check instead - closing it at runtime isn't possible for this
        # specific path. Concretely, without this: `from collections import
        # __builtins__ as rb` reaches the real, unrestricted `builtins` module
        # (every module's namespace carries one), a full sandbox escape.
        for alias in node.names:
            if alias.name == "*":
                self._fail(node, "wildcard imports are not allowed")
            elif is_dunder_name(alias.name):
                self._fail(node, f"import of dunder name '{alias.name}' is not allowed")
        self.generic_visit(node)

    # -- dunder attribute access ------------------------------------------------

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if is_dunder_name(node.attr):
            self._fail(node, f"access to dunder attribute '{node.attr}' is not allowed")
        self.generic_visit(node)

    # -- forbidden calls --------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALL_NAMES:
            self._fail(node, f"call to '{node.func.id}' is not allowed")
        self.generic_visit(node)

    # -- functions / classes -----------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_decorators(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._fail(node, "async functions are not allowed")
        self._check_decorators(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._check_decorators(node)
        # `len(node.bases) > 1` alone misses `class Evil(*(A, B)): ...` - a
        # single Starred expression in the bases list, which unpacks to any
        # number of actual bases at runtime while `node.bases` itself still has
        # length 1. Rejecting any Starred base closes that regardless of count.
        if len(node.bases) > 1 or any(isinstance(base, ast.Starred) for base in node.bases):
            self._fail(node, "multiple inheritance is not allowed")
        for kw in node.keywords:
            # `class Evil(**{"metaclass": M}): ...` supplies a metaclass via
            # dict-unpacking rather than a literal `metaclass=` keyword; such a
            # keyword node has `arg=None` (that's how `**`-unpacking is
            # represented), so the more specific check below would never match
            # it. Rejecting any unpacked keyword outright - the general rule,
            # not a metaclass-specific special case - closes this the same way
            # the Starred-bases check above does for inheritance.
            if kw.arg is None:
                self._fail(node, "unpacked (**) class keyword arguments are not allowed")
            elif kw.arg == "metaclass":
                self._fail(node, "metaclasses are not allowed")
        self.generic_visit(node)

    # -- generators / async / context managers -----------------------------------

    def visit_Yield(self, node: ast.Yield) -> None:
        self._fail(node, "generators (yield) are not allowed")
        self.generic_visit(node)

    def visit_YieldFrom(self, node: ast.YieldFrom) -> None:
        self._fail(node, "generators (yield from) are not allowed")
        self.generic_visit(node)

    def visit_Await(self, node: ast.Await) -> None:
        self._fail(node, "await is not allowed")
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._fail(node, "async with is not allowed")
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._fail(node, "async for is not allowed")
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self._fail(node, "with statements (context managers) are not allowed")
        self.generic_visit(node)


def validate(source: str) -> None:
    """Parse and validate `source` against the Grudge Python subset.

    Raises SyntaxError if `source` isn't valid Python at all, or ValidationError
    (with `.violations` listing every problem found) if it's valid Python but uses
    disallowed syntax. Returns None on success.
    """
    tree = ast.parse(source)
    validator = _Validator()
    validator.visit(tree)
    if validator.violations:
        raise ValidationError(validator.violations)
