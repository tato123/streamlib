// Copyright (c) 2025 Jonathan Fontanez
// SPDX-License-Identifier: BUSL-1.1

//! The refusal an author meets when a `config =` type does not derive
//! `JsonSchema`.
//!
//! The descriptor carries the config type's schema, so the derive is a
//! requirement rather than an option. Without a compile-fail case nothing runs
//! the compiler over a config type that lacks it, and the note that names the
//! fix could rot into a bare trait-bound error with every other test green.
//!
//! Refresh the expected output with `TRYBUILD=overwrite cargo test -p
//! streamlib-engine --test compile_fail_config_without_json_schema` after a
//! compiler upgrade reflows a diagnostic.

#[test]
fn a_config_type_without_the_derive_is_refused_with_the_derive_and_its_path() {
    trybuild::TestCases::new().compile_fail("tests/compile_fail/*.rs");
}
