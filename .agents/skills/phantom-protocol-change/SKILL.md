---
name: phantom-protocol-change
description: Изменить PHANTOM Quest↔EV3 protocol/wire semantics ("wire_schema", HELLO, TELEMETRY, COMMAND, HMAC, enum/bit/layout). Использовать schema-first; generated constants/size maps не редактировать вручную, production codecs проверять общими vectors.
---

# Изменение протокола PHANTOM

1. Прочитай только relevant sections
   `docs/PHANTOM/PROTOCOL_SPECIFICATION.md`, `docs/PHANTOM/SAFETY.md`,
   `docs/PHANTOM/TEST_PLAN.md` и `protocol/wire_schema.yaml`.
2. Классифицируй изменение: статическая wire structure, contextual behavioral/session semantics, production codec implementation или их комбинация.
3. Для field order/type/width, enum numeric values/bit positions, reserved bytes и fixed payload length сначала измени `protocol/wire_schema.yaml`. Для wire-visible authentication/session/admission/authority/validation semantics сначала измени `protocol/semantics.yaml`; contextual component rules вне общего wire contract меняй в owning normative prose/tests.
4. Generated full/structural/semantic/contract projections, hashes, constants и size maps являются производными. Production C++/C#/Python codecs могут быть hand-written, но не являются source of truth.
5. Запусти:
   `python tools/protocolgen.py`
   `python tools/protocolgen.py --check`
   `python tools/test_protocol.py`
6. Обнови cross-language golden/negative vectors и parser/HMAC/malformed/replay tests; каждым production codec декодируй/проверяй общие bytes.
7. `docs/PHANTOM/PROTOCOL_SPECIFICATION.md` обновляй для contextual behavioral semantics, которые не являются статической structural schema. Не создавай competing offsets/packet-size owner.
8. Считай semantic changes compatibility changes даже если fixed payload sizes и numeric
   major/minor не изменились: `protocol_schema_hash` меняется только от structural projection,
   `protocol_semantics_hash` — от canonical semantic source, а handshake/build compatibility
   использует derived `protocol_contract_hash`, связывающий оба значения.
9. Проверь auth-before-state-change, session/sequence/transaction ordering,
   reserved/unknown validation, finite/range checks и fail-closed behavior.
10. Запусти более широкие Quest/EV3 network regressions, требуемые
    `docs/PHANTOM/TEST_PLAN.md`.
11. Если изменился нормативный prose, regenerate/check PHANTOM spec/index/docs.
12. В отчёте укажи old/new schema/semantics/contract identities и real-device gates, которые остаются
    `NOT_RUN`.
