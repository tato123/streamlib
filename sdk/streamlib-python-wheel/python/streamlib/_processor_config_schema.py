# Copyright (c) 2025 Jonathan Fontanez
# SPDX-License-Identifier: BUSL-1.1

"""Deriving a processor's config schema from the config class its author wrote.

The document is JSON Schema draft 2020-12 with no `$schema` key — the dialect
`sdk/streamlib-processor-schema/src/config_schema_document.rs` emits for a Rust
config type, so a node serves one dialect whichever language declared the
processor. Nested classes are inlined and `Optional[T]` is an `anyOf` with null,
so nothing here emits a `$ref` and no document needs a `$defs`.

Stdlib only. A model is recognised by the `model_json_schema` method it carries
rather than by importing pydantic, which the wheel does not depend on.

`additionalProperties` is stated only where the config class refuses unknown
keys: a dataclass does, a TypedDict does not, and a model's own document speaks
for itself.
"""

from __future__ import annotations

import collections.abc
import dataclasses
import enum
import types
import typing
from typing import Any

__all__ = [
    "derive_config_class_json_schema",
    "json_schema_for_a_processor_declaring_no_config",
]

_SCALAR_JSON_TYPES = {
    bool: "boolean",
    int: "integer",
    float: "number",
    str: "string",
}

_SEQUENCE_ORIGINS = (
    list,
    set,
    frozenset,
    tuple,
    collections.abc.Sequence,
    collections.abc.MutableSequence,
    collections.abc.Set,
)

_MAPPING_ORIGINS = (
    dict,
    collections.abc.Mapping,
    collections.abc.MutableMapping,
)


def is_a_typed_dict(candidate: Any) -> bool:
    """Whether `candidate` is a TypedDict under either spelling.

    `typing.is_typeddict` recognises `typing.TypedDict` alone, and a
    `typing_extensions.TypedDict` subclass — what an author on the 3.10 floor
    reaches for, and what `Required` / `NotRequired` need there — is invisible
    to it. The pair of key sets is the structural signature of one; nothing
    else carries both.
    """
    return typing.is_typeddict(candidate) or (
        isinstance(candidate, type)
        and hasattr(candidate, "__required_keys__")
        and hasattr(candidate, "__optional_keys__")
    )


def json_schema_for_a_processor_declaring_no_config() -> "dict[str, Any]":
    """The document a processor that takes no configuration publishes.

    Mirrors what `EmptyConfig` publishes on the Rust side, description
    included, so the catalog reads the same for either language.
    """
    return {
        "type": "object",
        "description": "This processor declares no configuration.",
        "additionalProperties": False,
    }


def derive_config_class_json_schema(config_class: type) -> "dict[str, Any]":
    """The JSON Schema of `config_class`, derived from what its author wrote."""
    model_json_schema = getattr(config_class, "model_json_schema", None)
    if callable(model_json_schema):
        return _document_the_model_carries(config_class, model_json_schema)
    if is_a_typed_dict(config_class):
        return _typed_dict_document(config_class)
    if dataclasses.is_dataclass(config_class):
        return _dataclass_document(config_class)
    # An open object says the configuration is a mapping and claims nothing
    # about its keys, which is all that can honestly be derived from a class of
    # a kind the deriver does not recognise.
    return {"type": "object"}


def _document_the_model_carries(
    config_class: type, model_json_schema: "typing.Callable[[], Any]"
) -> "dict[str, Any]":
    """A model's own schema, verbatim minus the two keys the catalog owns."""
    document = model_json_schema()
    if not isinstance(document, dict):
        raise TypeError(
            f"{config_class.__name__}.model_json_schema() returned "
            f"{type(document).__name__} rather than a dict, so it cannot be a "
            f"processor's config class. A config class is a TypedDict, a dataclass, "
            f"or a model whose `model_json_schema()` returns a JSON Schema document."
        )
    return {
        key: value for key, value in document.items() if key not in ("$schema", "title")
    }


def _typed_dict_document(config_class: type) -> "dict[str, Any]":
    annotations = _resolved_class_annotations(config_class)
    required_keys = getattr(config_class, "__required_keys__", frozenset())
    document: "dict[str, Any]" = {
        "type": "object",
        "properties": {
            key: _json_schema_for_annotation(annotation)
            for key, annotation in annotations.items()
        },
    }
    # Declaration order rather than the set's, so deriving one class twice
    # gives one document.
    required = [key for key in annotations if key in required_keys]
    if required:
        document["required"] = required
    return document


def _dataclass_document(config_class: type) -> "dict[str, Any]":
    annotations = _resolved_class_annotations(config_class)
    properties: "dict[str, Any]" = {}
    required: "list[str]" = []
    for field in dataclasses.fields(config_class):
        # An `init=False` field is not a constructor input, so a configuration
        # cannot carry it and it is not documented.
        if not field.init:
            continue
        field_schema = _json_schema_for_annotation(
            annotations.get(field.name, field.type)
        )
        has_default = field.default is not dataclasses.MISSING
        has_default_factory = field.default_factory is not dataclasses.MISSING
        if has_default:
            rendered_default = _json_representable(field.default)
            if rendered_default is not _NOT_JSON_REPRESENTABLE:
                field_schema["default"] = rendered_default
        if not has_default and not has_default_factory:
            required.append(field.name)
        properties[field.name] = field_schema

    document: "dict[str, Any]" = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        document["required"] = required
    return document


