# Текущее состояние реализации PHANTOM

## Текущее состояние

**Stage 3 не завершён.** Изменение 2026-10-12 разделяет настройки разработки,
постоянные данные робота и привязки запуска. Результаты прежних ARM/APK сборок
не подтверждают новый кандидат. Software checks проходят; DEVICE и физическая
квалификация для нового кандидата — `NOT_RUN`.

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
- Все 138 tooling self-tests проходят: генераторы, пакеты, JSON/JCS, процессные отказы,
  Unity XML, SSH fingerprint/config, сохранение credentials, cleanup и анализ.
- Семь C++ suites проходят в Diagnostic, Release и с ASan/UBSan.
- Quest host: 3 Unit-группы и 10 Functional cases, включая настоящий C#↔C++ UDP/IPC, проходят.
- Diagnostic EV3 ARM-пакет собирается и проверяется; две независимые сборки совпадают по байтам.
- На проверке 2026-10-10 Unity EditMode и APK BUILD завершались кодом 198:
  `No valid Unity Editor license found`. Повторный запуск 2026-10-11 прошёл успешно.
- Release packaging остаётся заблокирован без qualification evidence и подтверждённых
  platform/SBOM/risk inputs; это не аппаратный PASS.
- INSTALL, START, интеграционные тесты и получение данных реальных устройств — `NOT_RUN`.
  Проверки с подменёнными зависимостями не подтверждают работу на устройствах.

CLI-анализ EV3 пока только сводка journald по службам и severity; полнота физических
метрик не реализована. `check` также не подтверждает полный clang-tidy/C# analyzer coverage.
Workflow выполняет программные проверки для push/PR; результаты публикуются
в checks соответствующего pull request. Unity и аппаратные проверки в этот workflow не входят.

Ревизия конфигурации 2026-10-11: настройки централизованы в `config/ev3`,
`config/quest`, `config/shared` и `config/tooling`. У компонентов `project.json`
и соседние `diagnostic.json`/`release.json`; авторитетные данные приводов и допуска
находятся у EV3, геометрия — в shared. Неиспользуемые настройки удалены, будущие
Quest runtime-поля явно отмечены в спецификации. Второй реестр измеренных значений удалён.
Полные конфиги автоматически компонуются перед `build`/`test` в `build/config/`;
`check` валидирует источники без готовых файлов. `generate` оставлен для протокола и документации.
Протокольные хэши сохранены; runtime config hashes изменились после удаления неиспользуемых
полей. Прежние артефакты не подтверждают эти конфиги.
После ревью проходят `check`, 141 self-tests, семь C++ suites в Diagnostic/Release
и ASan/UBSan, 3 Unit и 10 Functional Quest host cases. Diagnostic ARM-пакет собран
и проверен. После повторного запуска Unity проходят все 32 EditMode-теста и Diagnostic APK BUILD,
включая проверку подписи и пакета. APK: `build/quest/PhantomQuest-diagnostic.apk`,
`build_id=7d8dcf2efa1ba7f57c00e81e79f253428a66fbe29d55a4dcfd1507ada665cd43`.
Регрессии проверяют единственный источник измерения, пропущенную калибровку, диапазоны,
неизвестные настройки, отсутствие записи при ошибке и повторную подготовку используемых файлов.
Анализ выполнен на синтетических данных, очистка проверена только в режиме preview.

## Разделение жизненного цикла конфигурации — 2026-10-12

- Из `project.json` и профилей удалены измерения, commissioning-заготовки,
  неподтверждённая идентичность образа устройства и флаг полноты измерений.
  Удалены shared файлы незаполненной геометрии/механической ревизии.
- В Git остаются настройки разработки и схемы постоянного CommissioningBundle,
  device identity, EV3 startup references, Quest localization и transient
  network-only descriptor. Реальные robot data находятся вне исходников.
- BUILD не формирует/не упаковывает калибровку; TEST создаёт только synthetic
  session fixture. Новый runtime config имеет `schema_version=2`.
- Diagnostic автоматически создаёт в памяти нулевой сетевой описатель; EV3/Quest
  вычисляют одинаковый ненулевой hash. Сохранённая физическая калибровка не
  используется и не меняется этим режимом. Старый config version отвергается.
