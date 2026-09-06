# Карта архитектуры PHANTOM

Этот файл — короткая ненормативная карта для людей и coding agents. Детальные требования
находятся в `docs/PHANTOM/`; нормативный набор перечислен в
`docs/PHANTOM/spec-set.json`.

## Граница системы

```text
Meta Quest 3
  tracking / user intent / calibration UI
  workspace + mapping + IK
  protocol client
        |
        | authenticated UDP: targets, transactions, telemetry
        v
LEGO Mindstorms EV3
  session/state/safety admission
  encoder references + local trajectory/control
  gripper FSM + motor protection
  authoritative motor I/O
        |
        v
Physical PHANTOM
  Base / Shoulder / Elbow / Gripper
  mechanical limits / QR fixtures / LOCAL_STOP
  independent POWER_CUT
```

## Границы ответственности

### Quest

Quest отвечает за XR acquisition, shoulder/wrist/grasp inputs, преобразования координат,
пользовательскую калибровку, локализацию робота по QR, генерацию targets,
workspace/IK preview, UI и client-side сетевого протокола. Quest никогда не отправляет
PWM/duty commands.

### EV3

EV3 отвечает за authenticated session admission, authoritative actuator scope, startup
references, command freshness, local trajectory shaping, controllers, motor limits/protection,
gripper state, telemetry и motor I/O. Сеть или состояние Quest не могут обходить EV3
safety gates.

### Механика

Физическая сборка задаёт реальную геометрию, hard/mechanical constraints, размещение QR,
cable routing, поведение counterweight, `LOCAL_STOP` и независимый `POWER_CUT`.

## Канонические machine-readable источники

- Wire format: `protocol/wire_schema.yaml`
- Generated protocol documentation: `protocol/protocol.md`
- Cross-language protocol fixtures: `protocol/golden_vectors/`
- Configuration schemas: `config/schema/`
- Generated configuration artifacts: `config/generated/`

Generated files являются результатами, а не конкурирующими источниками истины.

## Карта документации

- Цели и требования продукта: `docs/PHANTOM/PRODUCT_REQUIREMENTS.md`
- Системные flows/state ownership: `docs/PHANTOM/SYSTEM_ARCHITECTURE.md`
- Quest: `docs/PHANTOM/QUEST_SPECIFICATION.md`
- EV3: `docs/PHANTOM/EV3_SPECIFICATION.md`
- Механика: `docs/PHANTOM/MECHANICAL_SPECIFICATION.md`
- Network/protocol semantics: `docs/PHANTOM/PROTOCOL_SPECIFICATION.md`
- Сквозная безопасность: `docs/PHANTOM/SAFETY.md`
- Build/deploy/CI: `docs/PHANTOM/ENGINEERING.md`
- Acceptance/evidence: `docs/PHANTOM/TEST_PLAN.md`
- Термины, формулы и измеряемые параметры: `docs/PHANTOM/REFERENCE.md`
- Нормативные этапы и gates: `docs/PHANTOM/IMPLEMENTATION_STAGES.md`
- Task-specific execution plans: `docs/PHANTOM/exec-plans/`
- Текущее состояние: `docs/PHANTOM/status/CURRENT_STATUS.md`

Навигация находится в `docs/PHANTOM/README.md`. Для разрешения legacy-ссылок вида `§x.y`
используй `python tools/docindex.py --locate <section>`.
