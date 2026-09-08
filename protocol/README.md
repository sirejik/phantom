# PHANTOM protocol sources

Navigation only. The generated human-readable mirror is [`protocol.md`](protocol.md); do not
duplicate wire tables here or anywhere else.

| file | role |
|---|---|
| `wire_schema.yaml` | normative machine-readable Quest↔EV3 wire source (JSON syntax, therefore valid YAML, so generation stays dependency-free on the pinned ev3dev image) |
| `ipc_schema.yaml` | normative machine-readable source for the EV3-local `phantom-network` ↔ `phantom-controller` boundary |
| `jcs.py` | RFC 8785 canonicalization, shared by every component so Quest and EV3 derive identical hashed bytes |
| `phantom_protocol.py` | reference codec used by the EV3 worker and the host tools |
| `protocol.md` | **generated** human-readable mirror of both schemas |
| `generated/` | canonical projections, C++/C#/Python constants and layouts, schema hashes |
| `golden_vectors/` | cross-language fixtures: `v1.json` (wire), `ipc_v1.json` (IPC layout), `jcs_v1.json` (canonicalization) |

Run `python tools/protocolgen.py` after an intentional schema change. The TEST phase and CI
run the same command with `--check` and reject stale metadata, a stale `protocol.md`, or stale
golden vectors.

The v1 transport is bounded to 1024 bytes and uses HMAC-SHA-256 with a minimum 32-byte PSK.
The key committed in `golden_vectors/` is `bytes(range(32))` — a published test vector, never
production key material.
