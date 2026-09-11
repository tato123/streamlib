# Copyright (c) 2025 Jonathan Fontanez
# SPDX-License-Identifier: BUSL-1.1

"""A processor's config class: how it is declared, derived and constructed.

Three seams, none of which boots an engine. `@processor` reads the config class
off `__init__` and refuses every other signature; the deriver turns that class
into the JSON Schema the catalog publishes; and the hosting module constructs
the class from the mapping `rt.add` recorded, which is what a helper process
does on the compile thread.
"""

import dataclasses
from typing import Annotated, Any, Literal, Optional, TypedDict

import pydantic
import pytest

from streamlib import processor
from streamlib._processor_hosting import (
    apply_configuration,
    construct_processor_instance,
)

# ---------------------------------------------------------------------------
# The config classes the cases below are declared against
# ---------------------------------------------------------------------------


class BlurConfigTypedDict(TypedDict):
    """Admits anything at run time — the loosest dial an author can pick."""

    width: int
    label: Annotated[str, "What to call this blur."]


class PartialConfigTypedDict(TypedDict, total=False):
    width: int


@dataclasses.dataclass
class BlurConfigDataclass:
    """Refuses an unknown key but not a mistyped value."""

    width: int
    label: str = "unlabelled"
    tags: "list[str]" = dataclasses.field(default_factory=list)
    quality: Literal["fast", "good"] = "fast"
    fallback: Optional[str] = None
    derived: int = dataclasses.field(init=False, default=7)


class BlurConfigModel(pydantic.BaseModel):
    """Validates values — the strictest dial, and it carries its own schema."""

    width: int
    label: str = "unlabelled"


@dataclasses.dataclass
class NestedConfig:
    inner: BlurConfigDataclass
    count: int = 0


# ---------------------------------------------------------------------------
# Declaration: which `__init__` signatures name a config class
# ---------------------------------------------------------------------------


def test_an_annotated_config_parameter_names_the_config_class():
    @processor(execution="manual")
    class Blur:
        def __init__(self, config: BlurConfigDataclass) -> None:
            self.config = config

    assert Blur.__streamlib_processor_config_class__ is BlurConfigDataclass


def test_an_init_taking_nothing_beyond_self_declares_no_config():
    @processor(execution="manual")
    class Counter:
        def __init__(self) -> None:
            self.seen = 0

    assert Counter.__streamlib_processor_config_class__ is None


def test_a_class_defining_no_init_at_all_declares_no_config():
    """`object.__init__` reports `(self, /, *args, **kwargs)`.

    Read literally that is a variadic signature, which the rule below refuses —
    so the commonest class in the suite would be refused for a signature its
    author never wrote.
    """

    @processor(execution="manual")
    class Bare:
        pass

    assert Bare.__streamlib_processor_config_class__ is None


def test_a_keyword_parameter_is_refused_with_the_fix_named():
    with pytest.raises(TypeError) as refusal:

        @processor(execution="manual")
        class Blur:
            def __init__(self, width: int = 1) -> None:
                self.width = width

    assert "Blur" in str(refusal.value)
    assert "`width`" in str(refusal.value)
    assert "must be named `config`" in str(refusal.value)
    assert "BlurConfig" in str(refusal.value), "the fix must show the shape wanted"


def test_several_parameters_are_refused_and_all_of_them_named():
    with pytest.raises(TypeError, match="width, height"):

        @processor(execution="manual")
        class Blur:
            def __init__(self, width: int, height: int) -> None:
                self.size = (width, height)


def test_an_unannotated_config_parameter_is_refused():
    with pytest.raises(TypeError, match="with no annotation"):

        @processor(execution="manual")
        class Blur:
            def __init__(self, config) -> None:  # noqa: ANN001
                self.config = config


