# PHANTOM CLI — единый инструмент разработки

<!-- BEGIN GENERATED TOC -->
<details>
<summary>Оглавление</summary>

- [1. Назначение и границы](#sec-tooling-purpose)
- [2. Окружение](#sec-tooling-environment)
- [3. Команды](#sec-tooling-commands)
- [4. Проверки и генерация](#sec-tooling-checks)
- [5. Тесты продукта](#sec-tooling-test)
- [6. Сборка](#sec-tooling-build)
- [7. Установка и назначенная пара](#sec-tooling-install)
- [8. Запуск и интеграционные тесты](#sec-tooling-device)
- [9. Диагностика и очистка](#sec-tooling-diagnostics)
- [10. Реализация и самотестирование](#sec-tooling-implementation)
- [11. Технические контракты](#sec-tooling-contracts)
  - [11.1. Идентификаторы сборок](#sec-engineering-contracts-build-identity)
  - [11.2. Проверка и воспроизводимость пакетов](#sec-engineering-contracts-package-validation)
  - [11.3. Пакет EV3](#sec-engineering-contracts-ev3-package)
  - [11.4. Пакет Quest](#sec-engineering-contracts-quest-package)
  - [11.5. Хранение и импорт ключей](#sec-engineering-contracts-credentials)
    - [11.5.1. Импорт ключа на Quest](#sec-engineering-contracts-quest-credentials)
  - [11.6. Установка EV3 и права служб](#sec-engineering-contracts-ev3-install)
  - [11.7. Настройка и защита сети EV3](#sec-engineering-contracts-network)

</details>
<!-- END GENERATED TOC -->

<a id="sec-tooling-purpose"></a>
## 1. Назначение и границы

Единственная точка входа — `python tooling <command>`. Команда работает из исходного checkout;
путь к репозиторию определяется по расположению инструмента. Собственный host-код написан
на Python; CMake, Docker, Unity, .NET, ADB и OpenSSH вызываются как внешние программы.
Python не устанавливается на EV3: проверки и обработка JSON там выполняют C++ binaries.
Systemd units и короткие POSIX обёртки системных операций являются устанавливаемыми ресурсами.
Тесты продукта остаются в `ev3/tests` и `PhantomQuest`, на C++ и C#.
Исходные настройки хранятся в `config/`, схемы форматов — в `schemas/`.
Компоновщик и генератор протокола читают схемы из единственного нового расположения.

<a id="sec-tooling-environment"></a>
## 2. Окружение

На компьютере нужен Python базовой версии из [`.python-version`](../.python-version)
или новее; сейчас это 3.12. Этот файл задаёт среду разработки: CLI проверяет по нему
интерпретатор, а CI использует его для установки Python. Зависимости CLI — стандартная библиотека.
Таймауты команд задаются в `config/tooling/settings.json`,
окружение WSL — в `config/tooling/environment.json`. Поиск Unity, Android SDK и .NET
принадлежит `config/quest/project.json`; ARM-среда и проверки ожидаемого компилятора — `ev3/docker/Dockerfile`.
Имя override-переменной `apksigner` задаётся в Quest Android environment.
Host-таймауты ADB/SSH, передачи пакетов, bootstrap и запуска Quest, SSH
connection/keyscan и интервалы опроса/наблюдения Quest принадлежат
`config/tooling/settings.json`. Значения проверяются до выполнения команд;
сетевой таймаут keyscan должен быть меньше таймаута его процесса. Изменение
SSH ConnectTimeout меняет локальный SSH config и для существующей пары требует
явного `--repair` по правилам защиты pair state.
Meta App ID и alias подписи заданы в `config/quest/project.json`; Android package ID
читается непосредственно из штатного Unity ProjectSettings.
Структура настроек и сборка профилей описаны в [engineering §8.1](engineering.md#sec-engineering-contracts-configuration).
Имя `python` в примерах должно указывать на этот интерпретатор. Если системная версия
старее, вместо `python` укажите полный путь к подходящему `python.exe`.
Настройки поиска инструментов находятся в `config/tooling/environment.json`; версии Unity и .NET
читаются из конфигураций проектов, ARM image — из `ev3/docker/Dockerfile`.
Команда `doctor` показывает найденные зависимости и завершается ошибкой при их отсутствии.
CLI не заменяет закреплённые версии и не активирует лицензию Unity.
ARM BUILD явно подготавливает среду по `ev3/docker/Dockerfile`; Docker при
необходимости получает закреплённую базу и архивные dev-пакеты. `doctor` только
проверяет наличие подготовленного образа и не выполняет Docker build.

Параметры текущего режима (`qualification_only`, обе scope masks и Quest
`required_user_inputs`) компоновщик выводит из `--profile`; они не задаются
в `project.json`. Пустых профильных JSON-файлов нет. Полученные runtime configs
сохраняют эти поля для проверки согласованности и допуска на устройстве.

Хэш toolchain EV3 вычисляется из канонического объединения SHA-256
`ev3/docker/Dockerfile` и фактического prepared image ID. Версия и SHA-256
компилятора проверяются самим Dockerfile после установки зависимостей;
фактические compiler facts сохраняются в манифесте сборки. EV3 `project.json`
содержит только runtime-настройки и не входит в toolchain hash.

<a id="sec-tooling-commands"></a>
## 3. Команды

| Команда | Результат | Где работает |
|---|---|---|
| `check` | Синтаксис host-кода, схемы, документация, секреты и компиляция Android bridge; `--target` выбирает область | Компьютер / CI |
| `generate` | Обновление производных протокола или оглавлений; `--target all/protocol/docs` | Компьютер / CI |
| `docs` | Поиск раздела: `--document docs/<file>.md --locate <section>` | Компьютер |
| `doctor` | Проверка доступности инструментов | Компьютер |
| `self-test` | Регрессии самого CLI, генераторов и анализаторов; устройства подменены | Компьютер / CI |
| `test` | Сборка и выполнение тестов продукта; `--target ev3/quest` | Компьютер; C++ в WSL на Windows |
| `build` | ARM-пакет EV3 или APK Quest; тесты продукта отдельно | Компьютер; Docker / Unity |
| `install` | Настройка назначенного устройства, передача и установка `--artifact` | Компьютер → устройство |
| `start` | Запуск установленной системы; `--build-id` сверяет кандидата | Компьютер → устройство |
| `integration-test` | Проверки установленной системы: Quest на столе, EV3 без движения | Компьютер → устройство |
| `logs` | Сбор данных выбранного устройства и анализ; `--skip-analysis` отключает анализ | Компьютер → устройство |
| `analyze` | Повторный анализ `--input` в `--output`, без устройств | Компьютер |
| `clean` | Предпросмотр рабочих данных; `--apply` удаляет выбранное | Компьютер |

У каждой команды есть `--help`. Ошибка завершает команду ненулевым кодом; зависимые
действия прекращаются. `--timeout` ограничивает операции с процессами/устройствами.
Установка не запускает систему или тесты. Команды полного конвейера пока нет.

<a id="sec-tooling-checks"></a>
## 4. Проверки и генерация

`python tooling check` запускается до сборки. `--target docs/schemas/security/android`
выбирает проверку. `generate` изменяет только производные файлы; `check` их не исправляет.
Оглавления обновляются через `python tooling generate --target docs`.
`generate --target protocol` также создаёт C++/C# bindings нулевого session
описателя из `schemas/ev3/network-only-session.schema.json`. Этот формат имеет
собственный hash и не меняет wire/IPC layout или protocol contract hash.
Конфигурации проверяются в памяти через `check --target schemas`. Полные файлы
создаются автоматически командами `build` и `test` в `build/config/`, без отдельного
вызова генератора. В `config/` хранятся настройки разработки и семантика протокола,
в `schemas/` — машинные схемы. Постоянные измерения
робота и привязки запуска не создаются BUILD и не входят в пакет. TEST отдельно
создаёт синтетический сетевой описатель в `build/config/test-fixtures/`.
Установка ПО сохраняет `/var/lib/phantom/robot/`; схемы и жизненные циклы —
[engineering §8.1](engineering.md#sec-engineering-contracts-configuration).

<a id="sec-tooling-test"></a>
## 5. Тесты продукта

`test --target ev3` собирает C++ тестовые targets и запускает CTest. `--filter` выбирает
suites; `--sanitize` включает ASan/UBSan. На Windows используется назначенный WSL distro;
промежуточные файлы создаются в `/tmp/phantom-tooling`, без записи через WSL в checkout.

`test --target quest` запускает NUnit Unit, Functional и Unity EditMode с Android target.
`--suite all/host/unity` выбирает среду, `--category all/unit/functional` — host-набор,
`--filter` — Unity-фильтр. Старый Unity XML удаляется перед запуском; отсутствие свежего
успешного непустого отчёта означает отказ. Fixtures сами создают моки и дочерние процессы.

<a id="sec-tooling-build"></a>
## 6. Сборка

`build --target ev3/quest --profile diagnostic/release` создаёт устанавливаемый артефакт.
Diagnostic — диагностические поверхности и подробные записи по правилам метрик;
Release — штатные журналы без DEBUG. Ядро управления и безопасность общие.
До объявления успеха проверяются manifest, хэши, состав пакета и ABI/подпись.
`--verify-reproducibility` выполняет две сборки: ARM должен совпасть по байтам,
разница APK сохраняется как требующая исследования. Release блокируется без применимой qualification.
Сборка Quest требует лицензированного Unity и приватного каталога `--signing-directory`.
`--output` задаёт APK или каталог ARM-сборки внутри `build/`.

<a id="sec-tooling-install"></a>
## 7. Установка и назначенная пара

`install --target ev3/quest --artifact <file>` включает настройку. Первое назначение пары
требует доверенного `--host-fingerprint`; `--quest-serial` задаётся явно либо выбирается
единственный авторизованный Quest 3. Обычные обновления сохраняют identities и credentials.
Данные пары хранятся вне checkout по умолчанию; `--state-root` задаёт другой приватный каталог,
кроме disposable `build/`, `results/`, `.git/`. Пароли и ключи не входят в сборку или отчёты.

Первый Quest APK должен быть Diagnostic: после успешной установки и сверки хэша CLI
передаёт credential для импорта приложением при следующем запуске. Обычное обновление
не передаёт его повторно. `--repair` восстанавливает staging существующего ключа.

EV3 настраивается через pinned SSH. Для первого root deployment key используется
доверенный `--bootstrap-user`; runtime должен быть безопасно остановлен до настройки.
Опции `--wifi-settings`/`--wifi-service` устанавливают профиль ConnMan. Замена настроек,
ротация `--rotate-ssh-key`/`--rotate-control-secret` и `--repin-host` требуют явного `--repair`.
Установщик проверяет пакет, права и конфигурацию; службы остаются остановлены.

<a id="sec-tooling-device"></a>
## 8. Запуск и интеграционные тесты

`start --target ev3 --build-id <id>` запускает службы; Quest сверяет startup report и
готовность credential. `--capture-debug` сохраняет дополнительные данные запуска.
`integration-test --target ev3/quest --build-id <id>` проверяет точную установленную версию.
Quest неподвижен, не надет; EV3 допускает только network-only Diagnostic с нулевыми масками.
Аппаратный PASS получается только после фактического выполнения на назначенном устройстве.
`integration-test --target quest --apk-a <A> --apk-b <B>` вместо `--build-id` проверяет
сохранение credential после обновления; A — Diagnostic, версии различаются.

<a id="sec-tooling-diagnostics"></a>
## 9. Диагностика и очистка

`logs --target ev3/quest` получает данные и вызывает анализ. EV3 — ограниченный journald
штатных служб (`--lines`), Quest — JSONL captures приложения. `analyze --target ev3/quest
--input <directory> --output <directory>` работает над сохранёнными данными. EV3-сводка
считает записи и severity; физические метрики не подтверждает. Состав данных и правила
отчётов принадлежат [метрикам и журналам](metrics-and-logs.md).

`clean --target build/results` показывает список. `--apply` разрешает удаление;
`--all` выбирает все outputs сборки, обычная очистка сохраняет `--keep` свежих пакетов.
Секреты и назначения пары не входят в область очистки.

<a id="sec-tooling-implementation"></a>
## 10. Реализация и самотестирование

| Каталог | Содержание |
|---|---|
| `tooling/__main__.py`, `cli.py` | Единственный публичный запуск и параметры |
| `tooling/commands/` | Проверки, продуктовые tests/builds, операции устройств, logs/cleanup |
| `tooling/common/` | Процессы, paths, environment, SSH/ADB и приватное назначение пары |
| `tooling/internal/` | Генераторы, канонические проверки, identity, упаковка и анализ Quest |
| `tooling/resources/ev3/` | Units, tmpfiles и внутренние системные обёртки установки/запуска |
| `tooling/tests/` | Unit/functional регрессии инструмента без оборудования |
| `ev3/src/maintenance_*`, `device_integration*` | Нативные поставляемые C++ помощники EV3 |

`self-test` проверяет парсинг команд, отказы процессов, timeouts, paths, staging,
сохранение credentials, генерацию и отрицательные случаи. Тесты продукта в этот набор
не входят. Регрессии нативных помощников находятся в `ev3/tests`.

<a id="sec-tooling-contracts"></a>
## 11. Технические контракты

<a id="sec-engineering-contracts-build-identity"></a>
### 11.1. Идентификаторы сборок

`build_id` отличает компонент, режим и входные данные сборки.
Документация не является входом сборки и не влияет на этот идентификатор.
`source_tree_hash` исключает Markdown, reStructuredText, AsciiDoc, `docs/`,
сгенерированный `docs/protocol-wire-reference.md`, кэши интерпретатора, результаты и готовые пакеты.
Входы EV3 объявлены в `EV3_SOURCE_INPUTS` в [source_hash.py](../tooling/internal/source_hash.py):
штатные C++-исходники и заголовки, протокол, deployment
и общий ARM toolchain. Тестовые исходники исключены; builder и проверка пакета
используют один список через `--component EV3`.

`build_id` — SHA-256, передаваемый как 32 байта; в тексте используется 64 символа
lowercase hex. До упаковки он вычисляется из UTF-8 представления следующего
объекта, канонизированного по RFC 8785 JCS:

```json
{
  "schema": "PHANTOM-BUILD-V4",
  "component_id": "<EV3|QUEST>",
  "build_profile": "<Release|Diagnostic>",
  "source_tree_hash": "<64-hex>",
  "protocol_contract_hash": "<64-hex>",
  "component_config_hash": "<64-hex>",
  "toolchain_or_package_lock_hash": "<64-hex>"
}
```

```text
build_id = SHA-256(JCS_UTF8(build_identity_object))
```

Объект содержит только указанные поля. Склейка строк или зависимость от порядка
словаря для вычисления хэша запрещены. Расчёт выполняет единый инструмент сборки
на компьютере и проверяется эталонными тестами; runtime C++/C# передаёт и проверяет
готовый идентификатор, не реализуя свой алгоритм JCS.

- `source_tree_hash` учитывает точные байты входных исходников, независимо от состояния Git.
- `component_config_hash` вычисляется до добавления идентификаторов и сведений о сборке.
- `git_commit`, `worktree_dirty`, время сборки и подпись описывают происхождение пакета,
  но не входят в `build_id`.
- Хэш готового APK/архива и манифест с самим `build_id` исключены из входов, чтобы не
  создавать циклическую зависимость.
- Результаты проверки связывают Quest и EV3 по протоколу, конфигурации и хэшам пакетов;
  равенство `quest_build_id == ev3_build_id` или общий commit не требуется.

<a id="sec-engineering-contracts-package-validation"></a>
### 11.2. Проверка и воспроизводимость пакетов

Сборка проверяет выбранную платформу, режим, состав файлов, встроенную конфигурацию,
идентификаторы и манифест. Для APK проверяются структура и подпись; для EV3 —
полнота файлов, `SHA256SUMS`, права и безопасность путей архива.
Результат записывается рядом с пакетом. При установке проверяются сами файлы,
а не наличие прежнего отчёта.

Манифест связывает хэши исходников, конфигурации и протокола, `build_id` компонентов,
хэши APK/EV3-пакета, версии инструментов/SDK/runtime и ревизию механики.
Проверка уязвимостей выполняется по [правилам зависимостей](engineering.md#sec-engineering-dependency-checks).

Две независимые сборки сравниваются по двум признакам:

| Поле отчёта | Что означает |
|---|---|
| `build_identity_stable` | Совпадает `build_id` |
| `artifact_byte_reproducible` | Совпадают байты и SHA-256 готового пакета |
| `difference_class` | Причина обнаруженного отличия |

Для EV3 требуются оба признака. Отличие APK требует разбора конкретной разницы,
созданной инструментами сборки. Смена commit при неизменных входных байтах не меняет `build_id`.

Release выбирается после проверки отладочной версии. После установки Release выполняются
запуск и интеграционные тесты именно этого пакета. Если менялись алгоритмы, конфигурация,
SDK или временные характеристики из-за логирования, повторяются затронутые программные
и ручные тесты. Результат одного пакета не подтверждает другой.
Логика безопасности и измеренные коэффициенты сохраняются в обоих режимах.

Для окончательной приёмки подтверждаются применимые требования и критерии
[матрицы](metrics-and-logs.md#sec-9-25); ни один критерий конечного продукта целиком
не помечается N_A. До приёмки движения разрешены только в области текущего этапа
по [этапам реализации](implementation-stages.md) и [безопасности](safety.md).

<a id="sec-engineering-contracts-ev3-package"></a>
### 11.3. Пакет EV3

Кросс-сборка использует среду из `ev3/docker/Dockerfile`. Единственный `FROM`
задаёт базовый образ по digest, ARM dev-пакеты имеют закреплённые версии.
CLI сначала выполняет Docker build с context `ev3/docker/`, затем запускает
полученный immutable image ID. Тег используется только для cache/поиска;
изменяемые Docker-теги не являются входом BUILD/CI/Release.
Платформа — `ARMv5TEJ / armel / gnueabi`; обязательные флаги:
`-march=armv5te -mfloat-abi=soft`. База и dev-зависимости берутся из [Dockerfile](../ev3/docker/Dockerfile); версия и SHA-256 компилятора — из
[toolchain lock](../config/ev3/project.json); требования CMake — из
[проекта EV3](../ev3/CMakeLists.txt).

Для релиза также фиксируются образ, установленный на EV3, его SHA-256, снимок пакетов,
SBOM и результаты проверки уязвимостей. Значения `UNRESOLVED`/`PENDING` разрешают
разработку и интеграционные тесты, но не подтверждают готовность релиза.

Все устанавливаемые unit-файлы проходят `systemd-analyze verify` на baseline systemd 232.
Директивы `StateDirectory=`, `LogsDirectory=` и `RuntimeDirectoryPreserve=` требуют
совместимого fallback. Установленные проверки и обработка JSON выполняются нативными C++ помощниками; Python на EV3 не требуется.
Release компилируется с `-O2` либо эквивалентной квалифицированной оптимизацией.

Fingerprint установленной платформы включает image SHA-256, kernel, machine/ABI,
systemd и используемые runtime dependencies; он сохраняется вместе с SBOM и
vulnerability/risk record. Legacy/EOL baseline допускается только в доверенной
изолированной LAN без Internet exposure.

Артефакт включает:

```text
phantom-controller
phantom-safety
phantom-network / phantom-mdns (C++14)
phantom-maintenance / phantom-device-integration-test
config.generated.json
build-manifest.json
SHA256SUMS
systemd units
tmpfiles.d policy
```

`SHA256SUMS` перечисляет все файлы пакета, кроме себя: относительные POSIX-пути,
ASCII, окончания строк LF. Неполный список, дубликаты, абсолютные пути, `..`, CRLF
или несовпадающий хэш вызывают отказ.
Controller, safety, сетевые entrypoints и тестовый runner сохраняют право исполнения;
файлы данных не становятся исполняемыми.

`build-manifest.json` хранит детерминированные сведения о сборке EV3. Он не содержит
хэш итогового архива или текущее время сборки:

```text
component: EV3
build_identity_schema: PHANTOM-BUILD-V4
build_id
git_commit
source_tree_hash / worktree_dirty
build_profile
protocol_version
compiler/toolchain
compiler_target: observed compiler -dumpmachine output
cross_image: immutable prepared image ID
cross_image_base: digest-pinned FROM
cross_image_recipe_sha256
protocol_schema_hash
protocol_semantics_hash
protocol_contract_hash
config_hash
drive_calibration_schema_version
source_date_epoch_or_reproducible_epoch
```

После упаковки создаётся внешний неизменяемый отчёт с `build_id`, `artifact_sha256`,
`created_at`, сведениями о подписи и хэшем встроенного манифеста. Он не добавляется
обратно в архив. Время создания описывает происхождение, но не меняет идентичность сборки.

Сборка отладочного пакета на Windows:

```powershell
python tooling build --target ev3 --profile diagnostic
```

Команда компилирует ARM-код, упаковывает его и проверяет готовый пакет.
Тесты запускаются отдельно. Незакоммиченные изменения разрешены;
`git_commit` и `worktree_dirty` записываются честно, но не определяют разрешение установки.
Упаковщик нормализует владельцев, порядок файлов, mtime и заголовок gzip.
Пакеты разных режимов имеют разные `build_id`.
Воспроизводимость проверяется по [§5.3](engineering.md#sec-engineering-build-validation).

<a id="sec-engineering-contracts-quest-package"></a>
### 11.4. Пакет Quest

Каждый APK встраивает **детерминированную build identity**, которая не содержит hash самого APK:

```yaml
build:
  component: QUEST
  build_id: ...
  app_version: 1.x.y
  git_commit: ...
  source_tree_hash: ...
  worktree_dirty: false
  build_profile: Release|Diagnostic
  protocol_version: 1
  protocol_schema_hash: ...
  protocol_semantics_hash: ...
  protocol_contract_hash: ...
  unity_version: ...
  package_lock_sha256: ...
  meta_xr_core_version: ...
  movement_sdk_version: ...
  body_tracking_provider: ...
  mruk_version: ...
  openxr_plugin_version: ...
  meta_openxr_version: ...
  xr_hands_version: ...
  quest_config_hash: ...
  target_sdk: ...
  local_network_permission_mode: ...
```

После подписи APK внешний `*.build-manifest.json` записывает `apk_sha256`, отпечаток
сертификата, key id без секрета, `created_at` и хэш встроенных сведений о сборке.
Этот файл не встраивается обратно в APK.

Сборка выполняется Unity Editor версии из
[ProjectVersion.txt](../PhantomQuest/ProjectSettings/ProjectVersion.txt) в batch mode,
методом `Phantom.Editor.PhantomBuild.BuildAndroid`.
Путь к keystore, пароль, alias и Meta App ID передаются через локальные файлы или
переменные окружения вне Git. Результат выбранного режима находится в `build/quest/`
рядом с `*.build-manifest.json` и `*.build-result.json`.
Отладочная и релизная версии подписываются разрешённым ключом.

Перед `BuildPipeline.BuildPlayer` в APK временно добавляются сведения о сборке без
хэша APK/времени и `quest.generated.json`. Приложение использует их для сообщения
`build_id` и проверки хэша конфигурации. После сборки временные Resources удаляются,
параметры подписи и разработки восстанавливаются без изменений отслеживаемых файлов.
Gradle daemon останавливается после каждой сборки, чтобы не удерживать файлы на Windows.

Обновление Unity/OpenXR/Meta требует повторных платформенных и интеграционных тестов.
В APK проверяются разрешения:

Для текущей pinned Meta XR matrix BUILD обязан проверить в APK как минимум:

```text
android.permission.INTERNET
# platform-conditional LAN access: target API 37+ -> android.permission.ACCESS_LOCAL_NETWORK;
# Android 16 restriction-opt-in/testing -> android.permission.NEARBY_WIFI_DEVICES where required
com.oculus.permission.HAND_TRACKING
com.oculus.permission.BODY_TRACKING
com.oculus.permission.USE_SCENE
com.oculus.permission.USE_ANCHOR_API
```

Разрешения LAN выбираются по `targetSdk` и API платформы; интеграционные тесты
проверяют их на установленном приложении. Для target API 37+ используется
`ACCESS_LOCAL_NETWORK`, поскольку PHANTOM сам обнаруживает фиксированный `robot_id`
и открывает UDP. Доступ NSD через системный выбор службы требует отдельного пересмотра UX/безопасности.
Для прежних сочетаний API проверяется необходимость foreground multicast lock;
он освобождается по lifecycle. Отказ или отзыв разрешения не заменяется жёстко заданным IP.

Манифест сборки фиксирует Unity и пакеты. Версия Horizon OS определяется только на
Quest и записывается в отчёт платформенной проверки вместе с `build_id` и `apk_sha256`.
Оба документа связывают пакет с реально проверенной платформой.

<a id="sec-engineering-contracts-credentials"></a>
### 11.5. Хранение и импорт ключей

Первичная настройка связывает назначенные Quest и EV3, сетевой доступ и два независимых ключа:

| Ключ | Назначение | Когда требуется |
|---|---|---|
| CONTROL PSK | `HELLO role=CONTROL`, обычный `COMMAND` | Начиная с network-only Stage 3 |
| Commissioning PSK | `HELLO role=COMMISSIONING`, `CALIBRATION_JOG`, запись калибровки, `ACTUATOR_QUALIFICATION` | Только с этапа, вводящего управление приводами |

Для network-only Stage 3 commissioning key не создаётся, не проверяется и не блокирует работу.
Разделение обязательно на этапах 4–5: проверка захвата не получает commissioning-полномочия
из обычного CONTROL key.

Подготовка ключей:

1. На доверенном компьютере создать независимые секреты по 32 случайных байта или больше,
   используя криптографический генератор. Не выводить один ключ из другого без пересмотра модели угроз.
2. Назначить разные `key_id`: `phantom01-control`, `phantom01-commissioning`.
3. Установить применимые ключи EV3 в отдельные защищённые файлы с минимальными правами.
4. Передать CONTROL key на Quest вне исполнительного UDP. Хранить его зашифрованным в закрытом
   хранилище приложения, используя Android Keystore для ключа шифрования; проверить доступность
   фактического механизма на Quest. Порядок — [§6.2](engineering.md#sec-8-11-1).
5. Commissioning key установить только в доверенное хранилище отладочной сборки.
   Release не имеет доступного commissioning-секрета или `commissioning_key_id`.

Ключи не хранятся открытым текстом в PlayerPrefs, Resources/StreamingAssets, Git,
манифестах, `CommissioningBundle`, журналах или телеметрии. Там допустимы только key id/slot.
Несовпадение роли и ключа отклоняется до создания сессии; CONTROL не повышается до COMMISSIONING.
Ротация выполняется независимо при запрещённом движении, инвалидирует соответствующие
сессии и требует одинакового нового ключа на обеих сторонах.

Настройка фиксированной пары входит в `python tooling install --target ev3` и `install --target quest`.
Состояние хранится в `%LOCALAPPDATA%\PHANTOM\pair.json`; SSH key, `known_hosts` и CONTROL PSK —
в соседних закрытых каталогах с ограниченным ACL. Запись пары выполняется атомарно
как локальное назначение устройств и ключей, до настройки соответствующего устройства.
Наличие pair.json не подтверждает установку, готовность credential или аппаратный PASS.
Повторная установка сохраняет назначение и ключи. Частичное или повреждённое состояние
блокирует установку до проверки и явного восстановления.
Смена доверенного отпечатка и ключей задаётся отдельно через `--repin-host`, `--rotate-ssh-key`,
`--rotate-control-secret` в установщике EV3 вместе с `--repair`, при запрещённом движении.
После ротации CONTROL повторно установить Diagnostic Quest для подготовки того же ключа.
Обычное обновление не ротирует ключи; тесты, сборка и запуск не настраивают пару.

CONTROL key EV3 хранится в `/var/lib/phantom/secrets/control.psk`, `key_slot=0`:
каталог `root:phantom-net 0750`, файл `root:phantom-net 0640`.
Только `phantom-net` читает ключ; controller, mDNS и helpers не получают доступ к нему.
Commissioning key хранится отдельным файлом с той же моделью прав, когда он требуется этапу.
Загрузчик принимает 32+ исходных байта или ровно 64 ASCII hex-символа для 32 байт.
Содержимое не выводится даже при ошибке запуска или конфигурации.

<a id="sec-engineering-contracts-quest-credentials"></a>
#### 11.5.1. Импорт ключа на Quest

Без установленного ключа CONTROL-сессия невозможна. Настройка входит в условия Stage 3.

1. На доверенном компьютере выполнить `python tooling install --target quest --artifact <Diagnostic APK>`:
   установка использует CONTROL key назначенной пары, хранимый вне репозитория,
   и при первой настройке подготавливает импорт credential. При восстановлении указать `--repair`.
2. Передать файл через ADB в каталог подготовки приложения.
3. При первом запуске отладочной сборки выполнить `importProvisioningDrop()`:
   записать AES-GCM ciphertext в закрытые preferences, ключ шифрования — в Android Keystore.
4. После обработки, успешной или отклонённой, перезаписать plaintext-файл и удалить его.
5. При запуске проверить статус ключа; интеграционные тесты подтверждают
   `quest-control-credential-ready`.

Импорт доступен только в `Diagnostic`; Release не импортирует файл.
Ключ передаётся файлом, не аргументом командной строки, не печатается и не включается в APK,
Resources, StreamingAssets, манифесты или журналы. Принимаются 32+ случайных байта
или ровно 64 ASCII hex-символа (`NFR-SEC-02`). Наружу передаётся только статус.

Отсутствие ключа даёт `PROVISION_REQUIRED`, ошибка чтения/расшифровки/хранения —
`PROVISION_CORRUPT`. В обоих случаях клиент остаётся в `AuthenticationFailure`
и не отправляет `HELLO`. Обнуление plaintext уменьшает время его хранения, но не гарантирует
физическое стирание flash или резервных копий. Передача через app-specific external storage
разрешена только в доверенной изолированной лаборатории по [§6.3](engineering.md#sec-8-12), на один запуск.
Commissioning PSK использует отдельный key id и тот же механизм, когда он требуется.

Ключ сохраняется между обычными обновлениями Diagnostic/Release через `adb install -r`.
Package id, preferences namespace, Android Keystore alias и версия формата шифрования
не меняются при таких обновлениях. Повторная настройка нужна только для нового/reset Quest,
явного удаления данных, ротации или восстановления хранилища.
Сборка и обычное обновление не меняют ключ. Первичная установка и явный `--repair` подготавливают импорт существующего ключа назначенной пары.

Проверка `python tooling integration-test --target quest --apk-a <A.apk> --apk-b <B.apk>` запускается на реальном Quest явно:
настроить ключ → установить и запустить A → обновить через `adb install -r` до B → запустить B.
Требуются два разных `build_id`. Проверяются сохранение
`dev.phantom.questprototype`, `phantom.credentials.v1`, `dev.phantom.control-credential.v1`
и успешная расшифровка, без записи секрета. Наличие файла не подтверждает готовность:
отсутствие и повреждение различаются.

<a id="sec-engineering-contracts-ev3-install"></a>
### 11.6. Установка EV3 и права служб

Установщик работает с root-правами. Службы получают отдельные полномочия:

| Служба | Доступ |
|---|---|
| `phantom-ctrl` | Controller и моторный ввод-вывод |
| `phantom-net` | UDP/HMAC и чтение сетевого ключа |
| `phantom-mdns` | Только публичная идентичность |
| `phantom-safety` | Root для supervisor и документированного перехвата управления |

IPC использует отдельные группы `phantom-ipc` и `phantom-safety-ipc`.
`/run/phantom` создаётся политикой `tmpfiles.d`, совместимой с systemd 232,
с минимальными правами для каждого endpoint. Controller/mDNS не имеют доступа к
`/var/lib/phantom/secrets`. Общая изменяемая область для сети и моторного управления запрещена.
Пользователь `robot` не получает неограниченный passwordless sudo; установка выполняется
контролируемой root/sudo-командой, вспомогательные средства получают только перечисленные команды.

Перед распаковкой проверяются пути архива, внешний хэш и хэш встроенного манифеста.
В распакованном пакете выполняется `sha256sum -c SHA256SUMS`.
Имя версии выводится из валидного 64-hex `build_id`, а не commit.

Каталоги:

```text
/opt/phantom/
  releases/
    <release-id>/
  current -> releases/<release-id>
```

Передача копирует `phantom-<build_id>.tar.gz` через SSH/SCP в каталог подготовки
установки, сверяет локальный и удалённый SHA-256 и не меняет службы или `current`.
Установщик и helpers поставляются при первичной настройке, а не с каждым пакетом.
Совпадающий файл даёт `SKIPPED_ALREADY_PRESENT`; иной хэш при том же `build_id` —
`ARTIFACT_MISMATCH`. Новые файлы передаются в `.partial`, проверяются и атомарно переименовываются.

Штатное состояние хранится в `/var/lib/phantom`, журналы — в `/var/log/phantom`,
временные IPC sockets/lease — в `/run/phantom`. Каталоги создаются с правами
соответствующих служб; правила хранения журналов — [метрики и журналы](metrics-and-logs.md#sec-8-13).

Установка выполняется при запрещённом движении:

1. Проверить внешний манифест, SHA-256 и встроенные сведения о сборке.
2. Безопасно распаковать новую версию и проверить схемы, конфигурацию, состав файлов, права и зависимости.
3. Остановить службы и подтвердить нулевой выход и безопасное состояние.
4. Сравнить units/tmpfiles с установленными; обновить только изменившиеся файлы и при необходимости выполнить daemon-reload/tmpfiles.
5. Атомарно переключить `current`, оставив службы остановленными.

Установка не выполняет self-tests, `compileall`, fault injection или интеграционные тесты.
До переключения допустимы только короткие проверки пакета с ограничением времени.
Неподтверждённая остановка или безопасное состояние блокирует переключение.

`START` запускает установленную версию в порядке зависимостей:
`phantom-safety` → `phantom-controller` → проверка готовой сети → `phantom-network` → `phantom-mdns`.
Для каждой службы проверяются результат и время запуска. После отказа зависимые службы
не запускаются. `systemctl start phantom.target` допустим, если сохраняются результаты
отдельных служб и определяется первый отказ, а не только каскад ошибок зависимостей.
Сеть поднимает ConnMan; запуск приложения не перенастраивает и не ремонтирует Wi-Fi.

При ошибке сохраняются журнал и статус первой отказавшей службы, `Result`, `ExecMainCode`,
`ExecMainStatus`, зависимые отказы, идентичность версии и конечное безопасное состояние.
Пакет не удаляется до диагностики. Запуск не выполняет fault injection или тесты.
Интеграционные тесты вызываются отдельно по [плану](test-plan.md#sec-9-1-3) и не изменяют установленную версию.

Команды для назначенного EV3:

```powershell
python tooling install --target ev3 --artifact <package.tar.gz>
python tooling start --target ev3 --build-id <ev3_build_id>
python tooling integration-test --target ev3 --build-id <ev3_build_id>
```

Остановка/перезапуск `phantom.target` распространяется на все службы через `PartOf=`
или явную остановку, чтобы процессы прежней версии не работали после переключения `current`.
При незавершённой установке восстанавливаются её изменения metadata и прежний `current`;
при первой неуспешной установке `current` удаляется. Это атомарность установки.
Удаление распакованного неуспешного пакета разрешено только после проверки, что его
канонический путь находится внутри `/opt/phantom/releases/`.

Развёртывание во время `TRACKING` запрещено.

<a id="sec-engineering-contracts-network"></a>
### 11.7. Настройка и защита сети EV3

EV3 принимает исполнительный UDP только из настроенной локальной сети.

USB gadget network используется только для инженерного обслуживания. Назначенный
EV3 определяется по сохранённому SSH fingerprint; адрес `192.168.0.1` сам по себе
не доказывает принадлежность Brick и может совпадать с LAN gateway. При link-local
диагностике дополнительно подтверждается LEGO RNDIS interface/MAC.

Wi-Fi для WNA1100 настраивается через доверенную консоль/USB/SSH до обычной работы Stage 3.
SSID/пароль хранятся только в локальной конфигурации EV3 с ограниченными правами;
не передаются через UDP и не попадают в журналы или bundle. После настройки сеть
поднимается при загрузке и переподключении без компьютера. Смена сети — отдельная операция.

Сетью управляет установленный ConnMan 1.36; второй менеджер сети запрещён.
Сохранённый профиль имеет `Favorite=true`, `AutoConnect=true`, settings доступны только root.
Если USB-драйвер `ath9k_htc` обнаруживается позже ConnMan, platform unit
`phantom-wifi-autoconnect` за ограниченное время обнаруживает интерфейс через
`/sys/class/net/*/wireless` и подключает только сохранённый профиль Favorite+AutoConnect.
Это часть первичной настройки платформы, а не каждого обновления PHANTOM.

`START` проверяет готовый интерфейс и адрес; при отсутствии выдаёт `NETWORK_NOT_READY`.
Он не перенастраивает Wi-Fi. Helper не читает и не выводит `Passphrase`, не хранит SSID/ключи
в репозитории и завершает работу по timeout. Восстановление обычного разрыва связи
выполняет ConnMan; helper не становится дополнительным daemon.

Для SSH используется аутентификация по ключам. Исполнительный UDP-сокет Release
привязывается к адресу настроенной Wi-Fi LAN, а не `0.0.0.0`, если доступны другие
маршрутизируемые интерфейсы. Firewall (`iptables` или эквивалент с сохранённой конфигурацией)
разрешает CONTROL/COMMISSIONING UDP только из доверенной подсети на этом интерфейсе.
Loopback допускается только для явно выбранных локальных тестов; остальные источники
отклоняются до парсера приложения. mDNS ограничен локальной сетью.

Port forwarding, UPnP/NAT-PMP и публикация исполнительного порта в интернете запрещены.
Первичная настройка и интеграционные тесты проверяют привязку сокета, firewall и отсутствие
лишних listeners. После смены SSID/подсети эти проверки повторяются до ручных тестов и Release.
