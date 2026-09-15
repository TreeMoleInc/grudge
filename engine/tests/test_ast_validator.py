import pytest

from grudge_engine.ast_validator import ValidationError, validate

# Adversarial matrix per CLAUDE.md's "stress-test adversarially" instruction.
# Note: two known gaps are deliberately NOT here because AST alone can't catch
# them - `getattr(x, '__' + 'class__')` (dynamic dunder) and `type(name, bases,
# ns)` (3-arg dynamic class creation) are covered instead in
# test_restricted_builtins.py, where they're closed at runtime.
REJECTED_SNIPPETS = [
    "import os",
    "from os import path",
    "__import__('os')",
    "x = object()\nx.__class__",
    "x = object()\nx.__class__.__bases__[0].__subclasses__()",
    "eval('1+1')",
    "exec('import os')",
    "compile('1', '<s>', 'eval')",
    "open('f')",
    "globals()",
    "locals()",
    "vars()",
    "class Foo:\n    pass\nclass Bar:\n    pass\nclass Baz(Foo, Bar):\n    pass",
    "class Meta(type):\n    pass\nclass Foo(metaclass=Meta):\n    pass",
    # Sandbox-escape-class bypasses found in the 2026-09-14 pre-launch review -
    # each one previously slipped past the checks above via an unusual syntax
    # form of the same disallowed thing (see ast_validator.py's comments).
    "from collections import __builtins__ as rb",  # bypassed the dunder-attribute check
    "from collections import *",  # bypassed the import allowlist's per-name check
    "class A:\n    pass\nclass B:\n    pass\nclass Evil(*(A, B)):\n    pass",  # bypassed the multiple-inheritance check
    "class Evil(**{'metaclass': type}):\n    pass",  # bypassed the metaclass check
    "@staticmethod\ndef f():\n    pass",
    "def f():\n    yield 1",
    "def f():\n    yield from range(3)",
    "async def f():\n    pass",
    "async def f():\n    await g()",
    "with open('x') as f:\n    pass",
    "import time",
    "import sys",
    "import socket",
    "import subprocess",
    "import shutil",
    "import pathlib",
    "import threading",
    "import multiprocessing",
    "import asyncio",
    "import pickle",
    "import marshal",
    "import shelve",
    "import ctypes",
    "import numpy",
    "input()",
    "breakpoint()",
]


@pytest.mark.parametrize("snippet", REJECTED_SNIPPETS)
def test_rejects_disallowed_syntax(snippet):
    with pytest.raises(ValidationError):
        validate(snippet)


ALLOWED_SNIPPETS = [
    "import random",
    "import math",
    "import statistics",
    "import collections",
    "import itertools",
    "import functools",
    "import re",
    "import copy",
    "import enum",
    "class Foo:\n    pass\nclass Bar(Foo):\n    pass",
    "x = [i for i in range(10)]",
    "x = (i for i in range(10))",
    "_state = 0\ndef decide(history):\n    global _state\n    _state += 1\n    return COOPERATE",
    (
        "class Base:\n"
        "    def f(self):\n"
        "        return 1\n"
        "class Child(Base):\n"
        "    def f(self):\n"
        "        return super().f()\n"
    ),
    "def decide(history):\n    if not history:\n        return COOPERATE\n    return history[-1].opponent\n",
    "from collections import OrderedDict",  # ordinary from-import of a non-dunder name stays allowed
]


@pytest.mark.parametrize("snippet", ALLOWED_SNIPPETS)
def test_allows_legitimate_syntax(snippet):
    validate(snippet)  # should not raise


def test_syntax_error_raises_syntax_error_not_validation_error():
    with pytest.raises(SyntaxError):
        validate("def f(:\n    pass")


def test_violations_report_every_problem_found_not_just_the_first():
    with pytest.raises(ValidationError) as excinfo:
        validate("import os\nimport sys\neval('1')\n")
    assert len(excinfo.value.violations) >= 3
