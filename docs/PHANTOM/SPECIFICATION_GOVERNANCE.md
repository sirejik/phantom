# PHANTOM — правила управления спецификацией

Этот документ определяет, как интерпретируется и изменяется набор спецификаций PHANTOM. Он
является нормативным для ролей документов, ownership, compatibility identity и разрешения
конфликтов. Он не дублирует поведение компонентов.

## 1. Нормативный набор спецификаций

Упорядоченный нормативный набор объявлен в `docs/PHANTOM/spec-set.json`.
`tools/specgen.py` проверяет, что каждый нормативный Markdown хранится как UTF-8 без BOM с LF line endings, вычисляет SHA-256 его **точных bytes в Git** и записывает ordered path+hash manifest в `docs/PHANTOM_SPECIFICATION.md`.

Существующий `specification_sha256` — SHA-256 точных bytes generated manifest. Hidden normalization перед hashing запрещена: другая encoding/BOM/CRLF форма отклоняется gate.

`specification_sha256` идентифицирует полный нормативный baseline PHANTOM.
`protocol_schema_hash`, configuration/component hashes, build IDs и artifact hashes
идентифицируют более узкие machine/runtime domains.

## 2. Нормативные уровни и основные владельцы

PHANTOM намеренно построен слоями. У факта есть основной owner на своём уровне, при этом
higher-level requirements и сквозные safety rules ограничивают lower-level design. Детальный
owner не имеет права ослаблять эти ограничения.

| Документ/источник | Основная нормативная роль |
|---|---|
| `PRODUCT_REQUIREMENTS.md` | цели продукта и обязательства FR/NFR |
| `SAFETY.md` | сквозные safety invariants и pre-motion constraints |
| `SYSTEM_ARCHITECTURE.md` | границы компонентов, responsibility split, system states и end-to-end flows |
| `QUEST_SPECIFICATION.md` | Quest runtime behavior, tracking, mapping, IK, QR/localization, UI и Quest config |
| `EV3_SPECIFICATION.md` | EV3 processes, references, controller behavior, actuator protection, telemetry и EV3 config |
| `MECHANICAL_SPECIFICATION.md` | physical assembly, geometry, QR fixtures, cabling, gripper и mechanical constraints |
| `PROTOCOL_SPECIFICATION.md` | человекочитаемая transport/session/transaction semantics |
| `protocol/wire_schema.yaml` | точная schema-representable структура wire: layout, widths, numeric enum/bit positions, reserved fields и payload lengths; контекстные semantic ranges/transition guards остаются в owning prose |
| объявленные репозиторием config schema/generator sources | машинно-читаемая структура конфигурации и generated config artifacts |
| `ENGINEERING.md` | source/build/CI/deployment/release/logging engineering requirements |
| `TEST_PLAN.md` | verification taxonomy, applicability, evidence requirements и final acceptance |
| `IMPLEMENTATION_STAGES.md` | нормативная последовательность разработки, stage definitions и qualification gates |
| `REFERENCE.md` | canonical terminology, общие формулы и measured-parameter rules |

`REFERENCES.md` является ненормативной трассировкой внешних источников. Vendor documentation
может объяснять или поддерживать требование, но не может переопределять requirements PHANTOM,
safety invariants или device/HIL qualification.

### Правило уточнения

Lower-level specification может уточнять higher-level requirement, добавляя точное поведение,
данные или алгоритмы. Такое уточнение обязано оставаться совместимым со всеми применимыми
FR/NFR, safety invariants и cross-component architecture contracts.

Осознанное повторение допустимо для читаемости, но primary owner остаётся местом изменения
факта. Secondary text при расхождении должен быть обновлён или заменён ссылкой.

## 3. Ненормативные документы жизненного цикла

Следующие документы намеренно не входят в `specification_sha256`:

- `exec-plans/**` — task-specific implementation plans, progress и локальные решения;
- `status/**` — краткое текущее состояние реализации;
- локальный `results/**` — игнорируемое Git workspace для machine-readable test/build/device
  evidence; долговечные отчёты публикуются как immutable CI/release artifacts;
- `decisions/**` — rationale/history архитектурных решений;
- `risks/**` — отслеживание открытых рисков и disposition;
- `CHANGELOG.md` — revision provenance;
- `REFERENCES.md` — трассировка внешних источников.

Status, execution plan, machine-readable result/evidence, ADR, risk record, внешний источник
или текущее поведение кода никогда не переопределяют нормативный набор. Долговечный
опубликованный report с artifact URI/SHA-256 доказывает, что конкретный gate действительно
выполнялся для зафиксированного candidate identity; локальный `results/**` является только
рабочим каталогом runner, а `status/**` кратко суммирует опубликованное evidence.

## 4. Разрешение конфликтов

1. Определи нормативный уровень и primary owner спорного факта.
2. Сначала проверь применимые FR/NFR, safety invariants и ограничения системной архитектуры;
   detailed component behavior должен им соответствовать.
3. В machine-owned domain machine source и generated artifacts обязаны совпадать; расхождение
   означает failed change, а не разрешение выбрать одну сторону.
4. Human-readable mirror, который расходится с primary owner, является stale и должен быть
   исправлен.
5. Если два документа выглядят primary owners одного изменяемого факта на одном уровне,
   ownership неоднозначен и должен быть разрешён явно.
6. Safety-relevant ambiguity трактуется fail-closed до устранения. Противоречие является
   дефектом; нельзя молча выбирать документ только потому, что он новее, длиннее или ближе к
   коду.

## 5. Стабильные ссылки на разделы

Legacy identifiers вида `§x.y` сохраняются при разбиении, чтобы существующие cross-references
оставались стабильными. `tools/docindex.py` генерирует `docs/PHANTOM/SECTION_INDEX.md`,
который сопоставляет identifier текущему файлу.

Перемещение раздела между файлами должно сохранять его `<a id="sec-...">`, если только в той
же правке не выполняется осознанная repository-wide migration всех ссылок.

## 6. Дисциплина изменений

- Финальное требуемое поведение хранится у соответствующего нормативного owner.
- Нормативные определения stages/gates хранятся в `IMPLEMENTATION_STAGES.md`.
- Task-specific work order/progress хранится в `exec-plans/`.
- Текущее состояние реализации хранится в `status/`; подробные реально выполненные
  automated/device/HIL reports публикуются как immutable CI/release artifacts и не
  копируются в normative prose либо историю Git.
- Exact wire tables/constants/size maps должны происходить из `protocol/wire_schema.yaml`, а не поддерживаться вручную в нескольких prose files. Production codecs могут быть hand-written, но обязаны проходить общие golden/negative vectors и не становятся source of truth.
- Secrets и credentials никогда не находятся в specifications, status, plans, source
  fixtures, build manifests или обычных logs.
- Изменение нормативного документа требует regeneration/check specification manifest и
  section index плюс применимые tests.
- Изменение только ненормативных status/task plans/ADRs/risks/changelog/`REFERENCES.md` не
  меняет `specification_sha256`.

## 7. Семантика evidence

Mocks, simulation, source inspection и успешная compilation могут доказывать software
properties, но не могут превращаться в real-device, HIL или manual-acceptance `PASS`.

Статусы evidence определяются в `TEST_PLAN.md`; current status является summary evidence, а
не самим evidence.
