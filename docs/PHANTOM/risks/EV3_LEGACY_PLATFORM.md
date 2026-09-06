# Риск legacy-платформы EV3

> **Тип:** risk/disposition record; не спецификация.
> Нормативные maintainability/release requirements остаются в
> `PRODUCT_REQUIREMENTS.md`, `ENGINEERING.md` и `TEST_PLAN.md`.

ev3dev Stretch и его ARMv5/armel userspace являются EOL. Control core изолирован от sysfs
через `MotorBackend`; SSH automation использует key-based access и ограничивается
изолированным LAN. Release остаётся заблокированным, пока exact brick image и
cross-toolchain artifacts не закреплены/архивированы с SHA-256, не создан SBOM и не приложен
known-vulnerability review. Это явный gate §3.2.7/§8.5; host tests его не отменяют.

## Disposition

Release остаётся заблокированным, пока указанное evidence не существует для exact release
candidate. Host/simulator tests не отменяют gate. `MotorBackend` является migration seam:
будущая смена controller platform не должна требовать переписывания state/safety/control
logic.