- EV3 читает постоянные данные отдельно из `/var/lib/phantom/robot/commissioning.json`.
  Отсутствие файла не разрешает Release; повреждённые файлы и symlinks отвергаются.
  INSTALL пакета отвергает включённые robot data и не перезаписывает постоянный каталог.
- Production-процедуры создания полной калибровки, platform identity, QR startup
  references/localization и полного motion admission ещё не реализованы. Для них
  оставлены схемы и нормативные lifecycle contracts; наличие схем не означает PASS.
  Stage-3 loader не выдаёт motion admission по одному label `QUALIFIED`.
- Release software suites доступны независимо от robot data. Packaging/publication
  Release остаётся заблокированным до реализации проверки внешнего qualification
  evidence; удаление измерений из исходников не ослабляет этот gate.
- Выполнены ревью и регрессии отсутствия/повреждения данных, сохранения данных при
  ошибке, bootstrap identity, отделения BUILD от robot data и runtime version.
  Проходят 148 tooling self-tests, семь C++ suites в каждом из
  Diagnostic/Release/ASan+UBSan, четыре Quest host Unit-группы, десять Functional
  cases и все 32 Unity EditMode-теста. Wire/IPC identities сохранены; bootstrap/config hashes
  изменились, поэтому старые installed candidates не подтверждены.
- Финальный EV3 Diagnostic ARM BUILD и artifact gate проходят; пакет не содержит
  commissioning JSON. `build_id=6cba7a0962f8829e5bbceae290dee5a7be0105f06bae4b7bee2057bf6d9cd61e`.
  Новый Quest APK не собирался в этой задаче; прошлый APK не подтверждает новый
  runtime config. Проверки EV3/Quest на устройствах — `NOT_RUN`.

## Ревью и итоговые проверки перед merge — 2026-10-13

Проверен весь накопленный diff: lifecycle конфигов, схемы и генераторы,
bootstrap/admission EV3/Quest, Docker/build/artifact gates, host tooling,
документация и удаления старых placeholders. Исправлено смешение JSON boolean
и number в `const`/`enum` валидатора; регрессия проверяет также вложенные значения.
Изменённые текстовые файлы приведены к LF по `.gitattributes`, чтобы рабочие
байты совпадали с коммитом и CI checkout. Действующая сводка: 105 параметров.
Итоговые наблюдённые проверки: 159 tooling tests; EV3 Diagnostic, Release и
ASan/UBSan — по семь C++ suites; Quest host Unit (4), Functional (10),
Unity Editor (32); полный `check` и согласованная повторная генерация.
ARM Diagnostic BUILD/artifact gate проходит; две независимые сборки дают
одинаковые bytes и build identity:
`9449096f821a588c470a4f409077203cc344ae98c128982c8e4087c2a05b322a`.
DEVICE/физическая квалификация — `NOT_RUN`: после software merge требуется
проверка согласованного EV3/Quest кандидата на назначенных устройствах по
действующим P0 gates. Эти software checks не подтверждают движение приводов
или завершение Stage 3. Новый Quest APK в этой задаче не собирался.

## Python как требование среды — 2026-10-13

`python_minimum` удалён из tooling config. Базовая версия Python 3.12 задана
в корневом `.python-version`; CLI читает её для проверки интерпретатора,
оба CI jobs используют этот же файл в setup-python. Документация обновлена,
Markdown-сводка проверена: 105 параметров из шести исходных конфигов.
Проходят 158 tooling tests и полный `check`; Python 3.8.2 отклоняется с
сообщением о необходимости Python 3.12 или новее. Облачный CI не запускался;
production runtime configs и код устройств этой правкой не изменены.

## Семантика протокола без полей версии — 2026-10-13

`schema_version` и `protocol_version` удалены из `config/shared/protocol/semantics.json`.
Генератор валидирует единственный актуальный набор разделов; прежние проверки
версии документа удалены. Wire layout, fixed wire header version и IPC не изменены.
Производные артефакты пересозданы; новая semantic identity:
`9b76f7b3b921c2a6c3905ae7f7b0c645a1268d36f185e3615c3c434e8ea51e0d`,
новый protocol contract hash:
`4a9beffb2c52fd0c0c49d73c12d1acddf163522b648d9bf537b4bd3d81cc0524`.
Markdown-сводка проверена: 107 параметров из шести исходных конфигов.
Проходят 158 tooling tests, семь EV3 C++ suites, Quest host Unit (4),
Functional (10), ARM Diagnostic BUILD/artifact gate и полный `check`.
Новый EV3 build identity:
`dbede77dac524859166ba683b85a756778c1dd44b697f88d2f62c4383d930d1d`.
DEVICE — `NOT_RUN`; перед аппаратной проверкой нужен согласованный кандидат
EV3/Quest с новым contract hash. Новый Quest APK не собирался.

