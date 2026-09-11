# Copyright (c) 2025 Jonathan Fontanez
# SPDX-License-Identifier: BUSL-1.1

"""What `@processor` puts in the processor catalog the moment it runs.

A class is discoverable before anything adds it, which is what lets an agent
read an app's effects off a node that has only imported them. No runtime boots
here: registration is a declaration-time fact, and the catalog is per process.
"""

import sys
import types

import pytest

from streamlib import processor
from streamlib._engine import (
    processor_class_import_paths_registered_in_this_process,
)


@processor(execution="manual", description="Declared here and added nowhere")
class DeclaredAndNeverAdded:
    """A processor this suite imports and never puts in a graph."""


@processor(execution="manual")
class DescribedByItsDocstringAlone:
    """What a processor with no description= keyword falls back to."""


@processor(execution="manual", description="The keyword wins")
class DescribedByBothKeywordAndDocstring:
    """The docstring the keyword outranks."""


@processor(execution="manual")
class DescribedByNothingAtAll:
    pass


def _declare_in_a_module_named(module_name: str, class_name: str) -> type:
    """Run a decoration inside a module of the caller's naming.

    A test function's own classes carry `<locals>` in `__qualname__` and are
    unimportable by design, so a module is the only place a decoration gets a
    real import path — and a name per test is what keeps the process-wide
    catalog from carrying one test's registration into another's.
    """
    module = types.ModuleType(module_name)
    sys.modules[module_name] = module
    source = (
        "from streamlib import processor\n"
        "@processor(execution='manual')\n"
        f"class {class_name}:\n"
        "    pass\n"
    )
    exec(compile(source, f"<{module_name}>", "exec"), module.__dict__)  # noqa: S102
    return getattr(module, class_name)


def test_a_decorated_class_is_in_the_catalog_before_anything_adds_it():
    """The whole point: importing the module is the registration."""
    assert (
        "test_declaration_registers:DeclaredAndNeverAdded"
        in processor_class_import_paths_registered_in_this_process()
    )


def test_the_catalog_names_a_class_by_its_import_path():
    """The same string a helper process imports the class back by."""
    declared = _declare_in_a_module_named(
        "a_module_declaring_one_processor", "RegisteredAtDecoration"
    )

    assert declared.__module__ == "a_module_declaring_one_processor"
    assert (
        "a_module_declaring_one_processor:RegisteredAtDecoration"
        in processor_class_import_paths_registered_in_this_process()
    )


def test_a_class_declared_inside_a_function_registers_nothing():
    """It has no import path to be registered under.

    `rt.add` is where a class no interpreter can import is refused, with the
    fix named — moving that refusal to decoration would refuse at import what
    the plan refuses at add.
    """
    catalog_before = set(processor_class_import_paths_registered_in_this_process())

    @processor(execution="manual")
    class DeclaredInsideThisTest:
        pass

    assert "<locals>" in DeclaredInsideThisTest.__qualname__
    assert (
        set(processor_class_import_paths_registered_in_this_process())
        == catalog_before
    )


def test_one_import_path_decorated_twice_is_refused_naming_the_reload():
    """A module loaded twice rebuilds its classes, and both claim one path.

    The registry's duplicate refusal, now met at import where `importlib.reload`
    is the cause a reader can act on.
    """
    module = types.ModuleType("a_module_loaded_twice")
    sys.modules["a_module_loaded_twice"] = module
    source = compile(
        "from streamlib import processor\n"
        "@processor(execution='manual')\n"
        "class DecoratedTwice:\n"
        "    pass\n",
        "<a_module_loaded_twice>",
        "exec",
    )

    exec(source, module.__dict__)  # noqa: S102

    with pytest.raises(ValueError) as refusal:
        exec(source, module.__dict__)  # noqa: S102

    assert "a_module_loaded_twice:DecoratedTwice" in str(refusal.value)
    assert "importlib.reload" in str(refusal.value)


def test_a_refused_second_decoration_leaves_the_first_registration_standing():
    """The registration that arrived first stays; nothing is overwritten."""
    _declare_in_a_module_named("a_module_reloaded_once", "SurvivesTheReload")

    module = sys.modules["a_module_reloaded_once"]
    source = compile(
        "from streamlib import processor\n"
        "@processor(execution='manual')\n"
        "class SurvivesTheReload:\n"
        "    pass\n",
        "<a_module_reloaded_once>",
        "exec",
    )
    with pytest.raises(ValueError):
        exec(source, module.__dict__)  # noqa: S102

    registered = processor_class_import_paths_registered_in_this_process()
    assert (
        registered.count("a_module_reloaded_once:SurvivesTheReload") == 1
    ), "a refused duplicate must neither displace the first nor register beside it"


def test_a_processor_with_no_description_is_described_by_its_docstring():
    """The text an author already wrote, rather than a second place to write it."""
    assert (
        DescribedByItsDocstringAlone.__streamlib_processor_description__
        == "What a processor with no description= keyword falls back to."
    )


def test_an_explicit_description_outranks_the_docstring():
    """The keyword is the deliberate one; the docstring is the fallback."""
    assert (
        DescribedByBothKeywordAndDocstring.__streamlib_processor_description__
        == "The keyword wins"
    )


def test_a_processor_with_neither_is_described_by_the_empty_string():
    """Never `None`: the descriptor's description is a string."""
    assert DescribedByNothingAtAll.__streamlib_processor_description__ == ""
