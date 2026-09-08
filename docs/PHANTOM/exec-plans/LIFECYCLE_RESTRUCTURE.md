# Переработка lifecycle PHANTOM

> **Тип:** execution plan; ненормативный
> **Область:** TEST/BUILD/PROVISION/TRANSFER/INSTALL/START/DEBUG/DEVICE INTEGRATION TEST/HIL/MANUAL ACCEPTANCE/RECOVERY
> **Начало:** 2026-09-08, `faa493af`
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
- Сохраняются content-addressed `PHANTOM-BUILD-V2`, artifact hashes, safe install,
  zero-output, privilege separation, explicit recovery и fail-closed authentication.
- `results/**` и `build/**` остаются удаляемыми локальными outputs; credentials, SSH trust и
  Wi-Fi profile относятся только к PROVISION.
- Один итоговый commit выполняется только после off-hardware проверок.

## Этапы работы

- [x] M1 — аудит старых lifecycle-зависимостей и сохранённых хороших границ
- [x] M2 — нормативная модель и stage/test gates синхронизированы
- [x] M3 — TEST/BUILD/PROVISION/deploy/debug tooling реализован по новой модели
- [x] M4 — regressions, skills и generated documentation синхронизированы
- [x] M5 — максимально применимая off-hardware validation и cleanup завершены; итоговый commit выполняется последним действием

## Журнал прогресса

- Сохранены уже существовавшие отдельные команды TRANSFER, INSTALL, START и RECOVERY;
  INSTALL оставляет runtime остановленным, START не выполняет rollback.
- P0: Quest/EV3 DEVICE runners требуют локальный `results/pre-install/report.json`, поэтому
  удаление disposable results блокирует независимую фазу.
- P0: Quest credential read/decrypt failure сворачивается в `credential_unavailable`, а
  START не различает `PROVISION_REQUIRED` и повреждённое persistent storage.
- P1: EV3 TRANSFER повторно передаёт installer/start/device/recovery helpers с каждым build.
- P1: EV3 START запускает release-owned Wi-Fi autoconnect и может ждать до 95 секунд вместо
  быстрой проверки provisioned platform network state.
- P1: EV3 host BUILD скрыто запускает `ctest`; cross BUILD по умолчанию строит оба profile.
- P1: CI и нормативные gates всё ещё используют удаляемое понятие PRE-INSTALL AUTO.
- P1: `quest-start.ps1` присваивает автоматической read-only переменной `$PID`.
- P2: `build-clean.ps1` не удаляет Unity backup/intermediate directories и не имеет `-All`.

## Решения

- ENGINEERING владеет фазами и user-intent mapping; TEST_PLAN владеет software/DEVICE/HIL
  классификацией; IMPLEMENTATION_STAGES только ссылается на эти gates.
- Maintenance target `phantom-ev3` и maintenance tooling являются persistent PROVISION
  state. Обычный TRANSFER отправляет только exact package и сверяет SHA-256.
- Stage 3 требует CONTROL credential, но не commissioning credential и не motor I/O.
- Normal DEBUG START использует те же установленные bytes; Deep Debug — отдельный
  developer-only profile, запрещённый для qualification evidence.

## Проверка

- Targeted unit/static/script regressions для всех новых фазовых инвариантов.
- Generated protocol/config/spec/index checks, documentation lint и repository-wide поиск
  удалённого активного контракта.
- Off-hardware builds/tests; реальные hardware gates: `NOT_RUN` по явному ограничению задачи.

## Итог проверки

- Нормативная модель, stage gates, scripts, CI, agent skills и generated документы переведены
  на независимые фазы без активного PRE-INSTALL-контракта.
- EV3 reproducibility TEST дал одинаковые `build_id` и SHA-256 двух пакетов.
- Quest reproducibility TEST дал одинаковый `build_id`; byte-level отличие точно локализовано в
  Unity per-build GUID metadata: `boot.config`, `globalgamemanagers`, `unity_app_guid` и четыре
  GUID-именованных entries с попарно одинаковым содержимым. Runner теперь сохраняет полный
  ZIP-entry diff в machine-readable report.
- Полный применимый off-hardware suite и Diagnostic BUILD обоих компонентов выполнены; точные
  итоговые identities и hashes фиксируются соседними BUILD result/manifest.
- DEVICE INTEGRATION TEST, HIL, manual acceptance и двух-APK credential persistence regression
  остаются `NOT_RUN` до следующего явного подключения устройств.
