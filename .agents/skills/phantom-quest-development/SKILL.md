---
name: phantom-quest-development
description: "Разрабатывать и отлаживать приложение PHANTOM для Meta Quest 3 на Unity/C#, OpenXR, Meta XR и MRUK; Android Java bridge, tracking, QR, lifecycle и UI. Для физической установки и P0 используй hardware workflow."
license: Apache-2.0
---

# Quest 3: Unity, C# и Android

Сначала прочитай нужный раздел [Quest spec](../../../docs/quest-specification.md)
и существующий adapter/consumer в `PhantomQuest/Assets/Phantom/`.
Языковые и Unity-ограничения: [C# и assets](references/unity-csharp.md).

## SDK и конфигурация

- Версию Editor бери из `PhantomQuest/ProjectSettings/ProjectVersion.txt`, пакеты — из
  `Packages/manifest.json` и `Packages/packages-lock.json` внутри Unity-проекта.
  Пример из Интернета не является разрешением обновить pinned stack.
- Найди фактический package root в `PhantomQuest/Library/PackageCache` (он ignored, для поиска
  может понадобиться `rg --files --no-ignore`) либо embedded/local package из lock.
  Для Core ищи `OVRManager.cs`, для MRUK — `MRUK.cs`/`MRUKTrackable.cs`.
  Проверяй сигнатуры и feature guards в этой revision, затем используй официальную
  документацию Meta/Unity/Khronos для неясных API. Если source не установлен, явно отметь
  предел проверки; не выдавай API из latest docs за проверенный на pinned package.
- Сохрани существующий XR rig/provider. Автоматические SDK Fix All, добавление второго rig,
  включение room mesh, raw camera access или смена tracking origin не являются обычной
  частью исправления adapter.
- При изменении feature/permission проверь источник настроек и итог merged Android manifest
  через существующий build/audit path. Не редактируй generated Gradle/APK outputs.

## Входы и lifecycle

Найди активный `required_user_inputs` и scope до изменения readiness. Network-only,
QR commissioning, D-only и full-arm используют разные входы; отсутствие Body Tracking
не должно превращаться в prerequisite network-only/D-only.

Сохраняй в snapshots validity, timestamp/age, систему координат и источник данных.
Разделяй SDK callback, pure mapping/IK и motion permission. Отдельно проверь focus loss,
pause/resume, reference-space change, stale/unaligned samples и повторную подписку на events.
Не добавляй silent provider fallback или HMD→shoulder эвристику.

Для QR используй существующий `QrTrackingAdapter` и MRUK Trackables. Проверь payload,
tracking validity, единицы, координатный adapter и stationary measurement acceptance.
Sample scene с synthetic fallback не может стать источником реального actuator input.

## Проверка

Чистую математику/state logic проверяй существующими EditMode/replay tests;
Unity assets и adapters — применимыми EditMode/PlayMode tests через
`scripts/phantom.cmd TEST QUEST`. Для Android bridge найди профильный checker в `tools/`
и тесты Java/C# границы; JNI/Keystore/NSD lifecycle не доказывается компиляцией C#.
BUILD нужен при затронутых package/manifest/IL2CPP inputs и выполняется отдельно.
P0/live tracking/QR/permissions на реальном Quest остаются отдельными cases TEST_PLAN.

Этот skill не требует Unity CLI/MCP/metavr и не устанавливает их автоматически.
[Источники и изменения относительно upstream](SOURCE.md) нужны при обновлении skill.
