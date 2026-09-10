// Copyright (c) 2025 Jonathan Fontanez
// SPDX-License-Identifier: BUSL-1.1

//! Processor infrastructure and implementations.

pub mod traits;

#[doc(hidden)]
pub mod __generated_private;

mod processor_instance_factory;
mod processor_spec;
// Re-export graph types — `ProcessorState` and `ProcessorStateComponent`
// live in `core::graph` (#786); kept as a re-export here so the public
// `streamlib::sdk::processors::ProcessorState` path stays stable.
pub use crate::core::graph::{ProcessorState, ProcessorStateComponent};

// Re-export processor traits
pub use traits::{Config, ConfigValidationError};
// Mode-specific processor traits
pub use traits::{ContinuousProcessor, ManualProcessor, ReactiveProcessor};

// Re-export internal traits (doc-hidden but needed by macro and runtime)
#[doc(hidden)]
pub use __generated_private::{
    DynGeneratedProcessor, GeneratedProcessor, OutOfProcessLinkWiringEnvelope,
};

pub use processor_instance_factory::{
    DynamicProcessorConstructorFn, PROCESSOR_REGISTRY, ProcessorInstance, ProcessorInstanceFactory,
};
pub use processor_spec::ProcessorSpec;

/// The config type of a processor that declares none.
///
/// It publishes an empty-object schema and takes nothing: a configuration
/// carrying keys is refused rather than discarded, because a processor that
/// declares no config cannot act on one and silently dropping it hides a
/// wiring mistake. It serializes back as an empty named map so it round-trips
/// as a bag.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct EmptyConfig;

impl serde::Serialize for EmptyConfig {
    fn serialize<S: serde::Serializer>(
        &self,
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        serde::ser::SerializeMap::end(serializer.serialize_map(Some(0))?)
    }
}

impl<'de> serde::Deserialize<'de> for EmptyConfig {
    fn deserialize<D: serde::Deserializer<'de>>(
        deserializer: D,
    ) -> std::result::Result<Self, D::Error> {
        deserializer.deserialize_any(EmptyConfigVisitor)
    }
}

/// Accepts an empty named map and the legacy `nil`; refuses anything a
/// processor declaring no config could not have meant.
struct EmptyConfigVisitor;

impl<'de> serde::de::Visitor<'de> for EmptyConfigVisitor {
    type Value = EmptyConfig;

    fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("an empty configuration")
    }

    fn visit_map<A: serde::de::MapAccess<'de>>(
        self,
        mut named_map: A,
    ) -> std::result::Result<Self::Value, A::Error> {
        match named_map.next_key::<String>()? {
            Some(refused_key) => Err(serde::de::Error::custom(format!(
                "this processor declares no config and takes none, \
                 so `{refused_key}` has nowhere to go"
            ))),
            None => Ok(EmptyConfig),
        }
    }

    fn visit_unit<E: serde::de::Error>(self) -> std::result::Result<Self::Value, E> {
        Ok(EmptyConfig)
    }

    fn visit_none<E: serde::de::Error>(self) -> std::result::Result<Self::Value, E> {
        Ok(EmptyConfig)
    }
}

impl schemars::JsonSchema for EmptyConfig {
    fn schema_name() -> String {
        "EmptyConfig".to_string()
    }

    fn json_schema(_: &mut schemars::r#gen::SchemaGenerator) -> schemars::schema::Schema {
        schemars::schema::SchemaObject {
            instance_type: Some(schemars::schema::InstanceType::Object.into()),
            metadata: Some(Box::new(schemars::schema::Metadata {
                description: Some("This processor declares no configuration.".to_string()),
                ..Default::default()
            })),
            object: Some(Box::new(schemars::schema::ObjectValidation {
                additional_properties: Some(Box::new(schemars::schema::Schema::Bool(false))),
                ..Default::default()
            })),
            ..Default::default()
        }
        .into()
    }
}

// Audio processors are not here: capture and playback ship as engine
// built-ins in `streamlib-media-builtins` (`microphone_source.rs`,
// `speaker_sink.rs`).
