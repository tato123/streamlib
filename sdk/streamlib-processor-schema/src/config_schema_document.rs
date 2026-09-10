// Copyright (c) 2025 Jonathan Fontanez
// SPDX-License-Identifier: BUSL-1.1

//! The JSON Schema a processor descriptor carries for its config type.
//!
//! One dialect leaves this seam: JSON Schema draft 2020-12 with no `$schema`
//! key. `schemars` 0.8 emits draft-07, whose only difference in what it
//! produces is the `definitions` keyword and the `#/definitions/` references
//! that point into it, so the rewrite below is the whole of the conversion.

use serde_json::Value;

/// Marks a type usable as a processor's `config =` type, and derives its
/// schema document.
///
/// Carries the `JsonSchema` bound so that a config type without the derive
/// fails on this trait, whose note names the fix, rather than on a bare
/// `schemars` bound the author has no path to.
#[diagnostic::on_unimplemented(
    message = "`{Self}` is a processor `config =` type but does not derive `JsonSchema`",
    note = "add `#[derive(streamlib::sdk::schemars::JsonSchema)]` and `#[schemars(crate = \"streamlib::sdk::schemars\")]` to `{Self}`",
    note = "the SDK re-exports `schemars` at `streamlib::sdk::schemars`, so the crate needs no new dependency"
)]
pub trait ProcessorConfigJsonSchema {
    /// This config type's schema, as JSON Schema draft 2020-12.
    fn processor_config_schema_document() -> Value;
}

impl<T: schemars::JsonSchema> ProcessorConfigJsonSchema for T {
    fn processor_config_schema_document() -> Value {
        let draft_07_document = serde_json::to_value(
            schemars::r#gen::SchemaGenerator::default().into_root_schema_for::<T>(),
        )
        .expect("a schemars root schema always serializes");
        rewrite_draft_07_document_as_2020_12(draft_07_document)
    }
}

/// Rewrite a schemars draft-07 document as draft 2020-12.
fn rewrite_draft_07_document_as_2020_12(mut document: Value) -> Value {
    if let Some(root_object) = document.as_object_mut() {
        root_object.remove("$schema");
        if let Some(definitions) = root_object.remove("definitions") {
            root_object.insert("$defs".to_string(), definitions);
        }
    }
    rewrite_definitions_references(&mut document);
    document
}

/// Repoint every `#/definitions/…` reference at `#/$defs/…`, at any depth.
fn rewrite_definitions_references(node: &mut Value) {
    match node {
        Value::Object(members) => {
            for (key, value) in members.iter_mut() {
                if key == "$ref"
                    && let Some(reference) = value.as_str()
                    && let Some(definition_name) = reference.strip_prefix("#/definitions/")
                {
                    *value = Value::String(format!("#/$defs/{definition_name}"));
                    continue;
                }
                rewrite_definitions_references(value);
            }
        }
        Value::Array(items) => items.iter_mut().for_each(rewrite_definitions_references),
        _ => {}
    }
}

#[cfg(test)]
mod config_schema_document_tests {
    use super::*;
    use schemars::JsonSchema;
    use serde::{Deserialize, Serialize};

    /// The shape a served document is checked against: doc comments become
    /// descriptions, serde defaults become defaults, and a field without one
    /// is required.
    #[derive(Serialize, Deserialize, JsonSchema)]
    struct FixtureSourceConfig {
        /// Frame width in pixels.
        #[serde(default = "default_width")]
        width: u32,
        /// Where the recording is written.
        path: String,
        /// How the frame maps onto the window.
        #[serde(default)]
        scaling: FixtureScaling,
    }

    fn default_width() -> u32 {
        1280
    }

    #[derive(Serialize, Deserialize, JsonSchema, Default)]
    #[serde(rename_all = "snake_case")]
    enum FixtureScaling {
        #[default]
        Fit,
        Stretch,
    }

    #[test]
    fn a_config_types_document_carries_each_fields_type_description_and_default() {
        let document = FixtureSourceConfig::processor_config_schema_document();
        let width = &document["properties"]["width"];
        assert_eq!(width["type"], "integer");
        assert_eq!(width["description"], "Frame width in pixels.");
        assert_eq!(width["default"], 1280);
    }

    #[test]
    fn a_field_serde_declares_no_default_for_is_required_and_one_it_does_is_not() {
        let document = FixtureSourceConfig::processor_config_schema_document();
        let required = document["required"].as_array().expect("a required list");
        assert!(required.contains(&Value::String("path".to_string())));
        assert!(!required.contains(&Value::String("width".to_string())));
        assert!(!required.contains(&Value::String("scaling".to_string())));
    }

    #[test]
    fn the_document_is_2020_12_with_no_schema_key_and_no_definitions_keyword() {
        let document = FixtureSourceConfig::processor_config_schema_document();
        assert!(document.get("$schema").is_none());
        assert!(document.get("definitions").is_none());
        assert!(document["$defs"]["FixtureScaling"].is_object());
    }

    #[test]
    fn a_nested_types_reference_points_into_defs_rather_than_definitions() {
        let document = FixtureSourceConfig::processor_config_schema_document();
        let rendered = serde_json::to_string(&document).expect("the document serializes");
        assert!(
            !rendered.contains("#/definitions/"),
            "no draft-07 reference may survive the rewrite: {rendered}"
        );
        assert!(
            rendered.contains("#/$defs/FixtureScaling"),
            "the nested enum's reference must be repointed: {rendered}"
        );
    }

    /// The refusal an author meets is the whole point of routing the bound
    /// through this trait, and it lives in an attribute no test can call. This
    /// reads the attribute's own source so that editing the note down to a
    /// bare trait-bound error reddens here.
    #[test]
    fn the_missing_derive_note_names_the_derive_and_the_re_export_path() {
        let source = include_str!("config_schema_document.rs");
        let note = source
            .lines()
            .find(|line| line.contains("note = \"add `#[derive("))
            .expect("the missing-derive note");
        assert!(note.contains("streamlib::sdk::schemars::JsonSchema"));
        assert!(note.contains("schemars(crate = "));
        assert!(
            source.contains("so the crate needs no new dependency"),
            "the note must say the crate adds no dependency"
        );
    }

    #[test]
    fn a_reference_nested_inside_an_array_is_repointed_too() {
        let mut document = serde_json::json!({
            "definitions": { "Door": { "type": "string" } },
            "anyOf": [{ "$ref": "#/definitions/Door" }, { "type": "null" }],
        });
        document = rewrite_draft_07_document_as_2020_12(document);
        assert_eq!(document["anyOf"][0]["$ref"], "#/$defs/Door");
        assert!(document["$defs"]["Door"].is_object());
    }
}
