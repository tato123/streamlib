# Research memo: how an agent learns what a port carries, with nothing required

2026-09-10, for #2215 (milestone 51, Intent-driven graph). Question: an agent reading only
a node's MCP resources needs to know what shape of bag a processor produces and accepts —
before adding it, across fan-in, with duck-typed producers, with machine-authored custom
shapes, and in a way that survives a node-to-node fabric later. Declaring a shape on a
port was rejected on ergonomics: an input only receives, fan-in has no single shape, an
output can write a duck-typed frame without the class, and none of it should be required.
What do streaming, event and agent systems do, and what shape falls out?

Evidence split **[V] verified** (primary source read; URL given) and **[I] inferred**.
Three source families were surveyed: data planes (Zenoh, ROS 2, DDS-XTypes, GStreamer,
Holoscan), self-describing message formats (CloudEvents, AsyncAPI, AT Protocol Lexicon,
protobuf `Any`, Confluent wire format, JSON Schema, MessagePack ext), and agent protocols
(MCP 2025-06-18, A2A, OpenAI Agents SDK, Pydantic AI, LangGraph, the MCP Python and
TypeScript SDKs).

## Recommendation

**Describe bags, never ports. Publish conventions as documents. Let a bag name its own
convention when it wants to. Let the graph's provenance do the rest.** Four pieces, every
one optional, none enforced, the engine reading no bag content anywhere.

1. **Conventions are published documents on the node.** A resource lists convention
   name → JSON Schema plus prose. The four built-in conventions derive from the cast
   types that already exist. A user publishes one by marking any class — TypedDict,
   dataclass, pydantic model — with a decorator at declaration time, the same reflection
   `@processor` already does. Names are plain strings. No version, no URI, no registry
   to contact.
2. **A bag may name its convention.** One reserved key inside the map, `$convention`,
   carrying the name. Keys beginning with `$` are reserved to the protocol, and a typed
   read strips them before constructing a cast, so a user dataclass never sees one; a
   TypedDict read is the raw view and keeps them. The built-in casts write it; a
   hand-rolled bag may or may not. It is the answer for a duck-typed producer, a
   machine-authored shape, a channel carrying more than one shape, and a foreign
   transport where the link is not there to tell you.
3. **An output may say what it intends to write; an input never declares.** The output
   port method's return annotation, which the decorator already documents as "the
   declaration, read by humans and type checkers only", becomes readable: an annotation
   naming a published convention renders as `"convention": "video_frame"` on that output
   in the catalog and the graph. Unannotated renders nothing. Inputs render name,
   description and delivery profile exactly as today. The Rust attribute mirrors it with
   an optional string key on outputs only.
4. **Fan-in is provenance, not a union.** `read_from_inbound_link` already hands a
   consumer each bag with the engine-known source channel, "which a producer cannot
   misstate". A many-input processor tells producers apart by where a bag came from and,
   when present, by `$convention`. No system surveyed expresses fan-in as a shape, and
   neither should this one.

An agent's path before adding a processor: read the catalog for config schemas and
output conventions, read the conventions resource for the keys, read the live graph for
channels, and `tap` a channel to see the real keys, which needs no declaration at all
because the producer is already running. It writes the consumer against the schema with
its own local cast and imports nothing.

What this changes against the proposal it replaces: nothing on an input; a name rather
than a class on an output, and only through an annotation that already exists; a
reserved in-bag key as the cross-transport truth; a standalone convention decorator
rather than a port keyword. It touches the plan's port-rendering decision in one
respect — an output may render a convention name — and that is a hint about intent, not
a type: `connect` never reads it, `tap` stays verbatim, the map stays open.

## Why this shape — the evidence

### Nothing required, and the tag lives with the data, is the convergent choice

