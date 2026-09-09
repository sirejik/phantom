# Переработка lifecycle PHANTOM

> **Тип:** execution plan; ненормативный
> **Область:** TEST/BUILD/PROVISION/TRANSFER/INSTALL/START/DEBUG/DEVICE INTEGRATION TEST/HIL/MANUAL ACCEPTANCE/RECOVERY
> **Начало:** 2026-09-08, `faa493af`
> **Status:** COMPLETED (2026-09-10)
> **Normative owners:** `ENGINEERING.md`, `PROTOCOL_SPECIFICATION.md`, `TEST_PLAN.md`, `IMPLEMENTATION_STAGES.md`
> **Hardware/evidence state:** все hardware-фазы текущего продолжения `NOT_RUN`
> Упоминания прежних названий фаз ниже находятся только в audit-журнале исходного состояния
> и не являются действующими командами или gates.

## Цель

Сделать каждую lifecycle-фазу явной, ограниченной одной ответственностью и независимой от
локальной истории `results/**`. Обычный Stage-3 цикл должен состоять из targeted TEST,
component-specific Diagnostic BUILD, TRANSFER, INSTALL и START/DEBUG START без скрытого
provisioning, qualification или recovery.

## Границы

- Физические Quest/EV3, DEVICE INTEGRATION TEST, HIL и manual acceptance в этой задаче не
  запускаются; их результаты остаются `NOT_RUN`.
- Сохраняются content-addressed `PHANTOM-BUILD-V3`, artifact hashes, safe install,
  zero-output, privilege separation, explicit recovery и fail-closed authentication.
- `results/**` и `build/**` остаются удаляемыми локальными outputs; credentials, SSH trust и
  Wi-Fi profile относятся только к PROVISION.
- Один итоговый commit выполняется только после off-hardware проверок.

## Этапы работы

- [x] M1 — аудит старых lifecycle-зависимостей и сохранённых хороших границ
- [x] M2 — нормативная модель и stage/test gates синхронизированы
- [x] M3 — TEST/BUILD/PROVISION/deploy/debug tooling реализован по новой модели
- [x] M4 — regressions, skills и generated documentation синхронизированы
- [x] M5 — fixed-pair PROVISION state machine, pinned identities и routine fail-fast admission
- [x] M6 — idempotent TRANSFER и единый phase-result/timing/first-failure contract
- [x] M7 — разделить structural/semantic/full protocol compatibility identities
- [x] M8 — синхронизировать historical plans/ADR/status/specs и выполнить полный non-build regression
- [x] M9 — один итоговый commit после финального audit

## Журнал прогресса

- Продолжение 2026-09-09 восстановило незакоммиченный lifecycle diff после hardware diagnosis.
  Уже сохранены исправления archive root member, runtime-traversable release directory,
  bounded START diagnostics, native stderr handling, Quest install visibility polling и
  deterministic Quest cold START. BUILD и hardware-команды в этом продолжении запрещены.
- Traceability продолжения: fixed pair → отсутствует единый state/Quest выбирает первый ADB →
  добавить private local record и admission helpers → mocked/state tests; длительный deploy →
  фазы уже разделены, но TRANSFER всегда копирует и timings неполны → remote SHA skip/atomic
  partial + per-step milliseconds → lifecycle tests; protocol compatibility → один hash
  смешивает layout/semantics → generated schema/semantics/contract identities → protocol tests.

### Исходные findings, закрытые планом

- Сохранены уже существовавшие отдельные команды TRANSFER, INSTALL, START и RECOVERY;
  INSTALL оставляет runtime остановленным, START не выполняет rollback.
- P0 (закрыт): Quest/EV3 DEVICE runners требовали локальный `results/pre-install/report.json`, поэтому
  удаление disposable results блокирует независимую фазу.
- P0 (закрыт): Quest credential read/decrypt failure сворачивался в `credential_unavailable`, а
  START не различает `PROVISION_REQUIRED` и повреждённое persistent storage.
