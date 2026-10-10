# Скрипты и инструменты PHANTOM

Единый каталог: 27 файлов в `scripts`, 9 дополнительных PowerShell/C# файлов в `tools`,
33 Python-файла и 6 shell helpers на EV3. Путь документа сохранён; описаны все языки.
Сборки, кэши и установленные зависимости не включены. Команды запускаются из корня проекта.
Декларативные CMake/systemd/config файлы описаны в [engineering.md](engineering.md).

Каталог объясняет необходимость функции, но не подтверждает PASS. Пробелы проверок
и оставшаяся поддержка DeepDebug/DEBUG — в [current-status.md](current-status.md).

## 1. Скрипты на компьютере

### 1.1. Общие команды и рабочие данные

| Файл | Назначение | Потребитель / причина сохранения |
|---|---|---|
| [scripts/phantom.cmd](../scripts/phantom.cmd) | Запускает PowerShell dispatcher с execution policy для текущего процесса. | Точка входа из документации и скилов; CMD. |
| [scripts/phantom.ps1](../scripts/phantom.ps1) | Вызывает runner одной выбранной операции. | phantom.cmd; разделяет TEST, BUILD, установку, запуск и интеграционные тесты. |
| [scripts/pair-state.ps1](../scripts/pair-state.ps1) | Приватное состояние пары, ACL, выбор назначенного Quest и bounded process/ADB helpers. | Общий модуль provisioning/device runners; test_pair_state.ps1. |
| [scripts/build-clean.ps1](../scripts/build-clean.ps1) | Предпросмотр и очистка build outputs, с сохранением свежих пакетов по умолчанию. | Ручная команда из AGENTS.md; использована для уборки проекта. |
| [scripts/results-clean.ps1](../scripts/results-clean.ps1) | Предпросмотр и очистка временных локальных отчётов. | Ручная уборка results; credentials и pair state вне её области. |
| [scripts/reproducibility-test.ps1](../scripts/reproducibility-test.ps1) | Две сборки компонента, сравнение identity и байтов; разбор различий APK. | Проверка воспроизводимости из engineering-contracts.md; отдельная от обычного BUILD. |

### 1.2. EV3: тесты, сборка и установка

| Файл | Назначение | Потребитель / причина сохранения |
|---|---|---|
| [scripts/ev3-test.ps1](../scripts/ev3-test.ps1) | Host C++ build и CTest в WSL. | TEST EV3; заменяет ненужную отдельную host-сборку. |
| [scripts/ev3-build.ps1](../scripts/ev3-build.ps1) | Generated inputs, ARM compile, упаковка и artifact validation. | BUILD EV3 и reproducibility-test.ps1. |
| [scripts/ev3-armel-docker.ps1](../scripts/ev3-armel-docker.ps1) | Pinned Docker cross-build, runtime/config files и manifest. | Внутренний шаг ev3-build.ps1. |
| [scripts/ev3-armel-build](../scripts/ev3-armel-build) | ARM compilation controller/safety внутри Linux-контейнера. | ev3-armel-docker.ps1 и GitHub Actions. |
| [scripts/ev3-package.ps1](../scripts/ev3-package.ps1) | Детерминированный tar.gz, Unix modes, checksum и sidecars. | ev3-build.ps1; создаёт устанавливаемый пакет. |
| [scripts/ev3-deploy-common.ps1](../scripts/ev3-deploy-common.ps1) | Общие SSH helpers: target, timeout, stdout/stderr и удалённый отчёт. | EV3 transfer/install/start/integration runners; test_pair_state.ps1. |
| [scripts/ev3-transfer.ps1](../scripts/ev3-transfer.ps1) | Upload в staging, SHA-256 и atomic finalize, без установки. | TRANSFER EV3 и ev3-deploy-install.ps1. |
| [scripts/ev3-install.ps1](../scripts/ev3-install.ps1) | Удалённый installer конкретного build_id/SHA-256, без запуска. | INSTALL EV3 и ev3-deploy-install.ps1. |
| [scripts/ev3-deploy-install.ps1](../scripts/ev3-deploy-install.ps1) | TRANSFER затем INSTALL с прекращением при первом отказе. | Команда установки пакета из engineering.md; без START. |
| [scripts/ev3-start.ps1](../scripts/ev3-start.ps1) | Запуск установленной версии, expected identity, timeout и optional debug capture. | START EV3; DEBUG пока legacy alias, см. current-status.md. |
| [scripts/ev3-device-integration-test.ps1](../scripts/ev3-device-integration-test.ps1) | Запуск EV3 integration wrapper, получение отчёта кандидата. | DEVICE EV3; реальная система без движения. |

