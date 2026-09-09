# ADR-0002 — Compatibility gate Body provider на Quest

- **Статус:** ограничение принято; выбор provider остаётся открытым
- **Дата:** 2026-09-05

## Контекст

Полное user-control PHANTOM требует квалифицированной комбинации right-hand tracking,
right-shoulder Body Tracking и left Touch Plus при требуемом Multimodal lifecycle.

Evidence от 2026-09-05 показал, что `OVRBody` в Meta XR Core `205.0.0` отключается при
`SimultaneousHandsAndControllersEnabled`. Source-only inspection Meta XR Core `85.0.0`
обнаружил тот же guard; candidate Unity package имел SHA-1
`f8b4cfb2789f06cb55ea30b9a379bf52c98d1af3` и был получен из
`https://packages.unity.com/com.meta.xr.sdk.core`.

## Решение

Не ослаблять required input model PHANTOM только ради прохождения текущего provider.
Ни одна из проверенных комбинаций `OVRBody` не считается actuator-qualified.

Full-arm actuator path остаётся заблокированным, пока exact
Horizon/Unity/Meta package/provider matrix не пройдёт применимый P0 qualification.
Исторические experimental APK/device runs не считаются evidence для другой
build/spec/platform matrix.

## Последствия

Network-only работа может продолжаться, когда профиль явно не требует tracking inputs.
Full-arm user-driven actuator authority не может обходить P0 gate.

Exact run evidence хранится в versioned test/device reports и Git history; этот ADR фиксирует
решение, а не test report.

## Жизненный цикл evidence

Указанные версии и SHA-1 выше являются историческим rationale/locator исходного наблюдения,
но не текущим qualification evidence и не переносятся на другую exact Quest platform matrix.
Актуальный gate создаёт immutable P0 report с `quest_build_id`, `apk_sha256`, Horizon/runtime,
Unity и package lock identities. Новый provider/package/runtime либо изменение required input
mode инвалидирует применимость старого report и требует нового P0; ADR при этом меняется
только если изменилось архитектурное решение, а не для записи результата очередного запуска.
Если исторический artifact/report недоступен, его вывод остаётся контекстом решения, но его
статус для qualification — `NOT_RUN`, а не восстановленный PASS.
