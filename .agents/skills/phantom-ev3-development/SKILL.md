---
name: phantom-ev3-development
description: "Разрабатывать PHANTOM для LEGO Mindstorms EV3/ev3dev на C++14 и Python 3.5: motor backend, controller, IPC, supervisor, network services и systemd. Не применять production workflow к bench без явной задачи про bench."
license: MIT
---

# EV3: Linux, C++14 и Python 3.5

Начни с нужного [EV3 контракта](../../../docs/ev3-specification.md) и target в
`ev3/CMakeLists.txt`. Toolchain закреплён в `toolchains/ev3dev-stretch.lock.json`.
Это Linux userspace ev3dev, а не Arduino/FreeRTOS/Pybricks: не переноси MCU register/ISR
примеры в controller. Языковые ограничения: [C++14 и device Python](references/device-code.md).

## Граница изменения

- `ev3/include`, `ev3/src` — core и hardware backend; `ev3/safety` — supervisor;
  `ev3/network` — Python network/mDNS. Уточни процесс и его runtime identity до добавления I/O.
- Проведи состояние и отказ через существующий `MotorBackend`/core. Не создавай второй
  motor writer или прямой sysfs write в network, диагностике либо новом скрипте.
- Для motor sysfs обнаруживай устройство по address/driver, а не `motorN`; единицы и
  `count_per_rot` проверяются startup contract. Encoder discontinuity и I/O error должны
  идти через штатную инвалидацию/reference/safety логику, а не становиться валидным нулём.
- Для control-loop правки проверь bounded work, worst-case latency, монотонное время,
  ограниченную очередь и overflow policy. Не добавляй discovery, JSON parsing, filesystem
  logging или неограниченное ожидание внутрь critical tick.
- Изменение IPC требует `phantom-protocol-change`, даже если внешний UDP layout прежний.
  Wire и IPC offsets не вычисляются независимо от generated contract.

## Проверка

Сначала используй `ev3/tests`, MockMotorBackend и применимые network tests.
`scripts/phantom.cmd TEST EV3 -Profile Diagnostic` запускает штатный host TEST;
`python ev3/network/test_phantom_network.py` проверяет network logic без Brick.
Для C++/ABI/package правки нужен отдельный pinned ARM BUILD, когда этого требует gate.
Host sanitizer result и cross-build не подтверждают motor behavior или timing на EV3.

Для unit/helper правки проверь ограничения systemd baseline и device Python из
[среды EV3](../../../docs/ev3-specification.md#sec-7-1). INSTALL не запускает
compileall/self-tests: это TEST/BUILD и отдельные DEVICE cases. Доступ к Brick и движение
выполняются через `phantom-hardware-gate` только в рамках запрошенной фазы.

[Источники и адаптация](SOURCE.md) описывают, почему generic embedded/C++ skills изменены.
