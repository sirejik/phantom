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

## Ревизия инструментов

[Каталог](python-scripts.md) описывает инструменты и внутренние модули по этапам
конвейера. Код тестов C++ и C# отделён от каталога скриптов; четыре C# host-набора
перенесены из tools в `PhantomQuest/Tests/Host`. Удалена обёртка `ev3-deploy-install.ps1`, повторявшая
TRANSFER и INSTALL. Полнота каталога проверяется `test_documentation.py`.
Quest EditMode runner требует свежий успешный непустой XML и ограничивает время запуска;
регрессии с fake Unity проверяют успешный отчёт, отказ, пустой/отсутствующий/повреждённый
отчёт, timeout и ненулевой exit code. Все 10 Python suites, PowerShell lifecycle tests,
Java compile и C# host suites прошли локально. Это не подтверждает Unity EditMode
с реальным Editor, APK BUILD или работу устройств.

TEST имеет две точки входа: `ev3-test.ps1` (CMake/CTest) и `quest-test.ps1`
(.NET/NUnit и Unity EditMode). Моки UDP и fixture настоящего C#↔C++ обмена входят
в C#/C++ проекты тестов; Python simulator и отдельные host runners удалены.
BUILD также имеет две точки входа: `ev3-build.ps1` и `quest-build.ps1`;
подготовка окружения остаётся внутренним PowerShell-модулем.
После ревью повторно прошли 6 C++ suites, 3 NUnit unit-группы и 10 functional cases,
включая настоящий C#↔C++ UDP/IPC. Diagnostic ARM-пакет повторно собран и проверен.
Ревью исправило сравнение времени snapshot после синхронного IPC, очистку процессов,
ограничения времени запуска и восстановление закреплённых NuGet-зависимостей.

## Незакрытые проверки

INSTALL объединяет настройку и установку для каждой платформы; отдельных PROVISION/TRANSFER
команд больше нет. При первой установке назначение пары и ключи создаются локально,
credential Quest подготавливается после установки Diagnostic APK. Повторное обновление
не заменяет ключ; восстановление и ротация явные. Код проверяется с fake ADB/SSH;
установка на реальные устройства после объединения — `NOT_RUN`.
DEVICE также имеет две точки входа; credential persistence включён в DEVICE QUEST
через `-ApkA`/`-ApkB`. Сбор диагностики выполняют два `*-pull-logs.ps1`, анализ —
`tools/analyze_logs.py`. Для EV3 сейчас реализована сводка journald по службам и severity,
а не анализ FlightRecorder или физических метрик. Проверки на реальных устройствах — `NOT_RUN`.

Конфигурации сборки EV3 собраны в `ev3/`: CMake-проект и `toolchains/`.
Образ/digest и ожидаемые сведения платформы берутся из единственного lock-файла;
CI и локальная сборка используют общую команду. Отсутствующий risk record обозначен
`null`; Release gate остаётся заблокирован. После переноса Diagnostic ARM BUILD
и 6 host C++ suites проверены повторно; запуск изменённого workflow на GitHub — `NOT_RUN`.

| Область | Состояние и следующий шаг |
|---|---|
| Механическая модель | BOM и LDraw фиксируют структуру, но модель остаётся DESIGN PLACEHOLDER / UNQUALIFIED. Нет подтверждённых измерений соосности, противовеса, упоров, QR mounts и поведения при потере питания; READY остаётся заблокирован до квалификации |
| Полнота программных тестов EV3 и Quest | Не подтверждена: сопоставить реализованную функциональность обеих платформ с автоматическими тестами production-кода по [План проверки §3](test-plan.md#sec-9-1-2), устранить пробелы и выполнить применимый software regression до DEVICE/MANUAL qualification |
| Host lifecycle tests | [test_pair_state.ps1](../tools/test_pair_state.ps1) проверяет pair state, process helpers и сбор логов Quest с fake SSH/ADB/Python, включая отказы. Полнота остальных lifecycle/install behaviors с подменёнными зависимостями не подтверждена; поиск строк в исходниках не заменяет такие тесты |
| Unity EditMode и APK BUILD | Активировать лицензию Unity 6000.3.22f1 в Unity Hub; выполнить `scripts/phantom.cmd TEST QUEST`, затем `scripts/phantom.cmd BUILD QUEST -Profile Diagnostic`. После успешного цикла повторить TEST/BUILD обеих платформ по запросу пользователя |
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
| Упрощение режимов сборки и запуска | Инструменты поддерживают Diagnostic и Release; запуск — START, дополнительный сбор логов включается его параметром CaptureDebug. Отдельные DeepDebug/DEBUG удалены |
| C++-службы сети EV3 | Службы network и mDNS перенесены в `ev3/src` на C++14; native wire codec, HMAC/session и Unix IPC проверяются C++ tests. Криптография использует OpenSSL, публикация DNS-SD — системный Avahi. Проверка на EV3 — NOT_RUN |
| Блокировка после критического loop overrun | Исправлены latched `STOPPED + FAULT_LOOP_OVERRUN`, запрет ACK до устранения причины и восстановление без автоматического движения. Пороги в configgen и runtime ограничены 60/100 ms; C++ host regression подтверждён. Проверка на EV3 — `NOT_RUN` |
| Полный Diagnostic profile | Спецификация разрешает полный продуктовый scope в Diagnostic при тех же safety gates, что и Release. Текущие configgen/Stage-3 runtime допускают только network-only Diagnostic; расширение профилей относится к следующим этапам |
| GitHub Actions | Workflow `.github/workflows/ci.yml` существует: документация, схемы/Python tools, C++ host tests/sanitizers, ARM cross-build. Успешный запуск в GitHub не подтверждён; полного Unity test/build job в workflow нет |

## Ближайший шаг

Подготовить свежую network-only Diagnostic пару: `actuator_scope_mask=safety_observation_mask=0x00`,
`required_user_inputs=NONE`; физическое движение запрещено, motor A может отсутствовать.
Последняя локальная проверка пары (2026-09-10) дала `LOCAL_PAIR_STATE_ABSENT`;
перед запуском проверить состояние заново и при отсутствии пары выполнить явный
`INSTALL EV3` / `INSTALL QUEST` с доверенным EV3 fingerprint и назначенным Quest serial.

Порядок: TEST → BUILD → EV3 INSTALL и Quest INSTALL → EV3 START → Quest START.
Разобрать timings, readiness, first failure и terminal state; DEVICE и применимые
Stage-3 manual cases выполнить отдельно. Команды и границы фаз —
[Разработка и развёртывание §4.2](engineering.md#sec-8-5-1).

Физические критерии MANUAL ACCEPTANCE — NOT_RUN; проверяются по
[test-plan](test-plan.md#sec-9-23). Существующие runners и measurement metadata с HIL label
не переименованы; при работе с ними учитывать ручные cases и не считать legacy label
доказательством автономной квалификации.
