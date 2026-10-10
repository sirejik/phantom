---
name: phantom-ev3-development
description: "Разрабатывать и исправлять службы EV3 на C++14, включая controller, safety, сеть и IPC."
license: MIT
---

# Разработка EV3

Начни с нужного раздела [EV3-спецификации](../../../docs/ev3-specification.md),
существующего кода и тестов. Язык, ABI и toolchain заданы в
[стеке](../../../docs/engineering.md#sec-engineering-stack), правила C++ — в
[правилах кода](../../../docs/code-guidelines.md#sec-code-guidelines-ev3).

1. Определи процесс: core/backend в `ev3/include` и `ev3/src`, supervisor в `ev3/safety`,
   сеть и mDNS в `ev3/src/network_*`, `controller_ipc_client.cpp` и `mdns_main.cpp`.
2. Проведи поведение и ошибки через существующие core/`MotorBackend` и штатные состояния.
   Для motor I/O сверь обнаружение, единицы, reference и обработку отказов с EV3-контрактом;
   прямой обход владельца приводов недопустим.
3. При изменении tick/concurrency найди нормативный бюджет, проверь ограниченность работы
   и очередей. Для IPC используй [phantom-protocol-change](../phantom-protocol-change/SKILL.md).
4. Проверь поведение в `ev3/tests` с MockMotorBackend и применимых сетевых suites.
   Host runner: `scripts/phantom.cmd TEST EV3 -Profile Diagnostic`.
   Сетевые регрессии и общий wire codec проверяет `phantom-network-server-tests`.
5. Для C++/ABI/package изменений выполни применимую ARM-сборку закреплённым toolchain.
   Для systemd/helpers проверь поддержку целевой средой и ограничения служб.

Host-тесты и cross-build не подтверждают движение или deadline на EV3. Запрошенную
работу на Brick выполняй через [phantom-hardware-gate](../phantom-hardware-gate/SKILL.md).
