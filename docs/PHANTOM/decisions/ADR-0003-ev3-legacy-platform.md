# ADR-0003 — Изоляция legacy-платформы EV3

- **Статус:** принято
- **Дата:** 2026-09-05

## Контекст

ev3dev Stretch и ARMv5/armel userspace являются EOL, при этом PHANTOM пока использует EV3
brick.

## Решение

Изолировать legacy dependency вместо распространения её по control core:

- держать motor/sysfs access за `MotorBackend`;
- использовать key-based SSH automation и изолированный LAN;
- pin/archive exact brick image и cross-toolchain artifacts по SHA-256;
- для release формировать SBOM и known-vulnerability review/disposition.

## Последствия

Release gate остаётся закрытым без exact legacy provenance/evidence. Host tests не отменяют
этот gate. Control/state/safety core должен оставаться переносимым за hardware backend.
