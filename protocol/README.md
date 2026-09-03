# PHANTOM wire protocol v1

`wire_schema.yaml` is the normative machine-readable source. It is JSON syntax
and therefore valid YAML 1.2, which keeps generation dependency-free on the
legacy EV3 build image.

Run `python tools/protocolgen.py` after an intentional schema change. CI and
`PRE-INSTALL AUTO` run the same command with `--check` and reject stale C++/C#
metadata or golden vectors. The v1 transport is bounded to 1024 bytes and uses
HMAC-SHA-256 with a minimum 32-byte PSK; the checked-in golden key is test-only.
