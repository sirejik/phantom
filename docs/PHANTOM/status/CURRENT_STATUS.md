# Текущее состояние реализации PHANTOM

> **Ревизия состояния:** 2026-09-09.
> **Тип:** ненормативное summary. Источником PASS/FAIL является опубликованный immutable
> machine-readable report с candidate/artifact hashes; локальный `results/**` не является
> долговечным хранилищем и не коммитится.

## Lifecycle/build state

Lifecycle переведён на явные независимо запускаемые фазы:

```text
TEST → BUILD → PROVISION → TRANSFER → INSTALL → START → DEBUG
     → DEVICE INTEGRATION TEST → HIL → MANUAL ACCEPTANCE → RECOVERY
```

- `PHANTOM-BUILD-V2` вычисляет component/profile-specific `build_id` из точных входов;
- Git commit/dirty state остаются provenance и не меняют identity bytes;
- BUILD, TRANSFER, INSTALL, START и DEVICE INTEGRATION TEST не читают отчёты предыдущих фаз;
- INSTALL проверяет выбранные bytes и embedded identity, но не строит и не тестирует;
- START запускает уже установленное и не выполняет provisioning/recovery;
- `build/**` и `results/**` являются удаляемыми локальными outputs;
- долговечное qualification evidence публикуется отдельно как immutable artifact.

Применимый off-hardware regression завершён. Diagnostic BUILD обоих компонентов и
reproducibility TEST выполнены; итоговые артефакты готовы к явным TRANSFER/INSTALL после
подключения устройств. EV3 package воспроизводится побайтово. Quest сохраняет одинаковый
content-derived `build_id`, но Unity меняет per-build GUID metadata; точные различия фиксирует
reproducibility report и они не скрываются как равенство APK bytes.

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
