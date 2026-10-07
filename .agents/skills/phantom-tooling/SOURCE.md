# Источники и локальная адаптация

Проверено 2026-10-06. Локальная редакция для PHANTOM; не является неизменённым upstream skill.

- [python-pro](https://github.com/Jeffallan/claude-skills/blob/1be15d8064f88fc25216442406d40add8fd23b53/skills/python-pro/SKILL.md), SHA-256 исходного SKILL.md: `b94b59450d7372ac0cf47c7313a189796a5a7b0470552b2fe9e9581ec6c3de04`.

Проверены указанные entrypoints. Их executable scripts, references, plugin hooks и MCP
конфигурация не импортированы. Лицензия upstream сохранена в [LICENSE](LICENSE).

Сохранены анализ окружения, явные ошибки, context managers и изолированные tests.
Исключены Python 3.11+, async-first, обязательные Poetry/pytest/mypy/black/ruff и произвольный
coverage threshold. Добавлены host/device compatibility, PowerShell/POSIX process boundaries,
encoding, exact artifact bytes и существующие PHANTOM runners.

При обновлении сравни pinned revision с новой, проверь API/зависимости и локальные
ограничения; автоматическая замена на latest не выполняется.
