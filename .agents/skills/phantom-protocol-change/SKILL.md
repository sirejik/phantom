---
name: phantom-protocol-change
description: "Изменять wire/IPC схемы, семантику, кодеки или совместимость Quest↔EV3 и проверять производные артефакты."
---

# Изменение протокола и IPC

Определи, меняется контракт или только его реализация. Владение задано в
[правилах спецификации](../../../docs/specification-governance.md#sec-specification-governance-2).

| Изменение | Начать с |
|---|---|
| Wire layout, enum, bits, widths | `config/shared/protocol/wire-schema.json` |
| Межреализационная семантика | `config/shared/protocol/semantics.json` |
| EV3-local IPC | `config/shared/protocol/ipc-schema.json` |
| Контекстные state/profile/bundle ограничения | Спецификация протокола или компонента |
| Ошибка codec при неизменном контракте | Production codec и регрессионные vectors/tests |

1. При изменении контракта исправь его источник и пересоздай производные файлы.
   При исправлении codec сохрани контракт; не меняй schema для оправдания ошибки.
2. Выполни `python tooling generate --target protocol`, затем `python tooling check --target schemas`.
   Generated Markdown также проверяется командой `check --target docs`.
3. Выполни `python tooling self-test` для wire и IPC.
   Выполни общие golden/negative vectors затронутыми production codecs: генерация
   не подтверждает совместимость языков. Для parser/session/admission проверь malformed
   length, reserved/unknown values, NaN/Inf, replay и действия до аутентификации.
4. Проверь изменения hashes и зависимые config/build artifacts по
   [техническим контрактам](../../../docs/tooling.md).
   Изменения документации проведи через [phantom-spec-sync](../phantom-spec-sync/SKILL.md).

Укажи изменённые identities, проверенные codecs/regressions и непроверенные device cases.
