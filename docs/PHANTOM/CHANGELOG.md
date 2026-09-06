# История изменений документации PHANTOM

> **Тип:** ненормативный provenance. Requirements находятся в нормативном specification set.

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
