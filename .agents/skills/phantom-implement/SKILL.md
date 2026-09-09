---
name: phantom-implement
description: Реализовать или исправить ограниченное требование/этап PHANTOM ("реализуй", "исправь", "этап"). Не использовать как основной процесс для docs-only аудита, чистого wire-schema изменения или real-hardware acceptance.
---

# Рабочий процесс реализации PHANTOM

1. Не перечитывай `AGENTS.md`: он уже является активной проектной инструкцией.
2. Найди только нужные нормативные разделы; если известна ссылка `§...`, используй
   `python tools/docindex.py --locate <section>`.
3. Читай `docs/PHANTOM/SYSTEM_ARCHITECTURE.md` только для изменения cross-component responsibility; читай
   `docs/PHANTOM/README.md` только когда owner/location неясен.
4. Если задача называет этап, прочитай §10.2 и этот этап в
   `docs/PHANTOM/IMPLEMENTATION_STAGES.md`, а также
   `docs/PHANTOM/status/CURRENT_STATUS.md`.
5. До редактирования исследуй существующий код, tests, ownership generated sources и
   `git status`.
6. Если задача охватывает несколько компонентов/milestones или, вероятно, потребует несколько
   запусков, создай/обнови execution plan из `docs/PHANTOM/exec-plans/TEMPLATE.md`; иначе не
   создавай его.
7. Составь короткую traceability-цепочку:
   требуемое поведение → существующая реализация → недостающее → tests/gates →
   hardware-only evidence.
8. Считай принятые architecture/spec decisions уже принятыми. Возвращайся к архитектуре только
   если реальное противоречие блокирует реализацию.
9. Реализуй минимальное целостное vertical change и сохраняй границы Quest/EV3/protocol.
10. Если hardware недоступен, реализуй детерминированную логику, добавь off-hardware
    tests/builds, оставь physical evidence `NOT_RUN` и никогда не выдумывай hardware `PASS`.
11. Если часть изменения затрагивает wire layout/schema или protocol compatibility, для этой
    части также следуй `$phantom-protocol-change`, затем продолжай этот процесс реализации.
12. Добавляй regression coverage для каждого исправленного воспроизводимого дефекта.
13. Сначала запускай targeted checks, затем обязательный gate изменённой области. Команда
    пользователя `test` означает targeted TEST затронутой области; полный regression запускай
    только для явно запрошенной stage/release qualification или когда он является
    обязательным gate изменённой нормативной области. `build` означает BUILD только одного
    указанного/затронутого component/profile (`Diagnostic` по умолчанию), без deploy.
14. Если изменилось нормативное поведение, обнови primary owner и regenerate/check docs. Если
    код лишь догнал неизменившиеся требования, обнови status/evidence вместо переписывания
    требования.
15. Просмотри `git diff` на unrelated edits, generated drift, secrets, stale links и
    ослабление safety.
16. В отчёте укажи реализованное, реально запущенные tests/results,
    physical PASS/FAIL/NOT_RUN и оставшиеся blockers.
17. Commit делай только по явному запросу. Если требуется один финальный commit, делай его
    после всех non-hardware checks одним сфокусированным commit.
