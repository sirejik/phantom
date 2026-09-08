---
name: phantom-hardware-gate
description: Запустить или подготовить real PHANTOM Quest 3/EV3 DEVICE/HIL/acceptance ("подключил Quest", "проверить EV3", "HIL", "hardware gate"). Evidence-grade физический workflow; никогда не выводить PASS из simulation.
---

# Проверка PHANTOM на реальном оборудовании

Используй только когда real hardware validation явно запрошен или непосредственно
подготавливается.

1. Найди нужный stage в `docs/PHANTOM/IMPLEMENTATION_STAGES.md`, затем прочитай только
   применимые разделы `docs/PHANTOM/TEST_PLAN.md`, `docs/PHANTOM/SAFETY.md` и involved
   component specs.
2. Сначала зафиксируй exact candidate identity: content-addressed source identity,
   `specification_sha256`, `protocol_schema_hash`, component/profile `build_id`,
   config/bundle hashes и artifact SHA-256.
3. Не переноси PASS с другой build/spec/platform matrix.
4. До actuator motion выполни все применимые pre-motion prerequisites, включая local
   authority, references/calibration, scope, physical fixture/support, `LOCAL_STOP` и
   доступный independent `POWER_CUT`.
5. Увеличивай motor authority только внутри квалифицированного scope. Diagnostic/test tooling
   не может обходить EV3 admission.
6. Выполняй bounded cases и сохраняй machine-readable evidence плюс diagnostic context.
7. Статус строгий:
   `PASS` = case реально выполнен на требуемом объекте;
   `FAIL` = выполненный case нарушил критерий;
   `NOT_RUN` = не запускался;
   `N_A` = есть нормативная причина неприменимости.
8. Simulator/mock/source inspection может подготовить case, но никогда не превращается в
   hardware PASS.
9. При failure сначала переведи систему в безопасное состояние и сохрани evidence; если
   возможна детерминированная off-hardware репродукция, добавь regression coverage.
10. Сохраняй подробный machine-readable result/evidence в локальный Git-ignored `results/**`,
    а требуемое долговечное evidence публикуй как immutable CI/release artifact с URI и
    SHA-256. `CURRENT_STATUS.md` обновляй только как summary опубликованного evidence. Никогда
    не ослабляй требование, чтобы превратить device failure в PASS.
