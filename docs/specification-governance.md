# PHANTOM — правила управления спецификацией

Этот документ определяет, как интерпретируется и изменяется набор спецификаций PHANTOM. Он
является нормативным для ролей документов, ownership, compatibility identity и разрешения
конфликтов. Он не дублирует поведение компонентов.

<!-- BEGIN GENERATED TOC -->
<details>
<summary>Оглавление</summary>

- [1. Нормативный набор спецификаций](#sec-specification-governance-1)
- [2. Нормативные уровни и основные владельцы](#sec-specification-governance-2)
  - [2.1. Правило уточнения](#sec-specification-governance-2-1)
- [3. Ненормативные документы жизненного цикла](#sec-specification-governance-3)
- [4. Разрешение конфликтов](#sec-specification-governance-4)
- [5. Стабильные ссылки на разделы](#sec-specification-governance-5)
- [6. Дисциплина изменений](#sec-specification-governance-6)
- [7. Семантика evidence](#sec-specification-governance-7)

</details>
<!-- END GENERATED TOC -->

<a id="sec-specification-governance-1"></a>
## 1. Нормативный набор спецификаций

Нормативный набор объявлен в `docs/spec-set.json` и используется только
для навигации, оглавлений и проверки согласованности документации.

Документация не является входом BUILD, config generation, artifact validation или
runtime handshake. Её содержание, наличие, пути и hashes не входят в `build_id`.
Соответствие реализации актуальным требованиям проверяется review и применимыми
TEST/DEVICE/HIL gates; build identity само по себе не доказывает это соответствие.

`source_tree_hash`, `protocol_schema_hash`, `protocol_semantics_hash`, derived
`protocol_contract_hash`, configuration/component hashes, build IDs и artifact hashes
идентифицируют machine/runtime inputs. Изменение требования, затрагивающего поведение,
требует согласованного изменения реализации, machine contracts и проверок.

<a id="sec-specification-governance-2"></a>
## 2. Нормативные уровни и основные владельцы

PHANTOM намеренно построен слоями. У факта есть основной owner на своём уровне, при этом
higher-level requirements и сквозные safety rules ограничивают lower-level design. Детальный
owner не имеет права ослаблять эти ограничения.

| Документ/источник | Основная нормативная роль |
|---|---|
| `product-requirements.md` | цели продукта и обязательства FR/NFR |
| `safety.md` | сквозные safety invariants и pre-motion constraints |
| `system-architecture.md` | границы компонентов, responsibility split, system states и end-to-end flows |
| `quest-specification.md` | Quest runtime behavior, tracking, mapping, IK, QR/localization, UI и Quest config |
| `ev3-specification.md` | EV3 processes, references, controller behavior, actuator protection, telemetry и EV3 config |
| `mechanical-specification.md` | physical assembly, geometry, QR fixtures, cabling, gripper и mechanical constraints |
| `protocol-specification.md` | человекочитаемая transport/session/transaction semantics |
| `protocol/wire_schema.yaml` | точная schema-representable структура wire: layout, widths, numeric enum/bit positions, reserved fields и payload lengths; контекстные semantic ranges/transition guards остаются в owning prose |
| `protocol/semantics.yaml` | machine-readable межреализационная semantics, входящая вместе со structural hash в compatibility `protocol_contract_hash` |
| объявленные репозиторием config schema/generator sources | машинно-читаемая структура конфигурации и generated config artifacts |
| `engineering.md` | source/build/CI/deployment/release/logging engineering requirements |
| `test-plan.md` | verification taxonomy, applicability, evidence requirements и final acceptance |
| `implementation-stages.md` | нормативная последовательность разработки, stage definitions и qualification gates |
| `reference.md` | canonical terminology, ссылки на формулы компонентов и measured-parameter rules |

`references.md` является ненормативной трассировкой внешних источников. Vendor documentation
может объяснять или поддерживать требование, но не может переопределять requirements PHANTOM,
safety invariants или device/HIL qualification.

<a id="sec-specification-governance-2-1"></a>
### 2.1. Правило уточнения

Lower-level specification может уточнять higher-level requirement, добавляя точное поведение,
данные или алгоритмы. Такое уточнение обязано оставаться совместимым со всеми применимыми
FR/NFR, safety invariants и cross-component architecture contracts.

Детальное правило, алгоритм или перечень полей хранится у одного primary owner. Другие
документы ссылаются на него и объясняют только свою область ответственности. Требование
продукта, его реализация в компоненте и проверяющий тест — разные уровни описания, а не
три независимые редакции одного правила.

Обязательное поведение детальной спецификации должно обеспечивать существующие
FR/NFR и критерии продукта; связка с владельцем решения и процедурой проверки
находится в [Плане проверки §25](test-plan.md#sec-9-25). Выбор алгоритма, схемы передачи
или инженерного ограничения сам по себе не требует нового критерия. Если появляется
самостоятельная возможность продукта, сначала добавляется её наблюдаемое требование
и при необходимости критерий. Опциональная возможность не становится условием
готовности обязательного режима.

<a id="sec-specification-governance-3"></a>
## 3. Ненормативные документы жизненного цикла

Ненормативные документы и отчёты имеют следующие роли:

- временные `task-*-plan.md` — task-specific implementation plans, progress и локальные решения;
- `current-status.md` — краткое текущее состояние реализации;
- локальный `results/**` — игнорируемое Git workspace для machine-readable test/build/device
  evidence; долговечные отчёты публикуются как immutable CI/release artifacts;
- `references.md` — трассировка внешних источников.

Status, execution plan, machine-readable result/evidence, внешний источник
или текущее поведение кода никогда не переопределяют нормативный набор. Долговечный
опубликованный report с artifact URI/SHA-256 доказывает, что конкретный gate действительно
выполнялся для зафиксированного candidate identity; локальный `results/**` является только
рабочим каталогом runner, а `current-status.md` кратко суммирует опубликованное evidence.

<a id="sec-specification-governance-4"></a>
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

<a id="sec-specification-governance-5"></a>
## 5. Стабильные ссылки на разделы

В каждом документе разделы нумеруются с 1. Ссылка на раздел содержит файл и его локальный
номер; внутри документа достаточно локального номера. Markdown-ссылка указывает на явный
HTML anchor и остаётся рабочей при перемещении текста.

Существующие `sec-*` anchors — непрозрачные стабильные идентификаторы: цифры внутри них
не являются текущей нумерацией. Они сохраняют совместимость со ссылками из кода и старых
записей Git. `tools/docindex.py` обновляет оглавление внутри каждого документа и выполняет поиск по файлу и локальному номеру;
`--document ev3-specification.md --locate 1` ищет текущий раздел, а `--locate 7.1` без
имени документа разрешает только прежний глобальный идентификатор.

Новые ссылки используют локальный номер и файл. Новые разделы получают уникальный anchor
с префиксом документа, например `sec-ev3-motor-backend`. При переносе anchor сохраняется,
а относительные пути ссылок обновляются в той же правке.

<a id="sec-specification-governance-6"></a>
## 6. Дисциплина изменений

- Финальное требуемое поведение хранится у соответствующего нормативного owner.
- Нормативные определения stages/gates хранятся в `implementation-stages.md`.
- Task-specific work order/progress хранится во временных `task-*-plan.md`. Завершённые и заменённые
  планы после переноса результата и незакрытых задач удаляются; история доступна в Git.
- Обоснования решений, ограничения и меры снижения риска находятся у соответствующего
  владельца спецификации. Состояние незакрытых проверок хранится в `current-status.md`. Отдельный
  журнал изменений документации не ведётся: авторство и история доступны в Git.
- Текущее состояние реализации хранится в `current-status.md`; подробные реально выполненные
  automated/device/HIL reports публикуются как immutable CI/release artifacts и не
  копируются в normative prose либо историю Git.
- Exact wire tables/constants/size maps должны происходить из `protocol/wire_schema.yaml`, а не поддерживаться вручную в нескольких prose files. Production codecs могут быть hand-written, но обязаны проходить общие golden/negative vectors и не становятся source of truth.
- Secrets и credentials никогда не находятся в specifications, status, plans, source
  fixtures, build manifests или обычных logs.
- Изменение нормативного документа требует regeneration/check локальных оглавлений,
  проверки ссылок и согласованности требований плюс применимые tests.
- Изменение только документации не меняет build identity и не требует пересборки.
  Если изменились требования к проверкам или безопасности, применимость прежнего evidence
  оценивается заново: прежний PASS не доказывает выполнение новых требований.

<a id="sec-specification-governance-7"></a>
## 7. Семантика evidence

Mocks, simulation, source inspection и успешная compilation могут доказывать software
properties, но не могут превращаться в real-device, HIL или manual-acceptance `PASS`.

Статусы evidence определяются в `test-plan.md`; current status является summary evidence, а
не самим evidence.
