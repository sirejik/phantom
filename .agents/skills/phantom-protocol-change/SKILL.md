---
name: phantom-protocol-change
description: "Изменить wire-протокол Quest↔EV3, EV3-local IPC, codecs или совместимость PHANTOM. Применяется к schema/layout, сообщениям, HMAC, session/transaction semantics, enum и bitfield."
---

# Изменение wire и IPC PHANTOM

Определи, меняется контракт или только его реализация. Выбери владельца:

| Изменение | Источник |
|---|---|
| Quest↔EV3 layout, enum, bits, widths, reserved bytes | `protocol/wire_schema.yaml` |
| Общие wire-visible session/auth/admission/validation semantics | `protocol/semantics.yaml` |
| EV3-local IPC layout и schema-representable значения | `protocol/ipc_schema.yaml` |
| Контекстные ограничения state/profile/bundle | owning component/protocol spec |
| Ошибка codec при неизменном контракте | production codec и regression vectors/tests |

Сначала измени источник контракта, затем производные артефакты. Не меняй schema, чтобы
узаконить ошибку codec. JCS используется из `protocol/jcs.py`.

```text
python tools/protocolgen.py
python tools/protocolgen.py --check
```

BUILD проверяет только machine artifacts. Generated Markdown проверяется отдельно
через `python tools/protocolgen.py --check --include-docs` в documentation gate.

Wire-изменение проверяется `tools/test_protocol.py`; IPC — `tools/test_ipc_contract.py`.
Общие golden/negative vectors должны проходить затронутыми production C++/C#/Python codecs;
выбирай их runners по [План проверки](../../../docs/test-plan.md), а не считай успешную
генерацию cross-language проверкой. Для parser/session/admission изменения проверь malformed
length, reserved/unknown values, NaN/Inf, replay и отсутствие side effects до authentication.

Wire structural hash и semantic hash совместно определяют `protocol_contract_hash`;
неизменные размеры/major/minor не доказывают совместимость. IPC имеет собственный schema hash.
Проверь зависимые config/build manifests. При изменении prose примени `phantom-spec-sync`.
В отчёте укажи изменившиеся identities, запущенные codecs/regressions и непроверенные device cases.