def test_a_config_annotated_as_a_parameterized_generic_is_refused():
    """`dict[str, Any]` is a mapping, not a class the helper can construct.

    The guard is on the annotation's origin rather than on `isinstance(_, type)`
    because on Python 3.10 — the wheel's floor — `isinstance(dict[str, Any],
    type)` is still True.
    """
    with pytest.raises(TypeError, match="is not a class"):

        @processor(execution="manual")
        class Blur:
            def __init__(self, config: "dict[str, Any]") -> None:
                self.config = config


def test_keyword_variadic_configuration_is_refused_by_name():
    with pytest.raises(TypeError, match=r"\*\*config"):

        @processor(execution="manual")
        class Blur:
            def __init__(self, **config: Any) -> None:
                self.config = config


def test_a_positional_only_config_is_refused_because_the_helper_passes_it_by_name():
    with pytest.raises(TypeError, match="positionally only"):

        @processor(execution="manual")
        class Blur:
            def __init__(self, config: BlurConfigDataclass, /) -> None:
                self.config = config


def test_an_unresolvable_annotation_is_refused_where_the_author_can_see_it():
    with pytest.raises(TypeError, match="cannot be resolved"):

        @processor(execution="manual")
        class Blur:
            def __init__(
                self,
                config: "NeverImported",  # noqa: F821  # pyright: ignore[reportUndefinedVariable]
            ) -> None:
                self.config = config


# ---------------------------------------------------------------------------
# Derivation: the document each kind of config class publishes
# ---------------------------------------------------------------------------


def schema_of(config_class: "Optional[type]") -> "dict[str, Any]":
    """The document a processor taking `config_class` publishes."""
    if config_class is None:

        @processor(execution="manual")
        class SubjectDeclaringNoConfig:
            def __init__(self) -> None:
                self.seen = 0

        return SubjectDeclaringNoConfig.__streamlib_processor_config_schema__

    @processor(execution="manual")
    class SubjectTakingAConfigClass:
        def __init__(self, config: config_class) -> None:  # type: ignore[valid-type]
            self.config = config

    return SubjectTakingAConfigClass.__streamlib_processor_config_schema__


def test_a_typed_dict_yields_its_annotations_and_its_required_keys():
    document = schema_of(BlurConfigTypedDict)

    assert document["type"] == "object"
    assert document["properties"]["width"] == {"type": "integer"}
    assert document["properties"]["label"] == {
        "type": "string",
        "description": "What to call this blur.",
    }
    assert document["required"] == ["width", "label"]
    # A TypedDict admits an unknown key at run time, so claiming otherwise
    # would be a promise the class does not keep.
    assert "additionalProperties" not in document


def test_a_total_false_typed_dict_requires_nothing():
    assert "required" not in schema_of(PartialConfigTypedDict)


def test_a_dataclass_yields_its_init_fields_defaults_and_required_names():
    document = schema_of(BlurConfigDataclass)

    assert document["properties"]["width"] == {"type": "integer"}
    assert document["properties"]["label"] == {"type": "string", "default": "unlabelled"}
    assert document["properties"]["quality"] == {
        "enum": ["fast", "good"],
        "default": "fast",
    }
    assert document["properties"]["fallback"] == {
        "anyOf": [{"type": "string"}, {"type": "null"}],
        "default": None,
    }
    assert document["required"] == ["width"]
    # A dataclass raises on an unknown key, so the document may say so.
    assert document["additionalProperties"] is False


def test_a_field_with_a_default_factory_is_optional_and_carries_no_default():
    """A factory's result is not a default — calling one to document it would
    run the author's code at import."""
    tags = schema_of(BlurConfigDataclass)["properties"]["tags"]

    assert tags == {"type": "array", "items": {"type": "string"}}
    assert "tags" not in schema_of(BlurConfigDataclass)["required"]


def test_an_init_false_field_is_not_documented_because_it_is_not_an_input():
    assert "derived" not in schema_of(BlurConfigDataclass)["properties"]


def test_a_model_contributes_its_own_document_without_the_two_catalog_keys():
    document = schema_of(BlurConfigModel)

    assert document["properties"]["width"]["type"] == "integer"
    assert document["properties"]["label"]["default"] == "unlabelled"
    assert document["required"] == ["width"]
    assert "$schema" not in document
    assert "title" not in document, "the catalog names a processor, not its config type"