### 1.3. Quest: тесты, сборка и установка

| Файл | Назначение | Потребитель / причина сохранения |
|---|---|---|
| [scripts/quest-test.ps1](../scripts/quest-test.ps1) | Unity EditMode suite с фильтром и XML/log результатом. | TEST QUEST; PlayMode и полное покрытие этим runner не подтверждены. |
| [scripts/quest-build.ps1](../scripts/quest-build.ps1) | Unity Android build, подпись и artifact validation. | BUILD QUEST и reproducibility-test.ps1. |
| [scripts/quest-install.ps1](../scripts/quest-install.ps1) | Установка на назначенный Quest, проверка installed APK hash. | INSTALL QUEST и persistence test; сохраняет app data. |
| [scripts/quest-start.ps1](../scripts/quest-start.ps1) | Запуск назначенного приложения, startup/build/credential readiness и optional debug capture. | START QUEST; readiness не подтверждает tracking или сетевой handshake. |
| [scripts/quest-device-integration-test.ps1](../scripts/quest-device-integration-test.ps1) | App report, identity, первый/повторный запуск и crash logs. | DEVICE QUEST; полнота test-plan cases и выполнение без надетого шлема ещё не подтверждены. |
| [scripts/quest-credential-persistence-test.ps1](../scripts/quest-credential-persistence-test.ps1) | Два разных APK и готовность credential после обновления. | Аппаратная регрессия из engineering-contracts.md; проверяет store readiness, не сетевую аутентификацию. |
| [scripts/quest-pull-logs.ps1](../scripts/quest-pull-logs.ps1) | Bounded получение JSONL с назначенного Quest и запуск analyzer. | Ручной сбор записей; pair-state helpers и проверка exit code анализа. |

### 1.4. Подготовка пары

| Файл | Назначение | Потребитель / причина сохранения |
|---|---|---|
| [scripts/provision-fixed-pair.ps1](../scripts/provision-fixed-pair.ps1) | Приватный pair state, SSH identity и CONTROL key; подготовка обеих платформ. | PROVISION PAIR; обычный повтор не вращает credentials. |
| [scripts/ev3-provision-maintenance.ps1](../scripts/ev3-provision-maintenance.ps1) | SSH fingerprint, bootstrap/helpers, пользователи, CONTROL credential и Wi-Fi. | EV3 шаг provision-fixed-pair.ps1, отдельно от INSTALL. |
| [scripts/quest-provision-credential.ps1](../scripts/quest-provision-credential.ps1) | Provisioning drop CONTROL key для импорта Diagnostic приложением. | provision-fixed-pair.ps1 и persistence test; без секретов в APK. |

## 2. Дополнительные инструменты и C# harnesses

