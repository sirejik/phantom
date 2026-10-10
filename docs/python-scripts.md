# Скрипты и инструменты PHANTOM

Главный каталог инструментов проекта, сгруппированный по [конвейеру разработки](engineering.md#sec-engineering-pipeline). Команды запускаются из корня репозитория. Для каждого файла указаны назначение и реальный потребитель либо ручная точка запуска.

Включены проектные scripts/tools, Python-библиотеки, помощники тестирования и внутренние исполняемые модули. Конфигурации проектов и окружения сборки описаны в [engineering.md](engineering.md#sec-engineering-build). Код тестов C++ и C# находится в проектах EV3 и Quest и не перечисляется как скрипты. Код сборки внутри Unity-проекта, обычный код приложения и служб, сторонние SDK, `.meta`, схемы и сгенерированные C++/C# определения относятся к исходникам и входам этих инструментов.

Для обычного цикла разработки используйте dispatcher; внутренние помощники вызываются соответствующими инструментами запуска. Регрессии самих Python/PowerShell-инструментов выделены в разделе 8.

## 1. Точки входа и среда

| Файл | Что делает | Кто вызывает / где работает |
|---|---|---|
| [scripts/phantom.cmd](../scripts/phantom.cmd) | Запускает PowerShell dispatcher с execution policy для текущего процесса. | Точка входа из документации и скилов. |
| [scripts/phantom.ps1](../scripts/phantom.ps1) | Вызывает runner одной выбранной операции. | phantom.cmd. |
| [tools/toolchain.ps1](../tools/toolchain.ps1) | Поиск Unity, .NET SDK, ADB, Android tools и WSL по manifest. | Общий модуль build/test/device runners. |
| [.github/workflows/ci.yml](../.github/workflows/ci.yml) | Запускает проверки docs/schemas/tools, C++ tests и ARM-сборку. | GitHub Actions на Ubuntu; без устройств и Unity job. |

## 2. Изменения схем и статические проверки

Генераторы обновляют производные файлы; `--check` проверяет их актуальность. Проверка документации не входит в BUILD. `doclint.py` уже вызывает `docindex.py --check` и `protocolgen.py --check --include-docs`; остальные проверки имеют отдельные области ответственности.

| Файл | Что делает | Кто вызывает / где работает |
|---|---|---|
| [tools/protocolgen.py](../tools/protocolgen.py) | Проверяет wire/IPC schemas и semantics; генерирует общие C++/C#/Python определения, канонические JSON, хэши, golden vectors и справочник в docs. | ev3-build.ps1, quest-build.ps1, doclint и CI. |
| [tools/configgen.py](../tools/configgen.py) | Проверяет исходную конфигурацию по схемам и реестру MEASURED; создаёт канонические runtime-конфигурации и manifest с хэшами. | обе сборки и CI. |
| [tools/docindex.py](../tools/docindex.py) | Генерирует локальные оглавления нормативных документов, проверяет их через `--check`, ищет разделы через `--locate`. | doclint, implementation_map_check и CI. |
| [tools/doclint.py](../tools/doclint.py) | Проверяет нумерацию, anchors, локальные ссылки и связи критериев/требований с матрицей приёмки. | CI. |
| [tools/implementation_map_check.py](../tools/implementation_map_check.py) | Проверяет implementation-map.json: допустимость статусов, существование владельцев/anchors и путей проверок. | CI и test_documentation. |
| [tools/spec_contract_check.py](../tools/spec_contract_check.py) | Проверяет согласованность prose с machine sources: ownership, MEASURED declarations, canonical outputs и protocol identities. | CI и test_documentation. |
| [tools/security_scan.py](../tools/security_scan.py) | Ищет секреты в исходниках, конфигурациях, manifests и переданных пакетах/APK; разрешает только явно перечисленные тестовые fixtures. | CI и provisioning-аудит. |
| [tools/quest_validation/compile_androidlib.ps1](../tools/quest_validation/compile_androidlib.ps1) | Проверяет компиляцию Java bridge до сборки APK. | Ручной запуск на компьютере; требует Unity Android SDK. |
| [protocol/phantom_protocol.py](../protocol/phantom_protocol.py) | Строгий bounded reference codec protocol v1: encode/decode, HMAC, размеры, enums/reserved и semantic validation. | установленный integration runner EV3. |
| [protocol/jcs.py](../protocol/jcs.py) | Канонизирует JSON по RFC 8785. | Импортируют генераторы, build identity и reference codec; также используется integration runner на EV3. |
| [protocol/generated/ipc_layout.py](../protocol/generated/ipc_layout.py) | Генерируемые Python layouts/constants локального IPC. | интеграционный runner EV3 и регрессии IPC layouts. |

## 3. Помощники unit и функциональных тестов на компьютере

Две точки входа: `scripts/phantom.cmd TEST EV3` и `scripts/phantom.cmd TEST QUEST`. Обе собирают тестируемый код и тестовые проекты для компьютера разработчика; готовые ARM-пакет и APK для этого не нужны.

Тесты EV3 находятся в [ev3/tests](../ev3/tests) и написаны на C++. Тесты Quest находятся в [PhantomQuest/Tests/Host](../PhantomQuest/Tests/Host) и [Unity EditMode](../PhantomQuest/Assets/Phantom/Tests) и написаны на C#. Моки, временные файлы, запуск дочерних процессов и их очистка входят в fixtures этих проектов. C# fixture настоящего C#↔C++ обмена сама собирает необходимую C++ зависимость и запускает её. Код тестов и fixtures не является отдельными скриптами и в таблице не перечисляется.

| Файл | Что делает | Кто вызывает / где работает |
|---|---|---|
| [scripts/ev3-test.ps1](../scripts/ev3-test.ps1) | Собирает C++ код и тесты через CMake/Ninja, запускает CTest. `-Profile Diagnostic/Release`, `-Filter` и `-TimeoutSeconds` задают профиль, выбор suites и предел времени. Отсутствие выбранных тестов или провал проверки завершают запуск ошибкой. | TEST EV3; WSL с CMake, Ninja и C++ compiler на компьютере, без устройства EV3. |
| [scripts/quest-test.ps1](../scripts/quest-test.ps1) | По умолчанию запускает NUnit host unit-тесты, затем functional-тесты, затем Unity EditMode с Android target. `-Suite All/Host/Unity` выбирает набор; `-Category All/Unit/Functional` применяется только к host-тестам; `-Filter` — только к Unity. `-TimeoutSeconds` ограничивает каждый запуск, `-Results` задаёт Unity XML. | TEST QUEST; .NET SDK для host-тестов, WSL/CMake/C++ для настоящего обмена с EV3, лицензированный Unity с Android support для EditMode. Шлем не требуется. |

## 4. Сборка и упаковка

Две точки входа: `scripts/phantom.cmd BUILD EV3` и `scripts/phantom.cmd BUILD QUEST`. Они собирают устанавливаемые ARM-пакет и APK; тесты запускаются через TEST. Ниже перечислены только скрипты и инструменты; конфигурационные файлы описаны в [engineering.md](engineering.md#sec-8-6). Поиск установленных инструментов описан в разделе 1; правила профилей и пакетов — в [engineering.md](engineering.md#sec-engineering-build).

Оба сборщика принимают `-Profile Diagnostic/Release` (по умолчанию Diagnostic). Опция `-VerifyReproducibility` выполняет две сборки в `-ReproducibilityWorkspace` и сравнивает `build_id` и хэши файлов. Различие ARM-пакетов завершает проверку ошибкой; различие APK отмечается для исследования готовым ZIP-инструментом.

| Файл | Что делает | Кто вызывает / где работает |
|---|---|---|
| [scripts/ev3-build.ps1](../scripts/ev3-build.ps1) | Проверяет окружение и актуальность генерируемых входов, собирает C++ службы в закреплённом Docker-образе, создаёт manifest и ARM-архив, проверяет пакет. `-OutputRoot` задаёт каталог сборки, `-PackageRoot` — каталог архивов. Тестовые targets отключены. | BUILD EV3; компьютер с Docker Linux engine, закреплённым cross-image и Python. |
| [scripts/quest-build.ps1](../scripts/quest-build.ps1) | Проверяет окружение и генерируемые входы, запускает Unity Android BUILD, проверяет подпись и содержимое APK. `-Output` задаёт путь APK, `-SigningDirectory` — каталог ключа подписи, `-TimeoutSeconds` — предел ожидания Editor. | BUILD QUEST; компьютер с лицензированным Unity, Android build support, Python и подготовленным ключом подписи. |
| [scripts/build-environment.ps1](../scripts/build-environment.ps1) | Проверяет Docker Linux engine и наличие закреплённого образа EV3 либо Unity Android SDK/JDK; выполняет повторные сборки и сравнение их результатов по `-VerifyReproducibility`. | Внутренний PowerShell-модуль обоих сборщиков. |
| [tools/source_hash.py](../tools/source_hash.py) | Вычисляет хэш содержимого входных файлов компонента, включая незакоммиченные изменения. Позволяет отличить сборки разного кода при одном Git commit. | Внутренний помощник обоих сборщиков и проверки пакета. Не компилирует код. |
| [tools/build_identity.py](../tools/build_identity.py) | Вычисляет `build_id` из компонента, профиля, хэша исходников, протокола, конфигурации и окружения. Повторная сборка тех же входов получает тот же идентификатор. | Общая реализация для обоих сборщиков и проверки пакета; отдельного шага запуска не требует. |
| [tools/artifact_check.py](../tools/artifact_check.py) | Проверяет результат BUILD: соответствие входам, manifest и хэши, состав пакета; для EV3 — ARM/soft-float, права и безопасные пути архива, для Quest — встроенные данные APK. | Оба сборщика вызывают его в конце BUILD, до сообщения об успехе. Провал завершает сборку ошибкой. |

Хэш исходников и `build_id` описывают входы сборки; SHA-256 готового APK/архива
описывает полученный файл. Это разные значения. Три Python-помощника используются
внутри BUILD и не добавляют операций в конвейер. Подпись APK проверяется сборщиком
через Android `apksigner`.

## 5. Установка на устройства

Две команды установки включают настройку назначенного устройства, передачу файлов и проверку установленного пакета. Первое назначение пары требует доверенного EV3 fingerprint и Quest serial; повторная установка сохраняет ключи и данные. Запуск и тесты вызываются отдельно. Внутренние помощники перечислены в разделе 9.

| Файл | Что делает | Кто вызывает / где работает |
|---|---|---|
| [scripts/ev3-install.ps1](../scripts/ev3-install.ps1) | Настраивает SSH, пользователей, сетевые credentials и Wi-Fi; передаёт выбранный ARM-пакет, сверяет SHA-256 и устанавливает его. Принимает `-Package`; fingerprint и serial нужны при первом назначении пары. | INSTALL EV3; компьютер и назначенный EV3 через SSH. Службы остаются остановлены. |
| [scripts/quest-install.ps1](../scripts/quest-install.ps1) | Устанавливает APK с разрешениями, сверяет установленный хэш; при первой установке подготавливает CONTROL credential для импорта Diagnostic приложением. Обновление сохраняет credential и данные. | INSTALL QUEST; компьютер и назначенный Quest через ADB. Приложение не запускается. |

## 6. Интеграционные тесты на устройствах

Две точки входа: `scripts/phantom.cmd DEVICE EV3` и `scripts/phantom.cmd DEVICE QUEST`. Quest лежит на столе; EV3 не двигает моторы. Проверки установленной системы и обмена выполняются без оператора. Полнота реализации и аппаратные результаты — в [current-status.md](current-status.md).

| Файл | Что делает | Кто вызывает / где работает |
|---|---|---|
| [scripts/ev3-device-integration-test.ps1](../scripts/ev3-device-integration-test.ps1) | Запускает встроенные проверки EV3 и получает отчёт установленной версии. Моторные выходы должны оставаться нулевыми. | DEVICE EV3; компьютер и назначенный EV3 через SSH. |
| [scripts/quest-device-integration-test.ps1](../scripts/quest-device-integration-test.ps1) | Проверяет отчёт приложения, identity, первый и повторный запуск, отсутствие crash. Вместо `-ExpectedBuildId` опции `-ApkA` и `-ApkB` выбирают проверку сохранения credential после обновления между двумя сборками. | DEVICE QUEST; компьютер и лежащий на столе Quest через ADB. |

## 7. Сбор и анализ диагностики

Два сборщика получают данные назначенного устройства и по умолчанию вызывают общий анализатор. `-SkipAnalysis` оставляет только сбор. Анализ сохранённых данных можно повторить отдельно. Правила данных и доступность метрик — в [metrics-and-logs.md](metrics-and-logs.md).

| Файл | Что делает | Кто вызывает / где работает |
|---|---|---|
| [scripts/ev3-pull-logs.ps1](../scripts/ev3-pull-logs.ps1) | Получает ограниченное число записей journald служб controller/safety/network/mdns; сохраняет JSONL и запускает анализ. Не читает credentials и не управляет моторами. `-Lines`, `-TimeoutSeconds`, `-Destination` ограничивают сбор. | Ручной запуск на компьютере, SSH к назначенному EV3. |
| [scripts/quest-pull-logs.ps1](../scripts/quest-pull-logs.ps1) | Получает диагностические JSONL из каталога приложения и запускает анализ. `-TimeoutSeconds` ограничивает ADB, `-Destination` задаёт каталог данных. | Ручной запуск на компьютере, ADB к назначенному Quest. |
| [tools/analyze_logs.py](../tools/analyze_logs.py) | Единый запуск анализа: `QUEST <inputs> --out <directory>` создаёт отчёты tracking/QR; `EV3` считает записи по службам и предупреждения/ошибки journald. Сводка EV3 не подтверждает физические метрики или аппаратный PASS. | Оба сборщика либо ручной повторный анализ на компьютере. |

## 8. Регрессии самих инструментов

Регрессии удалённых APK diff, симулятора и прежних отдельных test runners убраны вместе с инструментами. Ниже остались проверки действующих генераторов, упаковки, безопасности, анализа и транспорта. Python-тесты проверяют инструменты и библиотеки; тесты приложения и служб остаются на C# и C++. Python suites запускаются CI, `test_pair_state.ps1` — локально в Windows. Он использует fake SSH/ADB/Unity и не подтверждает работу устройств.

| Файл | Что делает | Кто вызывает / где работает |
|---|---|---|
| [tools/quest_validation/test_analyze.py](../tools/quest_validation/test_analyze.py) | Quest analyzer на неполных/legacy и instrumented captures; timestamps, loss/recovery и QR. | CI. |
| [tools/test_artifact_check.py](../tools/test_artifact_check.py) | Compiler facts, package naming, archive traversal/root members, executable modes и обязательные runtime inputs. | CI. |
| [tools/test_build_identity.py](../tools/test_build_identity.py) | Identity inputs, component/profile separation, canonical hex, исключение docs/tests и влияние runtime/toolchain. | CI. |
| [tools/test_configgen.py](../tools/test_configgen.py) | Строгий parsing, schema validation, safety thresholds/scopes, MEASURED lifecycle и стабильность generator без документации. | CI. |
| [tools/test_documentation.py](../tools/test_documentation.py) | Нумерация, ссылки, оглавления, связи требований/схем и полнота этого каталога. | CI. |
| [tools/test_ev3_device_integration.py](../tools/test_ev3_device_integration.py) | Чистые функции integration runner: clock/boot-id/status validation и проверка zero/brake. | CI. |
| [tools/test_ipc_contract.py](../tools/test_ipc_contract.py) | Сверяет Python/C++ IPC layouts и общие vectors. | CI; регрессии сгенерированного IPC. |
| [tools/test_jcs.py](../tools/test_jcs.py) | RFC 8785 числовые/строковые правила, UTF-16 key order, malformed значения и golden vectors. | CI. |
| [tools/test_pair_state.ps1](../tools/test_pair_state.ps1) | Проверяет pair state, первую установку и обновление, сбор логов, повторный запуск Quest и Unity test runner с подменёнными процессами. | Ручной запуск в Windows, без устройств. |
| [tools/test_protocol.py](../tools/test_protocol.py) | Генератор и reference codec: sizes/golden vectors, schema/semantics identities, HMAC, malformed/reserved/enum/NaN cases; независимость BUILD от generated docs. | CI. |
| [tools/test_security_scan.py](../tools/test_security_scan.py) | Обнаружение разных форм секретов, узкие исключения, корректность allowlist и отсутствие секрета в findings. | CI. |

## 9. Запуск и внутренние помощники установки

Это внутренние модули и исполняемый код на EV3; они не добавляют отдельных точек запуска установки или тестов. Самостоятельных команд настройки и передачи нет. START запускает уже установленную систему; правила конфигурации systemd находятся в [engineering.md](engineering.md#sec-8-12).

| Файл | Что делает | Кто вызывает / где работает |
|---|---|---|
| [scripts/install-common.ps1](../scripts/install-common.ps1) | Создаёт или проверяет локальное назначение пары и ключи; запрещает скрытую замену identities и ротацию. | Внутренний модуль обоих установщиков. |
| [scripts/install-device.ps1](../scripts/install-device.ps1) | Настройка EV3, staging credential Quest и передача ARM-пакета. | Внутренние функции установщиков; вне INSTALL не запускаются. |
| [provision/ev3/wifi-autoconnect](../provision/ev3/wifi-autoconnect) | Bounded повтор подключения provisioned Favorite+AutoConnect Wi-Fi. | Установленная phantom-wifi-autoconnect.service. |
| [scripts/pair-state.ps1](../scripts/pair-state.ps1) | Приватное состояние пары, ACL, выбор назначенного Quest и bounded process/ADB helpers. | Общий модуль provisioning/device runners. |
| [scripts/ev3-deploy-common.ps1](../scripts/ev3-deploy-common.ps1) | Общие SSH helpers: target, timeout, stdout/stderr и удалённый отчёт. | EV3 install/start/integration runners. |
| [deploy/scripts/install-release](../deploy/scripts/install-release) | Проверка архива, atomic install runtime/config/units и прав. | ev3-install.ps1 на EV3. |
| [scripts/ev3-start.ps1](../scripts/ev3-start.ps1) | Запуск установленной версии, expected identity, timeout и optional debug capture. | START EV3. |
| [deploy/scripts/start-release](../deploy/scripts/start-release) | Запуск systemd-служб по зависимостям и startup отчёт. | ev3-start.ps1 на EV3. |
| [scripts/quest-start.ps1](../scripts/quest-start.ps1) | Запуск назначенного приложения, startup/build/credential readiness и optional debug capture. | START QUEST. |
| [provision/ev3/bootstrap](../provision/ev3/bootstrap) | Подготавливает пользователей, права, CONTROL key и Wi-Fi service. | Внутренняя настройка EV3 из install-device.ps1. |
| [provision/ev3/install-deployment-key](../provision/ev3/install-deployment-key) | Устанавливает deployment SSH key через доверенного bootstrap user при первом INSTALL. | Внутренняя настройка EV3 из install-device.ps1. |
| [deploy/scripts/run-device-integration-test](../deploy/scripts/run-device-integration-test) | Проверяет кандидата и вызывает установленный integration runner. | Внутренний шаг DEVICE EV3 на устройстве. |
| [deploy/scripts/device-integration-test.py](../deploy/scripts/device-integration-test.py) | Проверяет службы/config/identity, I/O metadata, zero-output, сеть/discovery/protocol; пишет отчёт. | Внутренний установленный runner DEVICE EV3. |
| [tools/quest_validation/analyze.py](../tools/quest_validation/analyze.py) | Реализация анализа Quest JSONL: samples, guided captures, tracking/QR; создаёт отчёты. | Внутренний модуль analyze_logs.py. |

## 10. Очистка рабочих данных

Очистка показывает выбранные файлы; удаление включается через `-Apply`.

| Файл | Что делает | Кто вызывает / где работает |
|---|---|---|
| [scripts/build-clean.ps1](../scripts/build-clean.ps1) | Предпросмотр и очистка build outputs, с сохранением свежих пакетов по умолчанию. | Ручная команда из AGENTS.md. |
| [scripts/results-clean.ps1](../scripts/results-clean.ps1) | Предпросмотр и очистка временных локальных отчётов. | Ручная уборка results. |

## 11. Границы инструментов

Часть инструментов вызывается автоматически, часть предназначена для явного ручного запуска. Source hash выбирает входы, build identity объединяет их, artifact check проверяет готовый пакет. Проверки документации разделены по Markdown, карте реализации и машинным контрактам. Build cleanup сохраняет свежие пакеты, results cleanup очищает временные отчёты.

Полнота каталога проверяется `tools/test_documentation.py`: новый инструмент требует записи в таблице, удалённый — удаления ссылки. При добавлении нового каталога инструментов расширьте область этой проверки.
