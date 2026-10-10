# Consolidation of TEST and BUILD

Scope: two PowerShell TEST entry points and two BUILD entry points; internal environment
helpers remain. Preserve existing scenarios and uncommitted changes. No device deployment
or commit. Owners: engineering, engineering-contracts, test-plan, tooling catalogue.

- [x] Move host tests to a standard NUnit project, with C# UDP fixture and C++ IPC fixture.
- [x] Remove replaced Python stubs and standalone test runners; unify TEST selection.
- [x] Consolidate EV3 build/package operations, preserve environment preparation.
- [x] Remove APK diff and synchronize callers, CI, docs and inventory checks.
- [ ] First full software tests and Diagnostic APK/ARM package builds.
- [ ] Review all task changes, correct defects, repeat both tests and both builds.
- [ ] Record actual results and limits, remove this plan.

Completed locally: 6 C++ suites (also ASan/UBSan), 3 NUnit unit groups and 10 functional
cases with real native IPC/UDP, 10 Python tooling suites, mocked PowerShell lifecycle
checks, Diagnostic ARM package BUILD. Review corrections were retested.

Blocked: Unity EditMode and APK BUILD, repeated exits 198: no valid Unity license.
One Editor run reached compilation; TEST and BUILD now explicitly select Android.
Activate Unity 6000.3.22f1 in Hub, then rerun both complete TEST/BUILD cycles; do not
consider this plan complete or publish an APK PASS before those runs succeed.


Follow-up tooling consolidation:
- [x] INSTALL includes pair setup and transfer; two installation entry points.
- [x] Two DEVICE entry points; Quest update persistence is an explicit option.
- [x] Two log collectors and one analysis entry point; EV3 summary limited to journald.
- [x] Catalogue excludes project C#/C++ code and obsolete tool regressions.
- [x] Follow-up review and host checks: all 10 Python suites, mocked PowerShell INSTALL/DEVICE/log collection scenarios, parser and documentation checks passed. Device execution remains NOT_RUN.
