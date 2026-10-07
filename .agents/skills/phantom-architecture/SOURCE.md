# Источники и локальная адаптация

Проверено 2026-10-06. Локальная редакция для PHANTOM; не является неизменённым upstream skill.

- [architecture-designer](https://github.com/Jeffallan/claude-skills/blob/1be15d8064f88fc25216442406d40add8fd23b53/skills/architecture-designer/SKILL.md), SHA-256 исходного SKILL.md: `d8f3d98c54bbf35ad07e068c7ae4c9b570a3e0e51041d7669e91e8593a7655c7`.

Проверены указанные entrypoints. Их executable scripts, references, plugin hooks и MCP
конфигурация не импортированы. Лицензия upstream сохранена в [LICENSE](LICENSE).

Сохранены requirements → варианты → trade-offs → failure modes → проверяемое решение.
Убраны вымышленная роль «15+ лет», web-scale template, обязательный ADR-каталог и отдельное
универсальное согласование каждого решения. Добавлены authority/timing/state ownership
телемеханической системы и запись rationale в owning specification.

При обновлении сравни pinned revision с новой, проверь API/зависимости и локальные
ограничения; автоматическая замена на latest не выполняется.
