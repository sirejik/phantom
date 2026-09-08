# История изменений документации PHANTOM

> **Тип:** ненормативный provenance. Requirements находятся в нормативном specification set.

## 2026-09-09 — явный lifecycle без скрытых фаз

Lifecycle переработан в независимые `TEST`, `BUILD`, `PROVISION`, `TRANSFER`, `INSTALL`,
`START`, `DEBUG`, `DEVICE INTEGRATION TEST`, `HIL`, `MANUAL ACCEPTANCE` и `RECOVERY`.
Активная PRE-INSTALL-фаза удалена; её полезные software regressions принадлежат TEST/CI, а
дешёвая проверка exact artifact выполняется самим BUILD. `results/**` и `build/**` являются
удаляемыми локальными outputs и не управляют допуском установки уже выбранных bytes.

EV3 maintenance trust/helpers и Wi-Fi autoconnect вынесены в явный persistent PROVISION.
TRANSFER передаёт только пакет и сверяет SHA-256; INSTALL валидирует и атомарно выбирает
release, оставляя runtime остановленным; START имеет bounded per-service порядок и сохраняет
первый непосредственный отказ без автоматического rollback. DEVICE INTEGRATION TEST и recovery
запускаются только явно.

Quest обновляется через `adb install -r`, сохраняет стабильные package/storage/Keystore names и
различает отсутствующий credential (`PROVISION_REQUIRED`) от повреждённого (`PROVISION_CORRUPT`).
BUILD проверяет фактическую APK-подпись и фиксирует SHA-256 сертификата. Unity Development Build
ограничен `DeepDebug`; обычный Diagnostic использует тот же runtime с профильными engineering
поверхностями без profiler/debugger instrumentation. Reproducibility TEST подтвердил одинаковую
identity обоих Quest builds и локализовал оставшийся Unity per-build GUID nondeterminism в
`boot.config`, `globalgamemanagers`, `unity_app_guid` и GUID-именованных entries с одинаковым
содержимым. EV3 package воспроизводится побайтово.

## 2026-09-05 — проверенный монолитный baseline

Проверенная исходная спецификация фиксировала устранение противоречий вокруг TCP/Gripper QR
geometry, signed Shoulder QR-angle, Gripper safe-open calibration, LOCAL_STOP takeover,
payload UNKNOWN/contact transition, UDP config-commit recovery, CommissioningBundle
deployment/hash semantics и связанных test/wire contracts.

Также были зафиксированы conventions документации Markdown: Mermaid diagrams хранятся inline;
state/message/class/config/technology identifiers сохраняют canonical technical spelling, а
не переводятся и не переименовываются косметически.

## 2026-09-05 — разделение по ownership

Проверенный монолит разделён по ownership. Runtime requirements остаются нормативными;
implementation stage definitions вынесены в `IMPLEMENTATION_STAGES.md`; task-specific work —
в `exec-plans/`; current state — в `status/`; rationale — в ADR; open disposition — в
`risks/`. Старый путь `docs/PHANTOM_SPECIFICATION.md` теперь содержит generated manifest,
который транзитивно связывает нормативный набор для существующего
`specification_sha256`.

## 2026-09-06 — синхронизация после реализации Stage-3/network hardening

Обновлённая монолитная спецификация внесла 11 точечных изменений: уточнила ownership wire schema против contextual semantics и hand-written production codecs; зафиксировала exact `ControllerRequestV1`/`ControllerReplyV1` Stage-3 IPC contract и runtime socket ownership/path; разделила unqualified Release authoring candidate и production packaging gate; изменила `specification_sha256` на hash exact Git bytes без hidden normalization; централизовала `build_id` canonicalization в host tooling; зафиксировала Android AES-GCM/Keystore credential implementation; добавила `HELLO.capabilities_requested=0`/`ERR_UNSUPPORTED` semantics и обновила cross-codec/code-generation gates.

При разбиении также устранены две stale формулировки внутри самой обновлённой монолитной версии, которые всё ещё говорили о `generated codecs`: `TEST_PLAN` и protocol ownership policy §11.8 теперь согласованы с разрешёнными hand-written production codecs и generated constants/size maps.

## 2026-09-07 — remediation независимого аудита

Закрыты findings независимого audit snapshot. Нормативные изменения:

- §7.21 и §5.19 больше не содержат конкурирующую структуру конфигурации: schema/source
  объявлены единственным владельцем структуры, prose описывает смысл, поля будущих этапов
  помечены явно (§7.21.2, §5.19.2).
- §7.2.2 зафиксировал `TELEMETRY_QUERY`/`ControllerTelemetrySnapshotV1` как единственный
  источник состояния для wire `TELEMETRY`, canonical-zero правила по типам сообщений,
  session watchdog и запрет чтения motor/power sysfs из `phantom-network`.
- §7.24 дополнен двухуровневой политикой превышения периода цикла, latched `STOPPED` без
  завершения процесса и наблюдаемостью исчезнувшего controller.
- §4.6 требует нормализации DNS-SD service type до `_service._proto`.
- §8.1 приведён к фактическому дереву репозитория, добавлены §8.1.1 (среда разработчика) и
  граница `ev3/bench` как непроизводственной оснастки; §8.5 разделил роли PRE-INSTALL и CI;
  §8.11.1 описал реализованный путь provisioning CONTROL PSK.
- Единицы duty приведены к `permille` во всех документах; путь bundle-схемы исправлен.
- `protocol/protocol.md` стал действительно generated; добавлена нормативная
  `protocol/ipc_schema.yaml`.
- `gripper_capabilities` получил определение битов в wire schema
  (`GRIPPER_PRESENT`, `GRIPPER_REFERENCE_CAPABLE`, `0 = none`).

Изменение wire schema (новый bitfield) дало новый `protocol_schema_hash`; все зависимые
generated артефакты, config hashes и `specification_sha256` перегенерированы. Предыдущие
build/PASS identities остаются только provenance.

## 2026-09-08 — content-addressed build identity и локальное evidence

`PHANTOM-BUILD-V2` исключил Git commit из build identity: commit/dirty-state сохранены только
как provenance, а `build_id` зависит от точных component source/spec/protocol/config/toolchain
inputs. BUILD, TRANSFER, INSTALL и START больше не используют result-файлы предыдущих фаз как
управляющее состояние; PRE-INSTALL остаётся отдельным exact-artifact gate перед
DEVICE/HIL/Release qualification. `results/**` переведён в локальное/CI Git-ignored workspace,
а долговечное evidence публикуется как immutable artifact с URI и SHA-256.

## 2026-09-06 — software/build audit Stage 1–3 завершён

На clean commit `eb1339842045548c7224e2a8ae4da7b5158b9508` агент завершил аудит
спецификации и реализацию Stage 1–3. Исправлено 8 проблем спецификации и 13 групп
implementation/build defects. `PRE-INSTALL AUTO -Stage 3` завершился `PASS` (20/20
обязательных checks), protocol cross-codec golden vectors — `21/21 PASS`,
`protocol_schema_hash=48d85291e972cb6a954c7a8549349ba28c39f8f5b411d8e2a056f64bfb3317e3`.

Real Quest 3, новый EV3 build и Quest↔EV3 physical integration не запускались и остаются
`NOT_RUN`; Stage 3 physical acceptance остаётся `NOT COMPLETE`.

Этот результат был получен до split-spec migration при monolithic
`specification_sha256=419d936d5ddede106332d46abac98e0650de6b90aee0d86f898bc757826c7e3d`.
После перехода на generated split manifest software/build gate должен быть повторён, потому
что specification identity входит в build identity.
