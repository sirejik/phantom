---
name: phantom-spec-sync
description: "Изменить или реорганизовать документацию PHANTOM, устранить дублирование и рассогласование со schema. Сохраняет владельцев требований, локальную нумерацию и ссылки."
---

# Редактирование документации PHANTOM

Определи владельца изменения по
[Правила спецификации](../../../docs/specification-governance.md).
Требование и rationale находятся в owning spec, progress и незакрытые проверки — в status,
порядок текущей многошаговой работы — в execution plan. Не выводи требование из status
или исторического отчёта. Историю завершённых изменений хранит Git.

- Перед удалением повторяющегося текста проверь, что уникальные ограничения сохранены
  у владельца. Другие документы должны ссылаться на него.
- Точный wire/config layout принадлежит machine source. Недостающее в schema поле нужно
  либо добавить через соответствующий generator workflow, либо явно описать как будущее.
- Каждый документ нумеруется с 1. При переносе сохраняй anchors и обновляй file/section links,
  включая `implementation-map.json`. Locator: `python tools/docindex.py --document FILE.md --locate N`;
  без `--document` разрешаются только legacy identifiers.

После изменения нормативного Markdown:

```text
python tools/docindex.py
python tools/docindex.py --check
python tools/doclint.py
python tools/implementation_map_check.py
python tools/spec_contract_check.py
```

Для ненормативной правки достаточно применимых link/lint checks; wire/config source changes
требуют собственных generators и проверок. Изменённые requirements требуют оценки
применимости прежнего evidence; документация не входит в build identity.
Просмотри diff на потерю смысла и сообщи, что удалено, куда перенесено и что проверено.
