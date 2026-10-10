# Текущее состояние реализации PHANTOM

## Текущее состояние

**Stage 3 не завершён.** EV3 Diagnostic ARM BUILD и проверка пакета с C++ network/mDNS
выполнены для `PHANTOM-BUILD-V4`. Host C++ suites, включая ASan/UBSan, и UDP interop
штатного C# клиента с C++ сетевой службой проходят. Эти проверки не подтверждают
работу на устройствах; долговечный отчёт сборки ещё не опубликован.
Quest APK BUILD и Unity EditMode запрошены, но не прошли: Unity 6000.3.22f1
не находит действующую лицензию (код 198, `No valid Unity Editor license found`).
Один запуск дошёл до компиляции и выявил отсутствие Android target; оба запускателя
исправлены, но реальная проверка этой правки также заблокирована лицензией.
DEVICE и ручная приёмка — `NOT_RUN` для текущих артефактов.
Результаты прежних сборок не подтверждают текущие артефакты.

## Единый инструмент

Операции перенесены в `tooling/`; публичный запуск — `python tooling <command>`.
Host-код — Python 3.12+, общие модули процессов, окружения, пары и файлов переиспользуются.
Прежние PowerShell entrypoints удалены. Устанавливаемый Python EV3 заменён на
C++14 `phantom-maintenance` и `phantom-device-integration-test`; короткие POSIX обёртки
и systemd units хранятся в ресурсах CLI. Unit/functional tests продукта остаются в проектах C++/C#.

Команды и технические контракты собраны в [tooling.md](tooling.md).
`python-scripts.md` и `engineering-contracts.md` объединены с ним; правила конфигурации
перенесены в engineering. Skills, AGENTS и CI используют новую точку входа.

## Проверки переноса tooling

Результаты новой проверки 2026-10-10:

Системный `python` на этой машине — 3.8.2. Проверки выполнены отдельным Python 3.12.10
в `%LOCALAPPDATA%/PHANTOM/tooling-python-3.12.10/python.exe`; глобальные настройки Python
не изменялись. Для запуска CLI использовать этот интерпретатор либо установленный Python 3.12+.

- `doctor`, генерация протокола/конфигурации/оглавлений и `check` проходят;
  Android bridge компилируется, POSIX ресурсы проходят синтаксическую проверку.
- Все 136 tooling self-tests проходят: генераторы, пакеты, JSON/JCS, процессные отказы,
  Unity XML, SSH fingerprint/config, сохранение credentials, cleanup и анализ.
- Семь C++ suites проходят в Diagnostic, Release и с ASan/UBSan.
- Quest host: 3 Unit-группы и 10 Functional cases, включая настоящий C#↔C++ UDP/IPC, проходят.
- Diagnostic EV3 ARM-пакет собирается и проверяется; две независимые сборки совпадают по байтам.
- Unity EditMode и APK BUILD реально запущены новым CLI, но завершаются кодом 198:
  `No valid Unity Editor license found`. Нужна активация Unity 6000.3.22f1 в Unity Hub.
- Release packaging остаётся заблокирован без qualification evidence и подтверждённых
  platform/SBOM/risk inputs; это не аппаратный PASS.
- INSTALL, START, интеграционные тесты и получение данных реальных устройств — `NOT_RUN`.
  Проверки с подменёнными зависимостями не подтверждают работу на устройствах.

CLI-анализ EV3 пока только сводка journald по службам и severity; полнота физических
метрик не реализована. `check` также не подтверждает полный clang-tidy/C# analyzer coverage.
Workflow выполняет программные проверки для push/PR; результаты публикуются
в checks соответствующего pull request. Unity и аппаратные проверки в этот workflow не входят.

Настройки централизованы в `config/ev3`, `config/quest`, `config/shared` и `config/tooling`.
Runtime-основа и отличия профилей объединяются генератором; robot ID, discovery/port,
допуск приводов, версия/размеры wire и ожидаемый bundle hash имеют по одному источнику.
Все восемь канонических конфигов/manifest после переноса совпадают по байтам с предыдущими;
протокольные и конфигурационные хэши сохранены. Новые регрессии проверяют композицию,
запрет повторения общих значений и отсутствие частичной записи при ошибке валидации.
Анализ выполнен на синтетических данных, очистка проверена только в режиме preview.