| Файл | Назначение | Потребитель / причина сохранения |
|---|---|---|
| [tools/toolchain.ps1](../tools/toolchain.ps1) | Поиск Unity, ADB, Android tools и WSL по manifest. | Общий модуль build/test/device runners. |
| [tools/test_pair_state.ps1](../tools/test_pair_state.ps1) | Pair-state/process helpers, сбор логов, бинарные credentials и два запуска Quest с fake SSH/ADB/Python. | Локальная проверка изоляции пары, provisioning admission и отказа при отсутствующем/неуспешном отчёте повторного запуска; без устройств. |
| [tools/quest_validation/compile_androidlib.ps1](../tools/quest_validation/compile_androidlib.ps1) | Java androidlib compilation bundled javac до полной Unity-сборки. | Быстрая локальная проверка; не JNI/runtime test. При отсутствии target jar допускает установленный SDK с сообщением. |
| [tools/quest_validation/compile_and_smoke.ps1](../tools/quest_validation/compile_and_smoke.ps1) | Unity-free C# runtime compilation и три C# suites. | run_udp_integration.ps1 и самостоятельный запуск; не Unity asset/SDK tests. |
| [tools/quest_validation/run_udp_integration.ps1](../tools/quest_validation/run_udp_integration.ps1) | C# UDP client против Stub EV3 и настоящего Python worker на loopback. | Карта реализации Stage 3; fault injection и interop без устройств. |
| [tools/quest_validation/CoreSmoke.cs](../tools/quest_validation/CoreSmoke.cs) | Production mapping, FK/IK, HMAC, calibration и state logic. | compile_and_smoke.ps1; исполняемый C# harness. |
| [tools/quest_validation/Stage3CoreTests.cs](../tools/quest_validation/Stage3CoreTests.cs) | Client session/retry/telemetry и UI models с подменёнными зависимостями. | compile_and_smoke.ps1; регрессии C# компонентов. |
| [tools/quest_validation/GoldenVectorInterop.cs](../tools/quest_validation/GoldenVectorInterop.cs) | C# decode и побайтное round-trip общих 21 golden datagrams. | compile_and_smoke.ps1; межъязыковой codec contract. |
| [tools/quest_validation/UdpIntegration.cs](../tools/quest_validation/UdpIntegration.cs) | Production C# network client по настоящему loopback UDP. | run_udp_integration.ps1; отдельный от fake-transport сетевой path. |

## 3. Python-файлы

Python нужен для generators, analyzers, reference codecs и их тестов. Прикладные
EV3-службы переводятся на C++14; существующие network/mDNS пока поставляются.
Их удаление до замены лишит приложение сети. Ниже перечислены все 33 Python-файла.

### 3.1. Генерация схем и конфигурации — компьютер

| Файл | Назначение | Потребитель / причина сохранения |
|---|---|---|
| [tools/protocolgen.py](../tools/protocolgen.py) | Проверяет wire/IPC schemas и semantics; генерирует общие C++/C#/Python определения, канонические JSON, хэши, golden vectors и справочник в docs. Нужен для согласованности формата между реализациями. `--check` проверяет машинные outputs, `--check --include-docs` также справочник. | ev3-build.ps1, quest-build.ps1, doclint и CI. Без генерации приходится вручную синхронизировать layout/identity между языками. |
| [tools/configgen.py](../tools/configgen.py) | Проверяет исходную конфигурацию по схемам и реестру MEASURED; создаёт канонические runtime-конфигурации и manifest с хэшами. Не допускает неизвестные поля, неподтверждённые значения и несогласованные safety gates. | обе сборки и CI; schema/MEASURED validation и canonical outputs не выполняются компилятором. |

### 3.2. Сборка и безопасность пакетов — компьютер

| Файл | Назначение | Потребитель / причина сохранения |
|---|---|---|
| [tools/source_hash.py](../tools/source_hash.py) | Хэширует объявленные входы исходного кода компонента. Документация, её Unity metadata и кэши исключаются. Нужен как вход build identity; для EV3 есть единый список `EV3_SOURCE_INPUTS`. | сборщики EV3/Quest и artifact_check. Один алгоритм вычисления source hash вместо отдельных реализаций. |
| [tools/build_identity.py](../tools/build_identity.py) | Вычисляет детерминированный build_id из компонента, профиля и хэшей входов. Позволяет отличать установленные версии и связывать их с проверками. | сборщики и artifact_check импортируют/вызывают один алгоритм идентичности. |
| [tools/artifact_check.py](../tools/artifact_check.py) | Проверяет готовый пакет: metadata, identity, hashes, target architecture, профиль, toolchain lock; APK identity и EV3 archive состав/права/безопасность путей. Нужен, чтобы результат сборки можно было установить. | ev3-build.ps1 и quest-build.ps1; проверяет реальные пакеты, а не присутствие слов в исходниках. |
| [tools/apk_repro_diff.py](../tools/apk_repro_diff.py) | Сравнивает ZIP entries двух APK, включая изменённые и переименованные одинаковые данные. Нужен для объяснения различий повторных Unity-сборок; не тестирует приложение. | reproducibility-test.ps1. Разбор ZIP entries объясняет различия APK, которых не видно из двух SHA-256. |
| [tools/security_scan.py](../tools/security_scan.py) | Ищет секреты в исходниках, конфигурациях, manifests и переданных пакетах/APK; разрешает только явно перечисленные тестовые fixtures. Нужен, чтобы credentials не попали в поставку; содержимое обнаруженного секрета не печатается. | CI и provisioning-аудит; проверяет реальные данные на credentials, не дублирует компиляцию. |

