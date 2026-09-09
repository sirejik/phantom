# Execution plans PHANTOM

Execution plans — ненормативные рабочие артефакты для многошаговой реализации. Они позволяют
продолжать длинные Codex-задачи после перезапуска без помещения task progress в спецификации.

Нормативные этапы проекта и qualification gates находятся в
`../IMPLEMENTATION_STAGES.md`.

Создавай task execution plan, если работа охватывает несколько компонентов, содержит
несколько независимо проверяемых milestones или, вероятно, потребует нескольких запусков
Codex. Для небольшой обратимой правки plan не нужен.

- Новый task plan находится в `active/`, пока работа выполняется.
- После завершения перенеси его в `completed/`, когда результат уже отражён в коде,
  tests/evidence и `status/CURRENT_STATUS.md`.

Task plan фиксирует локальный work order, progress, decisions и verification commands. Он
никогда не переопределяет нормативную спецификацию или test plan.

Каждый plan имеет явный `Status`, normative owners и hardware/evidence state. Исторические
plans, оставшиеся в корне до физического перемещения архива, обязаны иметь
`COMPLETED`/`SUPERSEDED` и ссылку на преемника; они не считаются active только из-за пути.
Новый active plan не может объявлять hardware PASS без ссылки на exact immutable report.
