---
name: phantom-hardware-gate
description: "Подготовить или выполнить PHANTOM INSTALL, START, DEVICE INTEGRATION TEST, HIL, recovery или физическую приёмку Quest 3/EV3. Использовать для явно запрошенной работы с устройствами, а не для обычной правки кода."
---

# Работа с устройствами PHANTOM

Сопоставь запрос с конкретной фазой по
[Разработка и развёртывание](../../../docs/engineering.md#sec-8-5-1).
Используй существующий `scripts/phantom.cmd` и его phase runners. Установка/запуск
не подразумевают provisioning, тестирование, recovery или новую сборку.
Отсутствующий prerequisite сообщается как причина остановки зависимой фазы; доступную
подготовительную работу можно продолжать. Не запрашивай повторное разрешение на уже
авторизованные действия.

1. Определи stage/profile и применимые cases по
   [План проверки](../../../docs/test-plan.md). Проверь exact target из fixed-pair state,
   artifact SHA-256, component `build_id`, protocol contract и config/bundle
   identities; Quest cases также привязаны к фактической platform matrix.
2. До любого движения проверь применимые pre-motion gates из
   [Безопасность](../../../docs/safety.md#sec-11-4): локальную авторизацию, scope,
   calibration/reference, fixture/support, LOCAL_STOP и независимый POWER_CUT.
   Network-only case не получает motor authority ради диагностики.
3. Выполни только выбранные bounded cases. Сохрани первый непосредственный отказ,
   terminal safe state и результаты каждого case штатным runner. При отказе прекрати
   зависимые действия; recovery не запускается как скрытая часть START/DEVICE.
4. Используй PASS/FAIL/NOT_RUN/N_A по TEST_PLAN и сохраняй applicability/candidate identity.
   Локальный report находится в `results/`; требуемое долговечное evidence публикуется
   immutable artifact с URI/SHA-256 в пределах порученного workflow.

Секреты и pair state обслуживаются только PROVISION; missing/corrupt state не разрешает
автоматическую ротацию или fingerprint repin. При отсутствии оборудования оставь физические
cases NOT_RUN и укажи конкретные prerequisites и следующую команду/case.
