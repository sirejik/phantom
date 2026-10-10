---
name: phantom-quest-development
description: "Разрабатывать и исправлять приложение Quest 3: Unity/C#, SDK-адаптеры, Android bridge и lifecycle."
license: Apache-2.0
---

# Разработка Quest 3

Найди нужный [Quest-контракт](../../../docs/quest-specification.md) и adapter/consumer
в `PhantomQuest/Assets/Phantom/`. Стек — в
[engineering.md](../../../docs/engineering.md#sec-engineering-stack), C#/Unity правила — в
[правилах кода](../../../docs/code-guidelines.md#sec-code-guidelines-quest).

1. До изменения SDK-вызова сверь Editor и package locks. Найди установленный source в
   `PhantomQuest/Library/PackageCache` через `rg --files --no-ignore` либо embedded/local
   package из lock. Для Core ищи `OVRManager.cs`, для MRUK — `MRUK.cs`/`MRUKTrackable.cs`.
   Проверь сигнатуры и feature guards этой версии. Если source отсутствует, обозначь
   предел проверки; для неясного API используй официальные источники.
2. Найди существующий XR rig/provider и источник feature settings. Не выполняй SDK
   Fix All, смену provider/origin или обновление пакетов как побочную часть локальной правки.
3. Проследи входы через snapshots, mapping/IK и допуск движения. Выбери требования по
   активным `required_user_inputs` и scope: network-only, D-only, QR commissioning,
   full-arm имеют разные prerequisites.
4. Для tracking/lifecycle проверь validity/age/координаты, pause/resume, focus loss,
   смену reference space и повторные подписки. Для QR начни с `QrTrackingAdapter`
   и проверь обработку данных по Quest-спецификации.
5. Выполни подходящие EditMode/PlayMode tests через `python tooling test --target quest`.
   Для Android bridge проверь тесты Java/C# границы и обработку ошибок; поиск строк
   не доказывает JNI/Keystore/NSD. Отсутствующее покрытие укажи явно.
6. Для package/manifest/IL2CPP изменений выполни BUILD и проверь итоговый manifest штатным
   tooling. Реальные tracking/QR/haptics и Android runtime проверяются по
   [плану тестирования](../../../docs/test-plan.md), с разделением автоматических
   проверок лежащего шлема и ручных сценариев.

Работа на устройстве — через [phantom-hardware-gate](../phantom-hardware-gate/SKILL.md).
Инструкции адаптированы из материалов Meta Platforms, Inc.; лицензия — [LICENSE](LICENSE).
