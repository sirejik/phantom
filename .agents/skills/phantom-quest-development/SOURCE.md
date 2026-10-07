# Источники и локальная адаптация

Проверено 2026-10-06. Локальная редакция для PHANTOM; не является неизменённым upstream skill.

- [hz-unity-meta-core-sdk](https://github.com/meta-quest/agentic-tools/blob/3a8553d10a5a1bd1bf9beaaa950243fbbed3b9ea/skills/hz-unity-meta-core-sdk/SKILL.md), SHA-256 исходного SKILL.md: `622554adba456d23d019a063c0297c9987af37d121b3bc0f383de6cb0d03a969`.
- [hz-unity-meta-mixed-reality-utility-kit](https://github.com/meta-quest/agentic-tools/blob/3a8553d10a5a1bd1bf9beaaa950243fbbed3b9ea/skills/hz-unity-meta-mixed-reality-utility-kit/SKILL.md), SHA-256 исходного SKILL.md: `ffb5cca0c57b6f8ef85b67182581fa913b8c3eab875d472c8bac7c1ee1d07294`.

Проверены указанные entrypoints. Их executable scripts, references, plugin hooks и MCP
конфигурация не импортированы. Лицензия upstream сохранена в [LICENSE](LICENSE).

Сохранены приёмы поиска pinned SDK source, проверки feature settings/manifest и persisted
serialized changes. Убраны live-Editor-only workflow, обязательные unity-cli/metavr,
Fix All, автоматический build/install и sample room/raw-camera defaults. Добавлены PHANTOM
scope/readiness, C# assembly/IL2CPP, JNI и offline-vs-device verification boundaries.
`hz-quest-verify-first` рассмотрен на уровне entrypoint и не включён: обязательный внешний CLI
и catch-all activation не нужны для каждой локальной правки. `csharp-developer` из Jeffallan
не импортирован: он ориентирован на .NET 8/ASP.NET, а проект использует Unity.

При обновлении сравни pinned revision с новой, проверь API/зависимости и локальные
ограничения; автоматическая замена на latest не выполняется.
