# PHANTOM protocol sources

Navigation only. The generated human-readable mirror is [protocol-wire-reference.md](protocol-wire-reference.md); do not
duplicate wire tables here or anywhere else.

| file | role |
|---|---|
| [protocol/wire_schema.yaml](../protocol/wire_schema.yaml) | normative machine-readable Quest↔EV3 wire source (JSON syntax, also valid YAML; the host generator uses the Python standard library) |
| [protocol/semantics.yaml](../protocol/semantics.yaml) | shared protocol semantics and compatibility inputs |
| [protocol/ipc_schema.yaml](../protocol/ipc_schema.yaml) | normative machine-readable source for the EV3-local `phantom-network` ↔ `phantom-controller` boundary |
| [protocol/jcs.py](../protocol/jcs.py) | reference RFC 8785 canonicalizer for host tools; codec implementations must derive identical canonical bytes |
| [protocol/phantom_protocol.py](../protocol/phantom_protocol.py) | Python reference codec for host tools and the existing EV3 worker; production migration to C++ is tracked in [current status](current-status.md) |
| [docs/protocol-wire-reference.md](protocol-wire-reference.md) | **generated** human-readable mirror of both schemas |
| [protocol/generated/](../protocol/generated/) | canonical projections, C++/C#/Python constants and layouts, schema hashes |
| [protocol/golden_vectors/](../protocol/golden_vectors/) | cross-language fixtures: `v1.json` (wire), `ipc_v1.json` (IPC layout), `jcs_v1.json` (canonicalization) |

Run `python tools/protocolgen.py` after an intentional schema change.
Run `python tools/protocolgen.py --check --include-docs` to check generated metadata,
the documentation mirror and golden vectors. This check also runs through
[documentation lint](../tools/doclint.py).

Transport and authentication requirements belong to the [protocol specification](protocol-specification.md).
The key committed in `golden_vectors/` is `bytes(range(32))` — a published test vector, never
production key material.
