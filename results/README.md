# Test evidence

Generated reports are tied to commit/build IDs and artifact hashes. A
`PRE-INSTALL AUTO` report is PASS only when every requested mandatory check was
actually run. Device, HIL and manual reports must remain `NOT RUN` when the
corresponding physical hardware was unavailable; simulator results never
promote those gates.

`PRE-INSTALL AUTO` reports conform to
`config/schema/pre_install_report.schema.json`. Generated JSON is CI/release
evidence and is not committed as source; publish it with the matching build
artifacts.