def test_a_nested_config_class_is_inlined_rather_than_referenced():
    """Nothing here emits a `$ref`, so no document carries a `$defs` for one to
    point into."""
    document = schema_of(NestedConfig)

    assert document["properties"]["inner"]["properties"]["width"] == {"type": "integer"}
    assert "$defs" not in document
    assert "$ref" not in repr(document)


def test_an_annotation_the_deriver_does_not_know_renders_as_an_open_schema():
    """A config class is worth publishing long before every type in it is
    describable."""

    @dataclasses.dataclass
    class WithAnOpaqueField:
        handle: complex
        width: int = 2

    document = schema_of(WithAnOpaqueField)

    assert document["properties"]["handle"] == {}
    assert document["properties"]["width"] == {"type": "integer", "default": 2}
    assert document["required"] == ["handle"], "an opaque field is still an input"


def test_a_processor_declaring_no_config_publishes_what_rust_publishes():
    """One catalog reads one way whichever language declared the processor."""
    assert schema_of(None) == {
        "type": "object",
        "description": "This processor declares no configuration.",
        "additionalProperties": False,
    }


def test_the_document_is_2020_12_with_no_meta_schema_key():
    for config_class in (BlurConfigTypedDict, BlurConfigDataclass, BlurConfigModel):
        assert "$schema" not in schema_of(config_class), config_class


# ---------------------------------------------------------------------------
# Hosting: constructing the class from the mapping, and reconfiguring
# ---------------------------------------------------------------------------


@processor(execution="manual")
class DataclassConfigured:
    def __init__(self, config: BlurConfigDataclass) -> None:
        self.config = config

    def configure(self, config: BlurConfigDataclass) -> None:
        self.config = config


@processor(execution="manual")
class TypedDictConfigured:
    def __init__(self, config: BlurConfigTypedDict) -> None:
        self.config = config


@processor(execution="manual")
class ModelConfigured:
    def __init__(self, config: BlurConfigModel) -> None:
        self.config = config


@processor(execution="manual")
class Unconfigured:
    def __init__(self) -> None:
        self.seen = 0


def test_a_dataclass_config_reaches_the_processor_as_an_object():
    built = construct_processor_instance(
        DataclassConfigured, {"width": 4, "label": "left"}, None
    )

    assert built.config == BlurConfigDataclass(width=4, label="left")


def test_a_typed_dict_config_reaches_the_processor_as_the_mapping_itself():
    built = construct_processor_instance(TypedDictConfigured, {"width": 4}, None)

    assert built.config == {"width": 4}


def test_a_model_config_reaches_the_processor_validated():
    built = construct_processor_instance(ModelConfigured, {"width": "4"}, None)

    assert built.config.width == 4, "the model coerced it; the wheel added no opinion"


def test_whatever_the_config_class_raises_is_what_the_author_sees():
    """Construction is the only check the wheel performs: how strict it is is
    the author's choice of config class, the same dial `read(port, into=T)` is."""
    with pytest.raises(TypeError, match="bogus"):
        construct_processor_instance(DataclassConfigured, {"bogus": 1}, None)

    with pytest.raises(pydantic.ValidationError):
        construct_processor_instance(ModelConfigured, {"width": "wide"}, None)


def test_a_processor_declaring_no_config_refuses_a_non_empty_one_by_name():
    with pytest.raises(TypeError, match="`width` has nowhere to go"):
        construct_processor_instance(Unconfigured, {"width": 1}, None)


def test_a_processor_declaring_no_config_takes_an_empty_one():
    assert construct_processor_instance(Unconfigured, {}, None).seen == 0
    assert construct_processor_instance(Unconfigured, None, None).seen == 0