## Фиксированная идентичность единственного робота — 2026-10-13

`robot_id` удалён из Shared pair config и CLI `--robot-id`. Единственный
protocol ID `phantom01` задан как const в EV3 runtime schema; общий consumer
подставляет его в generated configs EV3/Quest и при создании локальной пары.
Wire layout и проверки HELLO/telemetry/discovery сохранены. Существующие
приватные pair records не перезаписываются этим изменением.
Markdown-сводка проверена: 109 параметров из шести исходных конфигов.
Проходят 158 tooling tests, семь EV3 C++ suites, Quest host Unit (4),
Functional (10) и полный `check`. DEVICE — `NOT_RUN`; настройка новой пары
ещё не проверена на назначенных EV3/Quest. ARM-сборка и Unity-тесты отдельно
не повторялись: содержимое runtime configs и production C++/C# не изменилось.

## Runtime-конфиги без версии и параметра остановки — 2026-10-13

`runtime.schema_version` удалён из исходных и generated runtime configs EV3/Quest,
их схем, загрузчиков и проверок. Используется единственная актуальная runtime
schema каждого компонента, без version suffix в `$id`; структура по-прежнему
валидируется, а deployment проверяет config hashes. Версии manifest/session/
данных робота этой правкой не затронуты.
`runtime.safety.motor_output_default` удалён: он только допускал строку BRAKE_ZERO,
не выбирая выход приводов. Нулевой выход/торможение controller/backend сохранены.
Markdown-сводка проверена: 110 параметров из шести конфигов.
Проходят 158 tooling tests, семь EV3 C++ suites, Quest host Unit (4),
Functional (10), Unity Editor tests, ARM Diagnostic BUILD/artifact gate и полный `check`.
Новый EV3 build identity:
`920263f35982ee15723449eacad49f4b8f38731268b4c65a060fb79372830fc1`.
DEVICE — `NOT_RUN`; аппаратная проверка требует установки и проверки этого
кандидата на назначенном EV3. Новый Quest APK не собирался.

## Сводка конфигов и host-настройки — 2026-10-13

`ev3-constants-inventory.csv` удалён. Markdown-сводка охватывает все шесть
JSON-файлов в `config/`: 113 листовых параметров, включая массивы и null,
текущие значения, назначение, применение и потребителей. Отдельно проверены
полнота, отсутствие повторов/лишних строк, SHA-256 и ссылки на потребителей.
Host-таймауты ADB/SSH, передачи/установки, bootstrap и запуска Quest, SSH
connection/keyscan и интервалы ожидания вынесены в tooling settings.
Override-переменная apksigner теперь принадлежит Quest Android environment.
Прежние значения по умолчанию сохранены; валидация отклоняет недопустимые пределы,
регрессии подтверждают применение настроек и явных переопределений таймаута.
Проходят 158 tooling tests, семь EV3 C++ suites, Quest host Unit (4),
Functional (10), ARM Diagnostic BUILD/artifact gate и полный `check`.
EV3 build identity сохраняется: `d5d67ed3e60b0059f4ad50e7db4593dc9e08e634df8f3bf32f02e22f15639a97`.
Проверки на устройствах — `NOT_RUN`;
изменённые host-параметры ещё не проверены на назначенных EV3/Quest.
Разделение Diagnostic/Release и режима допуска к движению остаётся отдельной
обсуждённой, но не реализованной задачей.

## Перенос схем в отдельный каталог

Все девять машинных схем перенесены из `config/` в `schemas/` с сохранением
подкаталогов `ev3`, `quest`, `shared/protocol`. Семантика протокола остаётся
в `config/shared/protocol/semantics.json`. Пути обновлены в потребителях,
генераторах, тестах и документации; generated artifacts пересозданы генератором.
Содержимое схем, wire/IPC/semantic identities и runtime configs не изменились.
EV3 source hash учитывает новый путь wire/IPC sources; build identity изменилась:
`d5d67ed3e60b0059f4ad50e7db4593dc9e08e634df8f3bf32f02e22f15639a97`.
Проходят 154 tooling tests, семь EV3 C++ suites, Quest host Unit (4) и
Functional (10), ARM Diagnostic BUILD/artifact gate и полный `check`.
DEVICE для новой identity — `NOT_RUN`; нужен запуск проверок точного кандидата
на назначенном EV3. Новый Quest APK не собирался.

