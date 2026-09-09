# Текущее состояние реализации PHANTOM

> **Ревизия состояния:** 2026-09-10.
> **Тип:** ненормативное summary. Источником PASS/FAIL является опубликованный immutable
> machine-readable report с candidate/artifact hashes; локальный `results/**` не является
> долговечным хранилищем и не коммитится.

## Lifecycle/build state

Lifecycle переведён на явные независимо запускаемые фазы:

```text
TEST → BUILD → PROVISION → TRANSFER → INSTALL → START → DEBUG
     → DEVICE INTEGRATION TEST → HIL → MANUAL ACCEPTANCE → RECOVERY
```

- `PHANTOM-BUILD-V3` вычисляет component/profile-specific `build_id` из точных входов и compatibility `protocol_contract_hash`;
- текущие generated protocol identities: schema `bbb1e01b…`, semantics `f0500563…`,
  contract `73829128…`; normative specification identity `03b05e82…`;
- Git commit/dirty state остаются provenance и не меняют identity bytes;
- BUILD, TRANSFER, INSTALL, START и DEVICE INTEGRATION TEST не читают отчёты предыдущих фаз;
- INSTALL проверяет выбранные bytes и embedded identity, но не строит и не тестирует;
- START запускает уже установленное и не выполняет provisioning/recovery;
- единственный назначенный EV3 обслуживается напрямую через `ev3dev.local` с pinned SSH
  fingerprint; отдельный alias и сохранённый IP штатному deploy не нужны;
- `build/**` и `results/**` являются удаляемыми локальными outputs;
- долговечное qualification evidence публикуется отдельно как immutable artifact.

Исторические Diagnostic BUILD/reproducibility results относятся к предыдущей protocol/build
identity и не являются artifacts текущей миграции. В текущей задаче BUILD Quest и EV3 —
`NOT_RUN`; TRANSFER, INSTALL, START, DEBUG START, DEVICE INTEGRATION TEST, HIL, MANUAL
ACCEPTANCE и RECOVERY — `NOT_RUN`. После изменения protocol contract новых installable
artifacts пока нет. Выполнены только off-hardware source/generator/unit/security/doc checks,
перечисленные в active execution plan.

## Stage 3

Stage 3 остаётся **NOT COMPLETE**. DEVICE INTEGRATION TEST, real Quest↔EV3 integration, HIL и
manual acceptance для нового lifecycle не запускались и имеют статус `NOT_RUN`.

После успешной off-hardware подготовки и явного подключения устройств порядок следующий:

```text
PROVISION (только если состояние отсутствует/повреждено)
→ EV3 TRANSFER + INSTALL / Quest INSTALL
→ START либо DEBUG START
→ DEVICE INTEGRATION TEST
→ применимые hardware acceptance cases
```

Отсутствие motor A допустимо для Stage-3 network-only Diagnostic profile с authoritative
`actuator_scope_mask=safety_observation_mask=0x00`. Hardware PASS из source review,
симуляции, BUILD или TEST не выводится.
