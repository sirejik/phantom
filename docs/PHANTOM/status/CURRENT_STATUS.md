# Текущее состояние реализации PHANTOM

> **Ревизия состояния:** 2026-09-08.
> **Тип:** ненормативное summary. Источником PASS/FAIL является опубликованный immutable
> machine-readable report с candidate/artifact hashes; локальный `results/**` не является
> долговечным хранилищем и не коммитится.

## Build/evidence workflow

В рабочем дереве выполняется переход на `PHANTOM-BUILD-V2`:

- `build_id` является content-addressed identity по component/profile и точным
  source/spec/protocol/config/toolchain inputs;
- Git commit и dirty-state остаются только provenance и не меняют `build_id`;
- BUILD, TRANSFER, INSTALL и START не читают локальные отчёты предыдущих фаз;
- INSTALL проверяет выбранный artifact/sidecar/embedded hashes и оставляет EV3 runtime
  остановленным;
- PRE-INSTALL остаётся обязательным для DEVICE/HIL/Release qualification exact artifact
  bytes, но не блокирует инженерную установку;
- локальные runner outputs пишутся в игнорируемый Git каталог `results/**`, а долговечное
  evidence публикуется отдельно.

После завершения этой правки требуется собрать новые Quest/EV3 artifacts: старые manifests
используют `PHANTOM-BUILD-V1` и несовместимы с новым validation contract.

## Stage 3

Stage 3 остаётся **NOT COMPLETE**. Для текущего дерева отсутствует опубликованный exact
candidate PRE-INSTALL/DEVICE/HIL evidence. Предыдущие локальные отчёты удалены по новой
retention policy и не переносятся на новый build.

После готовности устройств требуется выполнить раздельно:

```text
BUILD
→ PRE-INSTALL AUTO exact artifacts
→ Quest INSTALL / EV3 TRANSFER + INSTALL
→ START
→ DEVICE AUTO
→ применимые hardware acceptance cases
```

Отсутствие motor A допустимо только для Stage-3 network-only profile с authoritative
`actuator_scope_mask=safety_observation_mask=0x00`; hardware PASS из source review или
simulation не выводится.