## Вычисляемые поля профиля — 2026-10-12

Исходные EV3 `qualification_only`/`actuator_scope_mask`/`safety_observation_mask`
и Quest `required_user_inputs` перенесены в компоновщик. Для текущего Diagnostic
получается network-only контракт, для Release — полный product контракт.
Пустые `config/ev3/{release,diagnostic}.json` и
`config/quest/{release,diagnostic}.json` удалены. Настраиваемые отличия при
необходимости могут задаваться необязательными profiles; derived fields
переопределять нельзя. Флаг и маски в данных робота сохранены.
Все четыре generated runtime configs совпадают с предыдущим кандидатом;
EV3 build identity сохраняется:
`aa74422d4821ec735c76c92e871be806fce7b9f43da5e72173428a080bc87dc8`.
Проходят 154 tooling tests, семь EV3 C++ suites, Quest host Unit (4) и
Functional (10), ARM Diagnostic BUILD/artifact gate и полный `check`.
Markdown/CSV проверены: один исходный EV3 config, 21 параметр.
Новый Quest APK не собирался; DEVICE — `NOT_RUN`. Аппаратные Diagnostic phases
остаются будущей работой и не включаются выбором профиля.

## Удаление декларативного ready_gate — 2026-10-12

`runtime.safety.ready_gate` удалён из обоих EV3 profiles, runtime schema и
загрузчика: строка проверялась на наличие, но не участвовала в допуске.
Проверки profile/bundle, qualification, масок и физических данных сохранены.
Markdown/CSV содержат 27 исходных параметров без пропусков и лишних записей.
Проходят 153 tooling tests, семь C++ suites Diagnostic, ARM Diagnostic BUILD
и artifact gate. Новый
`build_id=aa74422d4821ec735c76c92e871be806fce7b9f43da5e72173428a080bc87dc8`.
DEVICE — `NOT_RUN`; аппаратная проверка требует установки этого кандидата
на назначенный EV3. Упоминания ready_gate ниже относятся к предыдущим кандидатам.

## Проверки компилятора в Dockerfile — 2026-10-12

Ожидаемые версия и SHA-256 компилятора перенесены в `ev3/docker/Dockerfile`.
Проверки выполняются после установки зависимостей; несовпадение прерывает
создание образа. Секция `build` удалена из EV3 `project.json`; конфиг содержит
только runtime-настройки. CLI больше не читает compiler lock из JSON:
toolchain identity включает SHA-256 рецепта и immutable prepared image ID,
фактические compiler facts продолжают сохраняться в манифесте сборки.
Сводка Markdown/CSV проверена: 29 параметров без пропусков и лишних записей.
Проходят 153 tooling tests, семь C++ suites Diagnostic, ARM Diagnostic BUILD
и artifact gate. Docker build отклоняет отдельно неверную версию и неверный
хеш компилятора. Новый
`build_id=ff12858d568416b77b83f3648efd3010103c9425d8dd7bbb75a3301277ffdd9d`.
DEVICE для новой identity — `NOT_RUN`; следующая аппаратная проверка требует
установки и проверки именно этого кандидата на назначенном EV3.
Ниже сохранены результаты предыдущих изменений; описание compiler lock в JSON
и прежние количества параметров относятся к предыдущим кандидатам.

## Docker-среда ARM-сборки — 2026-10-12

Базовый image/digest и версии ARM-пакетов разработки OpenSSL 1.0.2/Avahi перенесены
в `ev3/docker/Dockerfile`; секция `build.environment` удалена из EV3 project config.
CLI и CI автоматически подготавливают образ; сборка использует immutable image ID.
Рецепт, image ID и compiler facts учитываются в build identity и artifact gate.
`doctor` не создаёт образ. Пакеты установлены как `armel`; компиляция официальных
заголовков даёт ARM ELF. Проходят 153 tooling tests, ARM Diagnostic BUILD и
artifact gate; семь C++ suites Diagnostic проходят. Проверена актуальность таблицы
из 32 параметров. Новый `build_id=2f20754a0972a1c3f7c25015ae2d3143887fb7bff1d39364ea8789dd72fc6842`.
На EV3 библиотеки по-прежнему требуют отдельного provisioning;
DEVICE для новой build identity — `NOT_RUN`.

