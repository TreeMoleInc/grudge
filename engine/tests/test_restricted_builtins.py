import pytest

from grudge_engine.restricted_builtins import build_restricted_builtins


def _noop_print(*args, **kwargs):
    pass


@pytest.fixture
def builtins_dict():
    return build_restricted_builtins(_noop_print)


# -- gaps the AST validator can't catch statically, closed here at runtime -------


def test_dynamic_dunder_getattr_is_blocked(builtins_dict):
    getattr_fn = builtins_dict["getattr"]
    with pytest.raises(AttributeError):
        getattr_fn(object(), "__" + "class__")  # built at runtime, not static syntax


def test_static_dunder_getattr_is_blocked_too(builtins_dict):
    getattr_fn = builtins_dict["getattr"]
    with pytest.raises(AttributeError):
        getattr_fn(object(), "__class__")


def test_hasattr_dunder_returns_false_not_true(builtins_dict):
    hasattr_fn = builtins_dict["hasattr"]
    assert hasattr_fn(object(), "__class__") is False


def test_type_three_arg_dynamic_class_creation_is_blocked(builtins_dict):
    type_fn = builtins_dict["type"]
    with pytest.raises(TypeError):
        type_fn("Evil", (object,), {})


# -- normal, legitimate uses must keep working ------------------------------------


def test_getattr_normal_use_still_works(builtins_dict):
    getattr_fn = builtins_dict["getattr"]

    class Foo:
        bar = 1

    assert getattr_fn(Foo(), "bar") == 1
    assert getattr_fn(Foo(), "missing", "default") == "default"


def test_type_one_arg_still_works(builtins_dict):
    assert builtins_dict["type"](42) is int


def test_setattr_delattr_not_present(builtins_dict):
    assert "setattr" not in builtins_dict
    assert "delattr" not in builtins_dict


def test_import_whitelisted_module_succeeds(builtins_dict):
    mod = builtins_dict["__import__"]("math")
    assert mod.__name__ == "math"  # trusted test code, not player code


def test_import_blacklisted_module_blocked(builtins_dict):
    with pytest.raises(ImportError):
        builtins_dict["__import__"]("os")


def test_import_relative_blocked(builtins_dict):
    with pytest.raises(ImportError):
        builtins_dict["__import__"]("mod", level=1)


def test_print_routes_to_supplied_fn():
    calls = []

    def capture(*args, **kwargs):
        calls.append(args)

    d = build_restricted_builtins(capture)
    d["print"]("hello")
    assert calls == [("hello",)]