def _resolved_class_annotations(config_class: type) -> "dict[str, Any]":
    """Every annotated field of `config_class`, with forward references resolved."""
    try:
        return typing.get_type_hints(config_class, include_extras=True)
    except Exception as unresolvable:
        raise TypeError(
            f"{config_class.__name__} carries an annotation that cannot be resolved, "
            f"so its config schema cannot be derived: {unresolvable}. Every "
            f"annotation on a config class must name something importable at run "
            f"time, not only under `TYPE_CHECKING`."
        ) from unresolvable


def _json_schema_for_annotation(annotation: Any) -> "dict[str, Any]":
    """The schema of one annotated field.

    An annotation the deriver does not recognise renders as an empty schema
    rather than refusing the class: a config class is worth publishing long
    before every type in it is describable.
    """
    metadata = getattr(annotation, "__metadata__", None)
    if metadata is not None:
        described = _json_schema_for_annotation(typing.get_args(annotation)[0])
        description = next((entry for entry in metadata if isinstance(entry, str)), None)
        if description is not None:
            described["description"] = description
        return described

    if annotation is None or annotation is type(None):
        return {"type": "null"}
    if annotation is Any:
        return {}

    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        return {
            "anyOf": [
                _json_schema_for_annotation(member)
                for member in typing.get_args(annotation)
            ]
        }
    if origin is typing.Literal:
        return _enumerated_schema(typing.get_args(annotation))
    if origin is not None:
        if origin in _SEQUENCE_ORIGINS:
            return _sequence_schema(annotation, origin)
        if origin in _MAPPING_ORIGINS:
            return {"type": "object"}
        # A parameterized generic the deriver does not know. This branch is
        # also what keeps one out of the nested-class branch below on Python
        # 3.10, where `isinstance(dict[str, int], type)` is still True.
        return {}

    if isinstance(annotation, type):
        if annotation in _SCALAR_JSON_TYPES:
            return {"type": _SCALAR_JSON_TYPES[annotation]}
        if annotation in _SEQUENCE_ORIGINS:
            return {"type": "array"}
        if annotation in _MAPPING_ORIGINS:
            return {"type": "object"}
        if issubclass(annotation, enum.Enum):
            return _enumerated_schema(tuple(member.value for member in annotation))
        if (
            is_a_typed_dict(annotation)
            or dataclasses.is_dataclass(annotation)
            or callable(getattr(annotation, "model_json_schema", None))
        ):
            # Inlined rather than referenced: nothing here emits a `$ref`, so
            # no document carries a `$defs` for one to point into.
            return derive_config_class_json_schema(annotation)

    return {}


def _enumerated_schema(members: "tuple[Any, ...]") -> "dict[str, Any]":
    rendered = [_json_representable(member) for member in members]
    if any(member is _NOT_JSON_REPRESENTABLE for member in rendered):
        return {}
    return {"enum": rendered}


def _sequence_schema(annotation: Any, origin: Any) -> "dict[str, Any]":
    document: "dict[str, Any]" = {"type": "array"}
    element_annotations = typing.get_args(annotation)
    if origin is tuple:
        # `tuple[T, ...]` is a homogeneous sequence; every other tuple is
        # positional, which 2020-12 spells `prefixItems`.
        if len(element_annotations) == 2 and element_annotations[1] is Ellipsis:
            document["items"] = _json_schema_for_annotation(element_annotations[0])
        elif element_annotations:
            document["prefixItems"] = [
                _json_schema_for_annotation(element) for element in element_annotations
            ]
        return document
    if len(element_annotations) == 1:
        document["items"] = _json_schema_for_annotation(element_annotations[0])
    return document


class _NotJsonRepresentableSentinel:
    """The type of [`_NOT_JSON_REPRESENTABLE`] — never constructed by an author."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "_NOT_JSON_REPRESENTABLE"


# Distinct from `None`, which is itself a representable default.
_NOT_JSON_REPRESENTABLE = _NotJsonRepresentableSentinel()


def _json_representable(value: Any) -> Any:
    """`value` as JSON, or [`_NOT_JSON_REPRESENTABLE`] if it is not expressible.

    The derived document crosses into Rust as JSON, so a default the wire
    cannot carry is dropped rather than left to fail the whole declaration.
    """
    if isinstance(value, enum.Enum):
        return _json_representable(value.value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        rendered = [_json_representable(entry) for entry in value]
        if any(entry is _NOT_JSON_REPRESENTABLE for entry in rendered):
            return _NOT_JSON_REPRESENTABLE
        return rendered
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            return _NOT_JSON_REPRESENTABLE
        rendered = {key: _json_representable(entry) for key, entry in value.items()}
        if any(entry is _NOT_JSON_REPRESENTABLE for entry in rendered.values()):
            return _NOT_JSON_REPRESENTABLE
        return rendered
    return _NOT_JSON_REPRESENTABLE
