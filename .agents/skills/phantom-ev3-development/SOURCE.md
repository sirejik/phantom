# Источники и локальная адаптация

Проверено 2026-10-06. Локальная редакция для PHANTOM; не является неизменённым upstream skill.

- [cpp-pro](https://github.com/Jeffallan/claude-skills/blob/1be15d8064f88fc25216442406d40add8fd23b53/skills/cpp-pro/SKILL.md), SHA-256 исходного SKILL.md: `53017f862c526df6080210a1a00e6678c2cd5382b5d1a51026bf3b0bde7f7ed2`.
- [embedded-systems](https://github.com/Jeffallan/claude-skills/blob/1be15d8064f88fc25216442406d40add8fd23b53/skills/embedded-systems/SKILL.md), SHA-256 исходного SKILL.md: `536161470752d40a2bfc3ec4b17ab5c34fd3593a8960bf8089b0ea59b6ddec1f`.

Проверены указанные entrypoints. Их executable scripts, references, plugin hooks и MCP
конфигурация не импортированы. Лицензия upstream сохранена в [LICENSE](LICENSE).

Сохранены проверка compiler/target, ownership/RAII, bounded resource use и проверка timing.
C++20/23, concepts/SIMD defaults и MCU/ISR/FreeRTOS templates исключены. Добавлены C++14,
Linux userspace, ev3dev MotorBackend/IPC и Python 3.5. Готовый подходящий EV3 Agent Skill
в выполненном поиске GitHub не найден; device-specific часть написана по репозиторию PHANTOM
и официальному ev3dev tacho-motor API.

При обновлении сравни pinned revision с новой, проверь API/зависимости и локальные
ограничения; автоматическая замена на latest не выполняется.