### 3.3. Документация и нормативные связи — компьютер

| Файл | Назначение | Потребитель / причина сохранения |
|---|---|---|
| [tools/docindex.py](../tools/docindex.py) | Генерирует локальные оглавления нормативных документов, проверяет их через `--check`, ищет разделы через `--locate`. Сохраняет стабильные anchors и старые идентификаторы ссылок. | doclint, implementation_map_check и CI. Генерация TOC и locator используются в работе с документацией. |
| [tools/doclint.py](../tools/doclint.py) | Проверяет нумерацию, anchors, локальные ссылки и связи критериев/требований с матрицей приёмки. Находит формальные дефекты документации, но не доказывает отсутствие смысловых противоречий. | CI; относительные ссылки, anchors, нумерация и traceability требуют собственного валидатора. |
| [tools/implementation_map_check.py](../tools/implementation_map_check.py) | Проверяет implementation-map.json: допустимость статусов, существование владельцев/anchors и путей проверок. Нужен, чтобы карта реализации ссылалась на реальные источники. | CI и test_documentation; проверяет machine map, которую общий Markdown lint не валидирует. |
| [tools/spec_contract_check.py](../tools/spec_contract_check.py) | Проверяет согласованность prose с machine sources: ownership, MEASURED declarations, canonical outputs и protocol identities. Находит конкурирующие точные wire layouts и незавершённые изменения контракта. | CI и test_documentation; проверки связей prose/MEASURED с источниками и identity артефактами. |

### 3.4. Анализ данных и межкомпонентные проверки — компьютер

| Файл | Назначение | Потребитель / причина сохранения |
|---|---|---|
| [tools/quest_validation/analyze.py](../tools/quest_validation/analyze.py) | Анализирует JSONL Quest, валидность и происхождение samples, guided captures, tracking/QR результаты; создаёт отчёты. Не превращает отсутствующие или неполные данные в PASS. | quest-pull-logs.ps1; интерпретирует реальные JSONL captures. Полнота покрытия новых метрик не подтверждена. |
| [tools/quest_validation/real_server_harness.py](../tools/quest_validation/real_server_harness.py) | Запускает существующий EV3 network worker на loopback с временной конфигурацией и публичным тестовым ключом. Нужен для проверки Quest client именно с реальным worker, а не только со второй реализацией в Stub EV3. Не управляет физическими моторами. | run_udp_integration.ps1. Проверяет клиент с настоящим worker; Stub EV3 нужен отдельно для инъекции отказов. |

### 3.5. Общие библиотеки — импортируются другими файлами

| Файл | Назначение | Потребитель / причина сохранения |
|---|---|---|
| [protocol/jcs.py](../protocol/jcs.py) | Единственная Python-реализация RFC 8785 JSON canonicalization: порядок ключей, строки и числовая сериализация. Нужна для одинаковых хэшируемых байтов в генераторах и runtime. | generators, build_identity, codec и network worker импортируют общий canonicalizer. Замена json.dumps нарушит RFC 8785. |
| [protocol/phantom_protocol.py](../protocol/phantom_protocol.py) | Строгий bounded reference codec protocol v1: encode/decode, HMAC, размеры, enums/reserved и semantic validation. Используется инструментами, stub и существующим Python network worker. | действующий network worker, integration runner, simulator и harness. Это используемая библиотека, а не лишний CLI. |
| [protocol/generated/ipc_layout.py](../protocol/generated/ipc_layout.py) | Генерируемые Python layouts/constants локального IPC. Нужны worker для согласия с C++ controller и golden vectors; вручную не редактируются. | network worker и IPC-тесты. Генерируемые definitions не поддерживаются вручную. |

