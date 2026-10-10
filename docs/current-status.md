# Текущее состояние реализации PHANTOM

## Текущее состояние

**Stage 3 не завершён.** Прежний EV3 Diagnostic ARM BUILD и проверка пакета выполнены
для `PHANTOM-BUILD-V4` и обновлённого `HELLO_ACK`; после переноса toolchain и уточнения
входов source hash новая ARM-сборка и проверка пакета — `NOT_RUN`.
Долговечный отчёт прежней сборки ещё не опубликован.
Quest APK BUILD, DEVICE, ручная приёмка — `NOT_RUN` для текущих артефактов.
Результаты прежних сборок не подтверждают текущие артефакты.

## Незакрытые проверки

| Область | Состояние и следующий шаг |
|---|---|
| Полнота программных тестов EV3 и Quest | Не подтверждена: сопоставить реализованную функциональность обеих платформ с автоматическими тестами production-кода по [План проверки §3](test-plan.md#sec-9-1-2), устранить пробелы и выполнить применимый software regression до DEVICE/MANUAL qualification |
| Host lifecycle tests | [test_pair_state.ps1](../tools/test_pair_state.ps1) проверяет pair state, process helpers и сбор логов Quest с fake SSH/ADB/Python, включая отказы. Полнота остальных lifecycle/install behaviors с подменёнными зависимостями не подтверждена; поиск строк в исходниках не заменяет такие тесты |
| Stub Quest3 / tracking replay | C# TrackingReplaySource существует; JSONL loading и подача записей в production algorithms с unit/functional проверками не подтверждены. Прежний Python-счётчик записей удалён |
| Stage 3 | Выполнить Quest Diagnostic BUILD, запуск свежей пары и применимые network/session/reconnect/reboot cases; критерии — [Этапы реализации §5](implementation-stages.md#sec-10-5) |
| DEVICE, manual acceptance | `NOT_RUN` для новой identity; опубликовать exact reports с URI/SHA-256 |
| Интеграционные Quest/EV3/пара | Покрытие полного списка не подтверждено; сопоставить runners с [планом](test-plan.md#sec-9-1-3), реализовать недостающие cases и проверить пару без движения |
| Quest без надетого шлема | Полный прогон не подтверждён: OnApplicationPause останавливает сетевой клиент, KEYCODE_WAKEUP не доказывает непрерывное выполнение. Проверить awake/headless prerequisites и корректный NOT_RUN при suspend |
| Автоматический анализ метрик | Полнота не подтверждена: проверить сбор валидных samples, сообщения о превышениях и статус не измерено без данных/эталона по [метрикам](metrics-and-logs.md#sec-test-plan-manual-criteria). Пользовательские формы приёмки не требуются |
| Quest credential persistence | `NOT_RUN`: проверить сохранение credential между двумя APK после lifecycle migration |
| Full-arm Body provider | Exact platform matrix не квалифицирована; выполнить [P0](metrics-and-logs.md#sec-9-6) для применимого scope. Историческая несовместимость описана в [источниках](references.md#sec-11-5-1) |
| EV3 release inputs | Release PASS не подтверждён: нужны exact brick image/toolchain SHA-256, SBOM и vulnerability review/disposition по [Разработка и развёртывание §4](engineering.md#sec-8-5) |
| Quest APK reproducibility | Повторить проверку exact builds: ранее при одинаковом `build_id` различались Unity GUID metadata (`boot.config`, `globalgamemanagers`, `unity_app_guid`, GUID-именованные entries) |
| Упрощение режимов сборки и запуска | Спецификация предусматривает отладочную (`Diagnostic`) и релизную (`Release`) сборки, запуск через START. Скрипты и build tooling ещё поддерживают отдельные DeepDebug/DEBUG; объединение инструментализации с отладочной сборкой и удаление старых вариантов не реализованы |
| C++-службы сети EV3 | Целевой стек — C++14 для network/mDNS. `ev3/network/phantom_network.py` и `phantom_mdns.py` пока используются; перенос с сохранением IPC, HMAC/session semantics, process isolation и протокольных регрессий не выполнен |
| Блокировка после критического loop overrun | Исправлены latched `STOPPED + FAULT_LOOP_OVERRUN`, запрет ACK до устранения причины и восстановление без автоматического движения. Пороги в configgen и runtime ограничены 60/100 ms; C++ host regression подтверждён. Проверка на EV3 — `NOT_RUN` |
| Полный Diagnostic profile | Спецификация разрешает полный продуктовый scope в Diagnostic при тех же safety gates, что и Release. Текущие configgen/Stage-3 runtime допускают только network-only Diagnostic; расширение профилей относится к следующим этапам |
| GitHub Actions | Workflow `.github/workflows/ci.yml` существует: документация, схемы/Python tools, C++ host tests/sanitizers, ARM cross-build. Успешный запуск в GitHub не подтверждён; полного Unity test/build job в workflow нет |

## Ближайший шаг

Подготовить свежую network-only Diagnostic пару: `actuator_scope_mask=safety_observation_mask=0x00`,
`required_user_inputs=NONE`; физическое движение запрещено, motor A может отсутствовать.
Последняя локальная проверка пары (2026-09-10) дала `LOCAL_PAIR_STATE_ABSENT`;
перед запуском проверить состояние заново и при отсутствии пары выполнить явный
`PROVISION PAIR` с доверенным EV3 fingerprint и CONTROL credential.

Порядок: TEST → BUILD → EV3 TRANSFER/INSTALL и Quest INSTALL → EV3 START → Quest START.
Разобрать timings, readiness, first failure и terminal state; DEVICE и применимые
Stage-3 manual cases выполнить отдельно. Команды и границы фаз —
[Разработка и развёртывание §4.2](engineering.md#sec-8-5-1).

Физические критерии MANUAL ACCEPTANCE — NOT_RUN; проверяются по
[test-plan](test-plan.md#sec-9-23). Существующие runners и measurement metadata с HIL label
не переименованы; при работе с ними учитывать ручные cases и не считать legacy label
доказательством автономной квалификации.