- P1 (закрыт): EV3 TRANSFER повторно передавал installer/start/device/recovery helpers с каждым build.
- P1 (закрыт): EV3 START запускал release-owned Wi-Fi autoconnect и мог ждать до 95 секунд вместо
  быстрой проверки provisioned platform network state.
- P1 (закрыт): EV3 host BUILD скрыто запускал `ctest`; cross BUILD по умолчанию строил оба profile.
- P1 (закрыт): CI и нормативные gates использовали удаляемое понятие PRE-INSTALL AUTO.
- P1 (закрыт): `quest-start.ps1` присваивал автоматической read-only переменной `$PID`.
- P2 (закрыт): `build-clean.ps1` не удалял Unity backup/intermediate directories и не имел `-All`.

## Решения

- ENGINEERING владеет фазами и user-intent mapping; TEST_PLAN владеет software/DEVICE/HIL
  классификацией; IMPLEMENTATION_STAGES только ссылается на эти gates.
- Maintenance tooling и pinned SSH trust являются persistent PROVISION state. Первоначальное
  решение использовать alias `phantom-ev3` заменено 2026-09-09 прямым стандартным hostname
  `ev3dev.local` для единственного назначенного brick. Обычный TRANSFER отправляет только
  exact package и сверяет SHA-256.
- Stage 3 требует CONTROL credential, но не commissioning credential и не motor I/O.
- Normal DEBUG START использует те же установленные bytes; Deep Debug — отдельный
  developer-only profile, запрещённый для qualification evidence.

## Проверка

- `python -m unittest discover -s tools -p 'test_*.py'` — PASS, 93 tests.
- `python ev3/network/test_phantom_network.py` — PASS, 13 tests.
- `powershell -NoProfile -ExecutionPolicy Bypass -File tools/test_pair_state.ps1` — PASS.
- `python tools/protocolgen.py --check`, `python tools/configgen.py --check`,
  `python tools/specgen.py --check`, `python tools/docindex.py --check`,
  `python tools/doclint.py` — PASS.
- `python tools/spec_contract_check.py`, `python tools/implementation_map_check.py`,
  `python tools/security_scan.py` — PASS.
- PowerShell parser — PASS для 22 changed/new scripts; Python syntax — PASS для 16 files;
  `bash -n` — PASS для 6 changed POSIX scripts; `git diff --check` — PASS.
- Protocol identities после final generation: schema
  `bbb1e01b5254bd81496d1be20e071a696bef5f79b1e580e60326d027fb79466c`, semantics
  `f05005639fb801bbaaa1ecc96f625d553f3c5c5557493d1c98142ec60373e228`, contract
  `73829128fe170d0fc71a7a04f48b19f37e4d8862bf539babcbb25f86c9a34cbe`.
- Quest/EV3 BUILD и все реальные hardware phases — `NOT_RUN` по явному ограничению задачи.

## Исторический итог до текущей миграции

- Нормативная модель, stage gates, scripts, CI, agent skills и generated документы переведены
  на независимые фазы без активного PRE-INSTALL-контракта.
- EV3 reproducibility TEST дал одинаковые `build_id` и SHA-256 двух пакетов.
- Quest reproducibility TEST дал одинаковый `build_id`; byte-level отличие точно локализовано в
  Unity per-build GUID metadata: `boot.config`, `globalgamemanagers`, `unity_app_guid` и четыре
  GUID-именованных entries с попарно одинаковым содержимым. Runner теперь сохраняет полный
  ZIP-entry diff в machine-readable report.
- Эти старые BUILD artifacts используют предыдущую identity и не готовы к установке после
  текущего protocol-contract изменения. В текущей задаче BUILD обоих компонентов `NOT_RUN`.
- DEVICE INTEGRATION TEST, HIL, manual acceptance и двух-APK credential persistence regression
  остаются `NOT_RUN` до следующего явного подключения устройств.