## Ревью параметров EV3 — 2026-10-12

Удалён `build.toolchain.target`: он задавал только label и сверялся с собственной
копией. Манифест теперь содержит observed `compiler_target` от `-dumpmachine`,
экспортированный выбранным компилятором через CMake. Архитектура/ABI по-прежнему
проверяются по ELF; compiler version/SHA-256 сравниваются с ожидаемым lock.
Проверены остальные исходные параметры EV3. Кандидаты на дальнейшее упрощение:
декларативный `ready_gate`, фиксированный `motor_output_default`, фиксированная
разводка портов; heartbeat/recorder rates частично дублируют фиксированный 50-Hz
цикл, но участвуют в валидации/ёмкости. Их автоматическое удаление не выполнено:
нужно согласованное изменение owner/schema/consumers. Результаты отражены в
таблице параметров; реестр содержит 31 запись из трёх конфигов.
Проходят 155 tooling tests и семь C++ suites Diagnostic. Новая ARM-сборка и
artifact gate проходят: `compiler_target=arm-linux-gnueabi`,
`build_id=e597632b3da8eb6506d8e899e2ee00326a0c26734718f1d020912a6ee5cbbe97`.
DEVICE для новой identity — `NOT_RUN`.

## Незакрытые проверки

| Область | Состояние и следующий шаг |
|---|---|
| Механическая модель | BOM и LDraw фиксируют структуру, но модель остаётся DESIGN PLACEHOLDER / UNQUALIFIED. Нет подтверждённых измерений соосности, противовеса, упоров, QR mounts и поведения при потере питания; READY остаётся заблокирован до квалификации |
| Полнота программных тестов EV3 и Quest | Не подтверждена: сопоставить реализованную функциональность обеих платформ с автоматическими тестами production-кода по [План проверки §3](test-plan.md#sec-9-1-2), устранить пробелы и выполнить применимый software regression до DEVICE/MANUAL qualification |
| Host lifecycle tests | [PHANTOM CLI](tooling.md) проверяет pair state, process helpers и сбор логов Quest с fake SSH/ADB и дочерними процессами, включая отказы. Полнота остальных lifecycle/install behaviors с подменёнными зависимостями не подтверждена; поиск строк в исходниках не заменяет такие тесты |
| Stub Quest3 / tracking replay | C# TrackingReplaySource существует; JSONL loading и подача записей в production algorithms с unit/functional проверками не подтверждены. Прежний Python-счётчик записей удалён |
| Stage 3 | Запустить свежую Diagnostic пару и выполнить применимые network/session/reconnect/reboot cases; критерии — [Этапы реализации §5](implementation-stages.md#sec-10-5) |
| DEVICE, manual acceptance | `NOT_RUN` для новой identity; опубликовать exact reports с URI/SHA-256 |
| Интеграционные Quest/EV3/пара | Покрытие полного списка не подтверждено; сопоставить runners с [планом](test-plan.md#sec-9-1-3), реализовать недостающие cases и проверить пару без движения |
| Quest без надетого шлема | Полный прогон не подтверждён: OnApplicationPause останавливает сетевой клиент, KEYCODE_WAKEUP не доказывает непрерывное выполнение. Проверить awake/headless prerequisites и корректный NOT_RUN при suspend |
| Автоматический анализ метрик | Полнота не подтверждена: проверить сбор валидных samples, сообщения о превышениях и статус не измерено без данных/эталона по [метрикам](metrics-and-logs.md#sec-test-plan-manual-criteria). Пользовательские формы приёмки не требуются |
| Quest credential persistence | `NOT_RUN`: проверить сохранение credential между двумя APK после lifecycle migration |
| Full-arm Body provider | Exact platform matrix не квалифицирована; выполнить [P0](metrics-and-logs.md#sec-9-6) для применимого scope. Историческая несовместимость описана в [источниках](references.md#sec-11-5-1) |
| EV3 release inputs | Product Release PASS не подтверждён: нужны внешние exact brick image identity, SBOM, risk/qualification evidence и их реализованный gate; в исходниках остаётся только закреплённый build toolchain. См. [Разработка и развёртывание §4](engineering.md#sec-8-5) |
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
