# PHANTOM protocol v1

`wire_schema.yaml` is the normative machine-readable source. It is JSON syntax
(and therefore valid YAML) so generation needs only the standard library.
`tools/protocolgen.py` validates all 21 exact payload sizes, computes the
canonical schema SHA-256 and generates C++/C# constants plus HMAC golden
vectors. Datagram bounds are 64-byte header + at most 928-byte payload +
32-byte HMAC, with a 1024-byte total limit.

Do not hand-edit generated files. CI runs `protocolgen.py --check`.
