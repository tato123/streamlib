# Copyright (c) 2025 Jonathan Fontanez
# SPDX-License-Identifier: BUSL-1.1

"""Three processors, three kinds of config class, for one catalog read.

Their own module, not the test module, because each runs in a helper process
that reaches its class by importing the module it was declared in.

Each reports, from inside its helper, the object its `__init__` was handed —
which is the half of the contract a served schema cannot show.
"""

import dataclasses
import json
from typing import Annotated, TypedDict

import pydantic

from streamlib import RuntimeContextFullAccess, log, processor


def _report(processor_name: str, config: object) -> None:
    log.info(
        f"MARKER:CONSTRUCTED {json.dumps({'processor': processor_name, 'config_type': type(config).__name__})}"
    )


class TypedDictProbeConfig(TypedDict, total=False):
    width: Annotated[int, "How wide the probe pretends its frames are."]


@dataclasses.dataclass
class DataclassProbeConfig:
    width: Annotated[int, "How wide the probe pretends its frames are."] = 640
    label: Annotated[str, "What to call this probe."] = "unlabelled"


class ModelProbeConfig(pydantic.BaseModel):
    width: int = 1280


@processor(execution="manual", description="Configured by a TypedDict")
class TypedDictConfiguredProbe:
    def __init__(self, config: TypedDictProbeConfig) -> None:
        self.config = config

    def setup(self, ctx: RuntimeContextFullAccess) -> None:
        _report("TypedDictConfiguredProbe", self.config)


@processor(execution="manual", description="Configured by a dataclass")
class DataclassConfiguredProbe:
    def __init__(self, config: DataclassProbeConfig) -> None:
        self.config = config

    def setup(self, ctx: RuntimeContextFullAccess) -> None:
        _report("DataclassConfiguredProbe", self.config)


@processor(execution="manual", description="Configured by a model")
class ModelConfiguredProbe:
    def __init__(self, config: ModelProbeConfig) -> None:
        self.config = config

    def setup(self, ctx: RuntimeContextFullAccess) -> None:
        _report("ModelConfiguredProbe", self.config)


@processor(execution="manual", description="Takes no configuration at all")
class UnconfiguredProbe:
    def setup(self, ctx: RuntimeContextFullAccess) -> None:
        _report("UnconfiguredProbe", None)
