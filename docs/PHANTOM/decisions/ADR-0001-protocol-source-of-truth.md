# ADR-0001 — Источник истины wire-протокола

- **Статус:** принято
- **Дата:** 2026-09-06

## Контекст

Более старый документ Quest↔EV3 описывал 48-byte CRC32 prototype. Этот формат не является PHANTOM protocol v1 и не должен сохраняться как альтернативная спецификация. Последняя ревизия дополнительно разделяет статическую структуру wire и контекстную semantic validation.

## Решение

`protocol/wire_schema.yaml` является каноническим source of truth **структуры** wire protocol: field order/types/widths, numeric enum/bit positions, fixed arrays, reserved bytes и exact payload lengths. `protocol/semantics.yaml` владеет стабильной machine-readable межреализационной semantics. Structural/semantic/contract canonical artifacts, C++14/C# constants/size maps, compile-time definitions, generated `protocol/protocol.md` и golden vectors являются производными.

Контекстные semantic ranges и transition guards, особенно зависящие от active `CommissioningBundle`/state/profile, принадлежат соответствующему normative prose и tests. Их нельзя искусственно превращать в один статический schema range.

Production C++/C#/Python serializers/deserializers **могут быть hand-written**. Они не являются отдельным source of truth и обязаны проходить общие cross-codec golden bytes и negative vectors. Ручное редактирование generated constants/size maps запрещено.

## Последствия

`protocol_schema_hash` покрывает только binary structure; `protocol_semantics_hash` покрывает semantic source; `protocol_contract_hash` детерминированно связывает оба и является handshake compatibility identity. Изменение любого source запускает generation, golden/negative vectors и applicable migration regressions. Stale generated metadata или codec/vector disagreement блокирует change/release.