def test_reconfiguration_hands_configure_the_same_kind_of_object():
    built = construct_processor_instance(DataclassConfigured, {"width": 4}, None)

    apply_configuration(built, {"width": 9, "label": "right"})

    assert built.config == BlurConfigDataclass(width=9, label="right")


def test_a_processor_without_configure_is_refused_by_the_hook_it_needs():
    built = construct_processor_instance(TypedDictConfigured, {"width": 4}, None)

    with pytest.raises(TypeError, match=r"configure\(self, config\)"):
        apply_configuration(built, {"width": 9})


def test_a_configuration_that_is_not_a_mapping_is_refused_before_construction():
    with pytest.raises(TypeError, match="must be a dict"):
        construct_processor_instance(DataclassConfigured, ["width", 4], None)


def test_a_typing_extensions_typed_dict_is_recognised_as_one():
    """`typing.is_typeddict` sees `typing.TypedDict` alone.

    On the 3.10 floor `Required` / `NotRequired` come from `typing_extensions`,
    so its spelling is the one an author reaches for — and unrecognised it
    would fall through to an open object with no keys and no refusal to say so.
    """
    typing_extensions = pytest.importorskip("typing_extensions")

    class ExtensionSpelledConfig(typing_extensions.TypedDict):
        width: int

    document = schema_of(ExtensionSpelledConfig)

    assert document["properties"]["width"] == {"type": "integer"}
    assert document["required"] == ["width"]


def test_a_config_annotated_as_any_is_refused_the_same_on_every_version():
    """`isinstance(typing.Any, type)` is False on 3.10 and True on 3.11+, so
    without naming `Any` the rule would differ across the wheel's own range."""
    with pytest.raises(TypeError, match="`Any`"):

        @processor(execution="manual")
        class Blur:
            def __init__(self, config: Any) -> None:
                self.config = config


# ---------------------------------------------------------------------------
# The migrated fixtures, guarded where CI can see them
# ---------------------------------------------------------------------------

# Every other test that runs these five is `requires_gpu` and so runs on the rig
# alone. Decoration is where a bad migration raises, so importing them here is
# what puts the migration in front of CI at all.
MIGRATED_FIXTURES = [
    ("capability_context_probes", "ConfigProbe", "ConfigProbeConfig"),
    ("helper_placement_processors", "ReportsItsOwnProcessSource", "ReportsItsOwnProcessSourceConfig"),
    ("helper_process_probes", "PassThroughProbe", "PassThroughProbeConfig"),
    ("single_processor_under_test", "ConfiguredScaler", "ConfiguredScalerConfig"),
    ("texture_ring_producer_probes", "TextureRingPublishingVideoSource", "TextureRingPublishingVideoSourceConfig"),
]


@pytest.mark.parametrize(
    ("module_name", "processor_name", "config_name"),
    MIGRATED_FIXTURES,
    ids=[processor_name for _, processor_name, _ in MIGRATED_FIXTURES],
)
def test_a_migrated_fixture_declares_the_config_class_beside_it(
    module_name, processor_name, config_name
):
    module = __import__(module_name)
    processor_class = getattr(module, processor_name)

    assert processor_class.__streamlib_processor_config_class__ is getattr(
        module, config_name
    )


def test_the_live_mutation_fixture_written_as_a_source_string_still_declares():
    """`LiveAddedEffect` lives as a triple-quoted literal, so no import, no
    linter and no AST sweep reaches it — running it here is the only way a bad
    migration of it fails anywhere but on the rig."""
    from test_live_graph_mutation import LIVE_ADDED_EFFECT_SOURCE

    namespace: "dict[str, Any]" = {"__name__": "processors.live_added_effect"}
    exec(compile(LIVE_ADDED_EFFECT_SOURCE, "live_added_effect.py", "exec"), namespace)

    effect = namespace["LiveAddedEffect"]
    assert effect.__streamlib_processor_config_class__ is namespace["LiveAddedEffectConfig"]
    assert effect.__streamlib_processor_config_schema__["properties"]["marker"] == {
        "type": "string",
        "default": "LIVE_FRAME",
    }
