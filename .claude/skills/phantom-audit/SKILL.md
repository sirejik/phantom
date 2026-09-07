---
name: phantom-audit
description: Провести review/audit кода или документации PHANTOM ("проверь", "аудит", "противоречия", "что пропущено"). Ищет gaps и drift; не использовать как основной implementation или hardware-gate workflow.
---
<!-- Mirrored from .agents/skills/ by tools/skills_sync.py. Edit the source, not this copy. -->

# Рабочий процесс аудита PHANTOM

1. Не перечитывай `AGENTS.md`: он уже является активной проектной инструкцией.
2. Ограничь audit указанным component/stage. Известные `§...` разрешай через
   `python tools/docindex.py --locate <section>` и загружай только relevant ranges.
3. Читай `ARCHITECTURE.md` только при аудите cross-component boundaries.
4. Никогда не используй status или ADR вместо нормативного requirement/evidence report.
5. Построй traceability:
   `requirement → primary owner → implementation → test/gate → repository result/evidence → status`.
6. Проверь competing same-layer owners, contradictory refinements, generated drift,
   вручную продублированные protocol/config constants, missing implementation/tests, ложную
   hardware readiness, stale status, safety bypass, secrets, broken references и malformed
   Markdown.
7. Классифицируй:
   - P0: safety, actuator authority, auth/compatibility, false evidence;
   - P1: functional/reliability/acceptance gap;
   - P2: maintainability, duplication, stale documentation.
8. Для каждого finding укажи owner, evidence и минимальное исправление.
9. Если пользователь попросил исправить — исправляй в порядке ownership и добавляй regression
   coverage; иначе не выполняй скрытый redesign.
10. После изменений документации запускай relevant checks плюс spec/index/doc lint.
11. В конце перечисли unresolved items и точные hardware gates, которые остаются `NOT_RUN`
    или `FAIL`.
