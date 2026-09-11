# Research memo: what "a couple of bytes" means in Zenoh, and what the iceoryx2 gateway forwards

2026-09-10, for the §Networking OPEN on the cross-host fabric (Zenoh) and the #2217
session. Question: the owner recalled that a payload can cross Zenoh by "referencing a
key, transferring a couple of bytes" instead of the data. What is that mechanism exactly,
what are its limits, and does the shipped iceoryx2 ↔ Zenoh bridge use it? A side
question — whether Apache Arrow has any Zenoh integration — is answered because it was
asked; Arrow is not a direction (owner, same day).

Evidence **[V] verified** from primary sources at the revisions named: zenoh 1.10.1
(latest release 2026-09-07) and its `main`; iceoryx2 tags v0.7.0, v0.8.0, v0.9.3 (latest,
2026-07-08) and `main`; arrow.apache.org format docs.

## Answer

**The recollection is Zenoh's shared-memory transport, and it is a same-host fast path
with transparent fallback — not a change to what crosses a network.**

- A publisher allocates its payload through Zenoh's `ShmProvider` and `put`s the
  SHM-backed buffer. On a session that passed the shared-memory probe, the wire carries
  a one-byte `SHM_PTR` tag and a small descriptor — `data_len`, a `MetadataDescriptor
  { id: u16, index: u16 }` and a `generation: u32`, all varint-encoded — and the
  subscriber maps the segment and reads the bytes in place as a read-only `ZShm` **[V]**
  `commons/zenoh-codec/src/core/zbuf.rs` (`ZSliceKind::ShmPtr`),
  `commons/zenoh-shm/src/lib.rs` (`ShmBufInfo`), `commons/zenoh-shm/src/reader.rs`.
  The exact byte count is not documented; the fields above are the whole payload.
- The transport's own rule, verbatim **[V]** `io/zenoh-transport/src/common/shm/interop.rs`:
  `shmbuf -> shminfo if partner supports shmbuf's SHM protocol; shmbuf -> rawbuf if
  partner does not support shmbuf's SHM protocol; rawbuf -> rawbuf`. Across hosts, or
  to a peer with shared memory disabled, the same `put` sends the bytes. No error, no
  code change.
- Support is negotiated per session by a `shm_open` challenge at session establishment;
  a peer that cannot open the other's segment silently continues without SHM **[V]**
  `io/zenoh-transport/src/unicast/establishment/ext/shm/auth.rs`. The test
  `zenoh_shm_unicast_to_non_shm` proves SHM works over a TCP loopback link, so it is
  the host boundary that matters, not the link type **[V]** `zenoh/tests/shm.rs`.
- Buffers are reference-counted across processes in the chunk header; the sender
  increments before send, the receiver's drop decrements **[V]**
  `commons/zenoh-shm/src/lib.rs`. Safe allocation policies are `GarbageCollect` /
  `BlockOn`; `Deallocate` "may deallocate and reuse a buffer that is currently in use".
- The API is behind the non-default `shared-memory` feature and is marked **unstable**:
  "it works as advertised, but it may be changed in a future release" **[V]**
  https://docs.rs/zenoh/latest/zenoh/shm/index.html. There is also an implicit
  optimisation: a raw payload at or above `message_size_threshold` (default 3072 bytes)
  is copied into a provider buffer when one is configured **[V]** `DEFAULT_CONFIG.json5`.

**The iceoryx2 ↔ Zenoh bridge exists, is byte-forwarding, and does not use Zenoh SHM.**

- Shipped since iceoryx2 v0.7.0 ("Tunnel over zenoh for publish-subscribe and event
  services"), as crate `iceoryx2-tunnel-zenoh` in v0.8.0 and
  `iceoryx2-integrations-zenoh-tunnel-backend` in v0.9.3; renamed "gateway" on `main`
  (unreleased) **[V]** `doc/release-notes/iceoryx2-v0.7.0.md`, `integrations/Cargo.toml`.
- It maps a service to the key expressions `iox2/publish_subscribe/{service_id}`,
  `iox2/event/{service_id}`, `iox2/service_details/{service_id}` **[V]** v0.8.0 `keys.rs`.
- Egress copies the sample's bytes to the heap (`ZBytes::from(&[u8])` is `to_vec`);
  ingress copies the Zenoh payload into a loaned iceoryx2 slot. No revision references
  `zenoh::shm` **[V]** v0.8.0 `relays/publish_subscribe.rs`; grep across v0.8.0, v0.9.3
  and `main`. Its own doc: zero-copy applies to the iceoryx2 fan-out *after* ingest.
- `main`'s wire format wraps `MessageFrame { user_header, payload }` in postcard and
  validates the type layout on receipt; v0.9.3 prepends the user header to the payload.
  The released format is the v0.9.3 one.

**Arrow has no Zenoh integration, official or otherwise.** Zenoh's 53 predefined
`Encoding` constants include CBOR and protobuf but neither Arrow nor msgpack; the
`eclipse-zenoh` and `apache/arrow` orgs contain no cross-references **[V]**
`zenoh/src/api/encoding.rs`; GitHub code search. Arrow's own transports are Flight (gRPC)
and an experimental "Dissociated IPC" tested only on UCX and libfabric **[V]**
https://arrow.apache.org/docs/format/Flight.html,
https://arrow.apache.org/docs/format/DissociatedIPC.html. Arrow's C Data and C Device
interfaces are same-process only **[V]**
https://arrow.apache.org/docs/format/CDataInterface.html.

## What this means for the runtime

- "A couple of bytes" is real, but it is Zenoh talking to Zenoh on one host. It gives
  nothing across hosts, where the bytes go once regardless, and nothing inside a node,
  where iceoryx2 already does the same job.
- The shipped bridge is how a node's channels could appear on a Zenoh namespace with no
  engine change: each iceoryx2 service becomes a key expression, at the cost of one copy
  per direction at the node boundary. That is the cheap way to "start publishing things
  in Zenoh namespaces" and see what coordination looks like before designing any of it.
- Neither mechanism inspects a payload. A bag stays a bag on every hop, which is what the
  key-set / vocabulary direction the owner is exploring depends on.

## What remains unknown

- The measured per-message cost of the SHM descriptor path versus a raw small payload;
  no source states it.
- Whether Zenoh's `unixsock-stream` or `unixpipe` links change the SHM behaviour beyond
  the probe (the test covers TCP loopback only).
- Whether the iceoryx2 gateway's release after v0.9.3 keeps the header-plus-payload wire
  form or ships `main`'s postcard framing.
