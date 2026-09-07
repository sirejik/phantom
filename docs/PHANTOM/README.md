# Документация PHANTOM

Этот каталог — структурированный system of record проекта PHANTOM. Загружай только
информацию, необходимую для текущей задачи.

Нормативные роли и правила разрешения конфликтов определены в
[`SPECIFICATION_GOVERNANCE.md`](SPECIFICATION_GOVERNANCE.md). Нельзя выводить authority из
размера файла, его возраста, текущего поведения кода или status/task-plan документа.

## Быстрая карта

| Что нужно | Что читать |
|---|---|
| цели / FR / NFR | `PRODUCT_REQUIREMENTS.md` |
| границы системы / states / flows | `SYSTEM_ARCHITECTURE.md` |
| поведение Quest | `QUEST_SPECIFICATION.md` |
| поведение EV3 | `EV3_SPECIFICATION.md` |
| физическая конструкция | `MECHANICAL_SPECIFICATION.md` |
| семантика протокола | `PROTOCOL_SPECIFICATION.md` |
| точный wire layout | `protocol/wire_schema.yaml` + generated `protocol/protocol.md` |
| контракт EV3-local IPC | `protocol/ipc_schema.yaml` + generated `protocol/protocol.md` |
| что реализовано, а что относится к будущему этапу | `implementation-map.json` |
| сквозная безопасность | `SAFETY.md` |
| build / CI / deploy / release | `ENGINEERING.md` |
| tests / evidence / acceptance | `TEST_PLAN.md` |
| нормативные этапы проекта / stage gates | `IMPLEMENTATION_STAGES.md` |
| термины / формулы / измеряемые значения | `REFERENCE.md` |
| внешние технические источники | `REFERENCES.md` |
| task-specific многосоставная работа | `exec-plans/` |
| текущий прогресс / blockers | `status/CURRENT_STATUS.md` |
| реально выполненные test/build/device reports | repository `results/**` |
| архитектурные решения и rationale | `decisions/` |
| открытые риски | `risks/` |

## Как найти существующую ссылку `§...`

Используй детерминированный locator, а не открывай весь section index:

```text
python tools/docindex.py --locate 7.16
python tools/docindex.py --locate §10.5
```

Generated [`SECTION_INDEX.md`](SECTION_INDEX.md) — полный человекочитаемый индекс.
`SECTION_INDEX.md` и `docs/PHANTOM_SPECIFICATION.md` нельзя редактировать вручную.

## Проверки specification identity

После изменения нормативного документа PHANTOM:

```text
python tools/specgen.py
python tools/specgen.py --check
python tools/docindex.py
python tools/docindex.py --check
python tools/doclint.py
```

Изменения protocol/config sources дополнительно требуют собственных generators и tests.

## Правило экономии agent context

Используй progressive disclosure. Не читай `ARCHITECTURE.md`, этот README и целый component
spec при каждой задаче только потому, что они существуют.

- Для узкой component-задачи найди и прочитай только нужный раздел основного owner.
- Читай `ARCHITECTURE.md`, когда задача пересекает component boundaries или меняет
  responsibility.
- Читай этот README, когда owner/location неясен.
- Для stage-задачи читай §10.2 и нужный stage плюс `status/CURRENT_STATUS.md`.
- Для документов больше примерно 500 строк сначала найди heading/anchor и прочитай
  ограниченный диапазон.

## Соглашения документации

- Mermaid diagrams хранятся inline в Markdown.
- Canonical states/messages/classes/config fields/technology identifiers сохраняют своё
  техническое написание.
- Требуемое поведение, нормативные development stages, task plans, текущий status, rationale,
  risks и внешние sources имеют разные жизненные циклы; см. `SPECIFICATION_GOVERNANCE.md`.
- Secrets, credentials и private keys никогда не являются содержимым документации.