### 3.6. Тестовые подмены — компьютер

| Файл | Назначение | Потребитель / причина сохранения |
|---|---|---|
| [sim/ev3-simulator/phantom_simulator.py](../sim/ev3-simulator/phantom_simulator.py) | Stub EV3: UDP/HMAC server, состояния, references, ограничения движения и сетевые сценарии отказа. Нужен для разработки и тестов Quest без физического EV3. Не выполняет motor I/O. | run_udp_integration.ps1 использует сетевую подмену для fault scenarios; это реальный внешний вход production C# client. |

### 3.7. Существующие службы и проверки на EV3

| Файл | Назначение | Потребитель / причина сохранения |
|---|---|---|
| [ev3/network/phantom_network.py](../ev3/network/phantom_network.py) | Действующая прежняя Python-служба network-only Stage 3: bounded UDP, HMAC/session, rate limiting, IPC с controller и telemetry. Без actuator authority. До C++-переноса обеспечивает текущий сетевой runtime. | до C++-переноса: включён в EV3 package и systemd runtime; удаление сейчас лишит систему сети. |
| [ev3/network/phantom_mdns.py](../ev3/network/phantom_mdns.py) | Действующая прежняя Python-служба публикации controller identity через системный Avahi/D-Bus. Нужна для discovery EV3; собственный mDNS stack не реализует. Также ожидает перенос на C++. | до C++-переноса: включён в EV3 package и systemd runtime; удаление лишит EV3 discovery. |
| [deploy/scripts/device-integration-test.py](../deploy/scripts/device-integration-test.py) | Автоматический integration runner на установленном EV3: службы/config/identity, I/O metadata, zero-output, сеть/discovery/protocol; пишет отчёт. Проверяет реальную систему в нулевом actuator scope; не является приложением управления и не должен вращать моторы. | сборка устанавливает runner, device wrapper запускает его на EV3. Проверяет установленную систему без motor motion. |

### 3.8. Python-тесты — компьютер

Эти файлы проверяют перечисленные Python-инструменты, библиотеки и прежний
Python network worker. Они не заменяют unit/functional tests C++ controller и
C# приложения. Изолированные тесты runner не запускают интеграционный тест на EV3.

