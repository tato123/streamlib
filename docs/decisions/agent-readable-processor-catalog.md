# Agent-readable processor catalog

Rationale for the `[agent-readable-processor-catalog]` entries in
`docs/plan/ARCHITECTURE.md` §Processor model & scheduling, decided 2026-09-10. Narrows
`schema-free-ports.md` without reversing it.

## Trigger

Read this before adding any schema, descriptor field or registration path so that an
agent driving a node over its control plane can learn what a processor accepts; before
reintroducing keyword-argument configuration for a Python processor; before making the
control plane depend on a media crate; and before answering "what does this port carry"
or "how is a bag shape described" with anything other than the open entry that holds
both.

> Withdrawn 2026-09-10 (owner): this record once also covered serving the built-in bag
> conventions as derived schemas. That is undecided — it is the same question as what a
> port reports — and its text was removed rather than kept as a decision.

## Decision

A processor's config shape is a JSON Schema derived from the config type the author
already wrote — a `JsonSchema` derive on the Rust struct, the class named by the Python
`__init__` annotation — carried on the descriptor and served in the processor catalog.
Python config is that one class, constructed by the helper and handed in as an object;
keyword-argument configuration is deleted. A Python class registers its descriptor when
its decorator runs, so it is in the catalog before its first add. What a port reports
about the bags it carries, and how a bag shape is described at all, stays open.

The line that makes this consistent with the schema-free decision: that decision bans
schema-first machinery at ports — a schema as the source of truth, codegen from it,
identity grammar, a port declaring one, `connect` comparing two. Everything here runs
the other way, code to document, and attaches to nothing on a link.

## Rejected alternatives

- **Serialize each config type's `Default` and serve the values** — live and cheap, but
  it cannot mark a required key, carries no per-field prose, and would be replaced by a
  schema field within weeks; agent clients would program against a shape we already
  knew was temporary.
- **Revive the dormant per-field `ConfigDescriptor` derive** — hand-maintained field
  metadata beside the struct, which is what a derived schema produces mechanically from
  the doc comments and serde attributes already there.
- **Keep keyword-argument config beside the class form** — two ways to say one thing,
  and the keyword form has no place to hang a schema, a description or a required
  marker without re-deriving them from a signature; a config object is also what the
  Rust side already is.
- **A `register` verb for Python** — an extra call whose only job is to make a class
  visible; the decorator already runs at import and already collects everything the
  descriptor needs.
- **Describe what a port carries now, as part of this** — every proposed shape read
  wrong on the receiving side or bound a hint to an importable class; it is held open
  with the survey that records why, rather than decided badly.

## Consequences

- `schemars` becomes part of the SDK's public surface, re-exported so a third-party Rust
  processor adds no dependency; three local config enums gain the derive.
- The descriptor carries a schema document where it carried a type-name string.
- Every Python processor that took keyword configuration changes shape: the engine-tree
  fixtures migrate with the change; example and extension-wheel processors lag as
  consumers do, and the extension wheels' required parameters become required keys in a
  config class rather than defaults.
- Reconfiguration takes the config object; `configure(self, **config)` goes with the
  keyword form.
- A helper process importing a decorated class must register nothing, so the wheel has
  to know it is running as a helper at decoration time.
- Nothing in the control plane says what a port carries or what a bag looks like. That
  was already accepted cost under the schema-free decision; it is now an open entry with
  the research behind it, not a settled absence.