- Zenoh puts the description on each sample and disclaims it: "the Zenoh protocol does
  not impose any encoding value, nor does it operate on it. It can be seen as optional
  metadata" **[V]** — `zenoh/src/api/encoding.rs` lines 35-36,
  https://raw.githubusercontent.com/eclipse-zenoh/zenoh/main/zenoh/src/api/encoding.rs.
  The form is `type/subtype[;schema]` with `with_schema(...)`: "Zenoh does not define
  what a schema is, and its semantics is left to the implementer" **[V]**
  https://docs.rs/zenoh/latest/zenoh/bytes/struct.Encoding.html. An unrecognised string
  is legal on the wire (custom id `0xFFFF`) **[V]** lines 645-648. The default,
  `zenoh/bytes`, promises nothing. This is the closest analogue to a self-describing bag,
  and it is per message, never per key expression — so the in-bag name is exactly what
  the `;schema` slot would carry when the fabric lands.
- AT Protocol states the principle outright: `$type` "needs to be included any time there
  could be ambiguity about the content type when validating data" and is otherwise
  optional; "Data field names starting with `$` are reserved for use by the data model or
  protocol itself"; "Implementations should ignore unknown `$` fields" **[V]**
  https://atproto.com/specs/data-model, https://atproto.com/specs/lexicon. Unions are
  open by default and "Unexpected fields in data which otherwise conforms to the Lexicon
  should be ignored" **[V]**.
- CloudEvents makes `type` a name (reverse-DNS, no registry) and `dataschema` an OPTIONAL
  URI: "Identifies the schema that `data` adheres to" **[V]**
  https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md.
- The dereferenceable-URI-as-type idea was tried and abandoned: protobuf's `any.proto`
  now says "Do not write a scheme on these URI references so that clients do not attempt
  to contact them", and "As of May 2023, there are no widely used type server
  implementations" **[V]** https://protobuf.dev/reference/protobuf/google.protobuf/#any.
  Hence plain names, and a document on the node rather than a URL to fetch.
- JSON Schema defines no in-instance key at all; maintainers: "it's not something we can
  specify because we don't specify JSON" **[V]**
  https://github.com/orgs/json-schema-org/discussions/473. So the reserved key is ours
  to name, and the `$` sigil is the established convention for it.

### The agent world types the call, not the data between agents

- MCP: `inputSchema` is required on a tool, `outputSchema` "Optional JSON Schema defining
  expected output structure" **[V]**
  https://modelcontextprotocol.io/specification/2025-06-18/server/tools. A resource has
  `mimeType?` and no schema slot at all **[V]** `schema/2025-06-18/schema.ts`. A prompt
  argument has `description?` and `required?` and no type **[V]**.
- A2A: skills declare `inputModes` / `outputModes` as media types; a `DataPart` is
  "Arbitrary structured `data` as a JSON value" with `media_type` and no schema **[V]**
  https://github.com/a2aproject/A2A/blob/main/specification/a2a.proto.
- OpenAI Agents SDK: `handoff(input_type=None)` yields an empty schema `{}` **[V]**
  `src/agents/handoffs/__init__.py` lines 265, 303-307; Pydantic AI and LangGraph type
  the state or the output, never the edge **[V]**
  https://docs.langchain.com/oss/python/langgraph/graph-api.
- Every SDK derives its schemas from code — pydantic `TypeAdapter` / `create_model`, zod
  via `z.toJSONSchema` — and feeds descriptions from docstrings (griffe) **[V]** MCP
  python-sdk `func_metadata.py` lines 322-358; typescript-sdk `standardSchema.ts` lines
  183-206. Code-first with a derived document is the idiom the config-schema and
  convention-decorator pieces follow.

### Endpoint-declared shapes are the media-pipeline family, and they enforce

