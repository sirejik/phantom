---
name: phantom-spec-sync
description: Синхронизировать или реструктурировать документацию PHANTOM ("обнови спецификацию", "разнеси доку", "убери противоречия"). Использовать для ownership/migration; не выводить нормативное поведение из status или исторического evidence.
---
<!-- Mirrored from .agents/skills/ by tools/skills_sync.py. Edit the source, not this copy. -->

# Синхронизация спецификаций PHANTOM

1. Не перечитывай `AGENTS.md`: он уже является активной проектной инструкцией.
2. Используй `docs/PHANTOM/SPECIFICATION_GOVERNANCE.md`, чтобы классифицировать каждый
   изменяемый факт по нормативному layer/primary owner либо по ненормативной lifecycle role.
3. Строго разделяй жизненные циклы:
   - финальное требуемое поведение → normative owner;
   - определение development stage/gate → `docs/PHANTOM/IMPLEMENTATION_STAGES.md`;
   - task-local plan/progress → `docs/PHANTOM/exec-plans/`;
   - current implementation summary → `docs/PHANTOM/status/CURRENT_STATUS.md`;
   - реально выполненный automated/device/HIL report → repository `results/**`;
   - долговечный rationale → ADR;
   - unresolved exposure/disposition → risk;
   - наблюдаемый test result → evidence/report, а не requirement prose.
4. Не создавай новых mutable mirrors. Byte-level wire layout остаётся у schema/generated
   owner.
5. До удаления информации перенеси её к текущему owner или в долговечный provenance.
6. Legacy `§...` разрешай через `python tools/docindex.py --locate <section>`; после
   перемещения проверяй section/file links.
7. Regenerate/check:
   `python tools/specgen.py`
   `python tools/specgen.py --check`
   `python tools/docindex.py`
   `python tools/docindex.py --check`
   `python tools/doclint.py`
8. Если изменились protocol/config sources, запусти их generators.
9. Просмотри diff на semantic loss, accidental de-normativization, duplicate mutable facts и
   stale paths.
10. В отчёте укажи, что перемещено, что стало ненормативным/history, что намеренно удалено и
    какой source доказывает отсутствие потери нужной информации.
