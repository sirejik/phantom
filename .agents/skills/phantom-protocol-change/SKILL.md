---
name: phantom-protocol-change
description: "Изменять wire/IPC схемы, семантику, кодеки или совместимость Quest↔EV3 и проверять производные артефакты."
---

# Изменение протокола и IPC

Определи, меняется контракт или только его реализация. Владение задано в
[правилах спецификации](../../../docs/specification-governance.md#sec-specification-governance-2).

| Изменение | Начать с |
|---|---|
| Wire layout, enum, bits, widths | `protocol/wire_schema.yaml` |
| Межреализационная семантика | `protocol/semantics.yaml` |
| EV3-local IPC | `protocol/ipc_schema.yaml` |
| Контекстные state/profile/bundle ограничения | Спецификация протокола или компонента |
| Ошибка codec при неизменном контракте | Production codec и регрессионные vectors/tests |

1. При изменении контракта исправь его источник и пересоздай производные файлы.
   При исправлении codec сохрани контракт; не меняй schema для оправдания ошибки.
2. Выполни `python tools/protocolgen.py`, затем `python tools/protocolgen.py --check`.
   Generated Markdown проверь отдельно через `--check --include-docs`.
3. Для wire запускай `tools/test_protocol.py`, для IPC — `tools/test_ipc_contract.py`.
   Выполни общие golden/negative vectors затронутыми production codecs: генерация
   не подтверждает совместимость языков. Для parser/session/admission проверь malformed
   length, reserved/unknown values, NaN/Inf, replay и действия до аутентификации.
4. Проверь изменения hashes и зависимые config/build artifacts по
   [техническим контрактам](../../../docs/engineering-contracts.md).
   Изменения документации проведи через [phantom-spec-sync](../phantom-spec-sync/SKILL.md).

Укажи изменённые identities, проверенные codecs/regressions и непроверенные device cases.
