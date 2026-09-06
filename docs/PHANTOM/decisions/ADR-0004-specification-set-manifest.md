# ADR-0004 — Разделённая спецификация с generated manifest

- **Статус:** принято
- **Дата:** 2026-09-05

## Контекст

Предыдущая монолитная спецификация объёмом более 8 тысяч строк смешивала product requirements,
architecture, Quest, EV3, mechanics, protocol, build/release rules, testing,
implementation stages и reference material. Это увеличивало agent context и смешивало
документы с разными жизненными циклами.

При этом protocol/build contract уже использует один `specification_sha256`.

## Решение

Разделить human system of record по primary ownership. Сохранить
`docs/PHANTOM_SPECIFICATION.md` как небольшой generated manifest, а не монолитный source.
`tools/specgen.py` проверяет UTF-8 без BOM и LF line endings, вычисляет hashes **точных bytes** каждого нормативного документа из `docs/PHANTOM/spec-set.json` и записывает ordered path+hash list в manifest. Существующий `specification_sha256` остаётся SHA-256 точных bytes этого manifest; hidden normalization перед hashing запрещена.

Нормативные определения implementation stages/gates остаются частью specification set в
`IMPLEMENTATION_STAGES.md`. Current status, task-specific exec plans, ADRs, risk records,
changelog и external-reference notes не входят в specification identity.

## Последствия

Agents могут загружать только нужные разделы через progressive disclosure. Один существующий
hash продолжает связывать полный нормативный specification baseline, а
`protocol_schema_hash` и другие component hashes сохраняют более узкие machine/runtime
identities. Нормативная правка требует regeneration manifest; CI обязан запускать
`specgen.py --check`.