## Незакрытые проверки

| Область | Состояние и следующий шаг |
|---|---|
| Механическая модель | BOM и LDraw фиксируют структуру, но модель остаётся DESIGN PLACEHOLDER / UNQUALIFIED. Нет подтверждённых измерений соосности, противовеса, упоров, QR mounts и поведения при потере питания; READY остаётся заблокирован до квалификации |
| Полнота программных тестов EV3 и Quest | Не подтверждена: сопоставить реализованную функциональность обеих платформ с автоматическими тестами production-кода по [План проверки §3](test-plan.md#sec-9-1-2), устранить пробелы и выполнить применимый software regression до DEVICE/MANUAL qualification |
| Host lifecycle tests | [PHANTOM CLI](tooling.md) проверяет pair state, process helpers и сбор логов Quest с fake SSH/ADB и дочерними процессами, включая отказы. Полнота остальных lifecycle/install behaviors с подменёнными зависимостями не подтверждена; поиск строк в исходниках не заменяет такие тесты |
| Unity EditMode и APK BUILD | Активировать лицензию Unity 6000.3.22f1 в Unity Hub; выполнить `python tooling test --target quest`, затем `python tooling build --target quest --profile diagnostic`. После успешного цикла повторить TEST/BUILD обеих платформ по запросу пользователя |
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
| Упрощение режимов сборки и запуска | Инструменты поддерживают Diagnostic и Release; запуск — START, дополнительный сбор логов включается параметром `--capture-debug`. Отдельные DeepDebug/DEBUG удалены |
| C++-службы сети EV3 | Службы network и mDNS перенесены в `ev3/src` на C++14; native wire codec, HMAC/session и Unix IPC проверяются C++ tests. Криптография использует OpenSSL, публикация DNS-SD — системный Avahi. Проверка на EV3 — NOT_RUN |
| Блокировка после критического loop overrun | Исправлены latched `STOPPED + FAULT_LOOP_OVERRUN`, запрет ACK до устранения причины и восстановление без автоматического движения. Пороги в configgen и runtime ограничены 60/100 ms; C++ host regression подтверждён. Проверка на EV3 — `NOT_RUN` |
| Полный Diagnostic profile | Спецификация разрешает полный продуктовый scope в Diagnostic при тех же safety gates, что и Release. Текущие configgen/Stage-3 runtime допускают только network-only Diagnostic; расширение профилей относится к следующим этапам |
| GitHub Actions | Workflow `.github/workflows/ci.yml` существует: документация, схемы/Python tools, C++ host tests/sanitizers, ARM cross-build. Успешный запуск в GitHub не подтверждён; полного Unity test/build job в workflow нет |

## Ближайший шаг

Подготовить свежую network-only Diagnostic пару: `actuator_scope_mask=safety_observation_mask=0x00`,
`required_user_inputs=NONE`; физическое движение запрещено, motor A может отсутствовать.
Последняя локальная проверка пары (2026-09-10) дала `LOCAL_PAIR_STATE_ABSENT`;
перед запуском проверить состояние заново и при отсутствии пары выполнить явный
`install --target ev3` / `install --target quest` с доверенным EV3 fingerprint и назначенным Quest serial.

Порядок: TEST → BUILD → EV3 INSTALL и Quest INSTALL → EV3 START → Quest START.
Разобрать timings, readiness, first failure и terminal state; DEVICE и применимые
Stage-3 manual cases выполнить отдельно. Команды и границы фаз —
[Разработка и развёртывание §4.2](engineering.md#sec-8-5-1).

Физические критерии MANUAL ACCEPTANCE — NOT_RUN; проверяются по
[test-plan](test-plan.md#sec-9-23). Существующие runners и measurement metadata с HIL label
не переименованы; при работе с ними учитывать ручные cases и не считать legacy label
доказательством автономной квалификации.