| Файл | Назначение | Потребитель / причина сохранения |
|---|---|---|
| [tools/test_protocol.py](../tools/test_protocol.py) | Генератор и reference codec: sizes/golden vectors, schema/semantics identities, HMAC, malformed/reserved/enum/NaN cases; независимость BUILD от generated docs. Защищает wire contract от регрессий. | CI; выполняет реальный codec/generator на valid/invalid inputs. |
| [tools/test_configgen.py](../tools/test_configgen.py) | Строгий parsing, schema validation, safety thresholds/scopes, MEASURED lifecycle и стабильность generator без документации. Защищает конфигурационный допуск. | CI; выполняет parser/schema/config generator на временных fixtures. |
| [tools/test_jcs.py](../tools/test_jcs.py) | RFC 8785 числовые/строковые правила, UTF-16 key order, malformed значения и golden vectors. Защищает единый канонизатор от несовместимых хэшей. | CI; проверяет реальную сериализацию общими RFC/golden cases. |
| [tools/test_ipc_contract.py](../tools/test_ipc_contract.py) | Sizes/offsets/types Python IPC, C++ generated definitions и общие golden vectors. Находит рассогласование между worker и controller. | CI; Python layouts сравниваются с vectors и C++ definitions. |
| [tools/test_build_identity.py](../tools/test_build_identity.py) | Identity inputs, component/profile separation, canonical hex, исключение docs/tests и влияние runtime/toolchain. Защищает идентификатор сборки от лишних и пропущенных входов. | CI; реальный identity/source hash изменяется на контролируемых inputs. |
| [tools/test_artifact_check.py](../tools/test_artifact_check.py) | Compiler facts, package naming, archive traversal/root members, executable modes и обязательные runtime inputs. Проверяет gate готового пакета. | CI; реальные функции package/compiler validation получают временные архивы. |
| [tools/test_apk_repro_diff.py](../tools/test_apk_repro_diff.py) | Отчёт о изменённых и переименованных одинаковых ZIP entries. Проверяет, что сравнение APK правильно объясняет отличие. | CI; сравнивает специально созданные ZIP, проверяет содержательный diff. |
| [tools/test_documentation.py](../tools/test_documentation.py) | Local numbering, legacy anchors, idempotent TOC, criterion/requirement traceability, schema/prose declarations и implementation-map links. Защищает средства проверки документации. | CI; выполняет функции TOC/links/traceability на корректных и повреждённых документах. |
| [tools/test_security_scan.py](../tools/test_security_scan.py) | Обнаружение разных форм секретов, узкие исключения, корректность allowlist и отсутствие секрета в findings. Проверяет реальную полезность secret scanner. | CI; detectors получают искусственные секреты и допустимые данные. |
| [tools/test_ev3_device_integration.py](../tools/test_ev3_device_integration.py) | Чистые функции integration runner: clock/boot-id/status validation и проверка zero/brake. Нужен для проверки runner на компьютере без аппаратного запуска. | CI; вызывает pure validation functions установленного runner без устройств. |
| [tools/quest_validation/test_analyze.py](../tools/quest_validation/test_analyze.py) | Quest analyzer на неполных/legacy и instrumented captures; timestamps, loss/recovery и QR. Не позволяет автоматически подтвердить результат без нужных данных. | CI; проверяет анализ synthetic captures и отсутствие ложного PASS. |
| [ev3/network/test_phantom_network.py](../ev3/network/test_phantom_network.py) | Существующий Python network worker: HELLO/session/retry, IPC, scope zero, telemetry, malformed/HMAC/replay/flood и restart. Сохраняет сетевую семантику до и при C++-переносе. | CI; вызывает действующий worker и проверяет sessions/IPC/flood/restart. |
| [sim/ev3-simulator/test_simulator.py](../sim/ev3-simulator/test_simulator.py) | Handshake, references, targets/watchdog, malformed packets и scenarios Stub EV3. Проверяет корректность тестовой подмены. | CI; проверяет сетевую подмену, от которой зависят client fault scenarios. |

## 4. Shell helpers на EV3

| Файл | Назначение | Потребитель / причина сохранения |
|---|---|---|
| [deploy/scripts/install-release](../deploy/scripts/install-release) | Проверка архива, atomic install runtime/config/units и прав. | ev3-install.ps1 на EV3; отмена незавершённой install transaction остаётся внутренней защитой. |
| [deploy/scripts/start-release](../deploy/scripts/start-release) | Запуск systemd-служб по зависимостям и startup отчёт. | ev3-start.ps1 на EV3. |
| [deploy/scripts/run-device-integration-test](../deploy/scripts/run-device-integration-test) | Проверка кандидата и вызов packaged integration runner. | ev3-device-integration-test.ps1 на EV3, без движения. |
| [provision/ev3/bootstrap](../provision/ev3/bootstrap) | Пользователи/группы, CONTROL key, maintenance helpers и Wi-Fi service. | ev3-provision-maintenance.ps1; однократная подготовка EV3. |
| [provision/ev3/install-deployment-key](../provision/ev3/install-deployment-key) | Доверенная начальная установка публичного deployment SSH key. | ev3-provision-maintenance.ps1, если deployment key ещё не принят. |
| [provision/ev3/wifi-autoconnect](../provision/ev3/wifi-autoconnect) | Bounded повтор подключения provisioned Favorite+AutoConnect Wi-Fi. | Установленная phantom-wifi-autoconnect.service; без вывода пароля. |