- GStreamer caps live on the pad as a *set* ("all possible types a given pad can
  handle"), with `GST_CAPS_ANY` as the wildcard, negotiated to one fixed caps before
  flow, and a mismatch refused at link: `GST_PAD_LINK_NOFORMAT` "pads do not have common
  format" **[V]** https://gstreamer.freedesktop.org/documentation/gstreamer/gstcaps.html,
  https://gstreamer.freedesktop.org/documentation/gstreamer/gstpad.html. That is the
  typed-ports design the schema-free-ports pivot removed; the flexible property of caps
  worth keeping is only that `ANY` is the default.
- ROS 2 and DDS carry one mandatory type per endpoint and resolve it at runtime by
  hash-then-fetch: RIHS hashes "communicated automatically during discovery" and a
  `~/get_type_description` service "to request the full definition from the node
  advertising that type" **[V]** Iron release notes lines 272-277; DDS-XTypes §7.6.3.2.1
  TypeLookup **[V]** https://www.omg.org/spec/DDS-XTypes/1.3/PDF. The reusable idea is
  the *fetch from the node* — which the conventions resource is — not the mandatory type.
- Holoscan's Python operators declare a port by name only — `spec.input("in")` — and
  "any Python object can be emitted or received" **[V]**
  https://docs.nvidia.com/holoscan/sdk-user-guide/holoscan_create_operator.html. Fan-in
  is `IOSpec.ANY_SIZE` returning a tuple, saying nothing about shape **[V]**. The closest
  peer runtime declares less than we already do.

### Fan-in

No surveyed system expresses fan-in as a shape: GStreamer's `tee` / `adder` intersect
caps across pads, Holoscan returns a tuple, DDS and ROS match per pair **[V]** (agent
report, patterns 5). Our engine already gives the consumer something none of them do —
an unforgeable source channel per bag through `read_from_inbound_link` **[V]**
`sdk/streamlib-python-wheel/python/streamlib/_engine.pyi` around line 733. That, plus
an optional in-bag name, covers every fan-in case without an input declaring anything.

### Why the reserved key must be stripped before a constructed cast

`read(port, into=T)` builds `T` by calling it with the bag's entries as keyword arguments
**[V]** `sdk/streamlib-python-wheel/src/python_bag_conversion.rs` lines 117-160. The
built-in casts accept `**keys_this_cast_does_not_read` for exactly the open-map reason
**[V]** `video_frame.py` line 248; a user dataclass does not, and `$convention` is not
even a legal keyword name. So the typed read drops `$`-prefixed keys before construction.
A TypedDict read returns the decoded dict untouched — the raw view keeps them. Rust's
serde ignores unknown keys by default, and `VideoFrame` has a test pinning that **[V]**
`video_frame.rs::video_frame_cast_ignores_unknown_keys`. The frame header carries
`port_key`, `timestamp_ns` and `len` and no type slot **[V]**
`runtime/streamlib-ipc-types/src/lib.rs` line 386; putting the name there would be a
`#[repr(C)]` wire change and would not travel inside a foreign transport's payload, so
in-map is the right place. MessagePack's ext types offer 128 unnamed codes and no
registry **[V]** https://github.com/msgpack/msgpack/blob/master/spec.md — a codec hook,
not a name.

## What this asks of the plan

Not decided here; pointers for `/align`:

- Config carries a derived JSON Schema (`schemars` on the Rust struct; the config class
  the Python `__init__` annotation names). Narrows the "no schema layer" wording to
  schema-first on ports, which is what was removed.
- Conventions are published by name as derived schemas, from the built-in casts and from
  any class marked at declaration; served as documentation, never attached to a link.
- A bag may carry `$convention`; `$`-prefixed keys are reserved and stripped before a
  constructed cast. The engine still reads no bag.
- An output port may render a convention name from its return annotation (Python) or an
  optional string key (Rust); inputs are unchanged. Amends the port-rendering decision by
  one optional key, stated as a hint `connect` never reads.
- Declaration registers a Python class's descriptor; the constructor still arrives at
  first add.

The Zenoh OPEN is untouched. The in-bag name is what Zenoh's per-sample `;schema` slot
would carry, so nothing here has to be undone when that fabric is decided.

## What remains unknown

- Whether a return annotation resolves reliably at decoration under
  `from __future__ import annotations` and forward references; `typing.get_type_hints`
  is the expected tool, and a string that does not resolve should render nothing rather
  than fail the class **[I]**.
- Whether the Rust output key should be checked against the built-in cast's published
  name by a test in the media crate; it can be, since both live there **[I]**.
- Whether MCP 2025-11-25 added a schema slot to resources (not fetched). If it did, the
  conventions resource could declare its own schema; nothing here depends on it.
- Zenoh's ecosystem conventions for the `;schema` string (only core `encoding.rs` was
  read).
