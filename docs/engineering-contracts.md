# PHANTOM — технические контракты сборки и установки

Форматы, идентификаторы и ограничения инструментов. Порядок работы и ожидаемый результат
описаны в [engineering.md](engineering.md). Этот документ предназначен для изменения build/deploy tooling.

<!-- BEGIN GENERATED TOC -->
<details>
<summary>Оглавление</summary>

- [1. Идентификаторы сборок](#sec-engineering-contracts-build-identity)
- [2. Проверка и воспроизводимость пакетов](#sec-engineering-contracts-package-validation)
- [3. Пакет EV3](#sec-engineering-contracts-ev3-package)
- [4. Пакет Quest](#sec-engineering-contracts-quest-package)
- [5. Каноническая конфигурация](#sec-engineering-contracts-configuration)
  - [5.1. Ревизии конфигурации для квалификации и Release](#sec-engineering-contracts-qualification-bundles)
- [6. Хранение и импорт ключей](#sec-engineering-contracts-credentials)
  - [6.1. Импорт ключа на Quest](#sec-engineering-contracts-quest-credentials)
- [7. Установка EV3 и права служб](#sec-engineering-contracts-ev3-install)
- [8. Настройка и защита сети EV3](#sec-engineering-contracts-network)

</details>
<!-- END GENERATED TOC -->

<a id="sec-engineering-contracts-build-identity"></a>
## 1. Идентификаторы сборок

`build_id` отличает компонент, режим и входные данные сборки.
Документация не является входом сборки и не влияет на этот идентификатор.
`source_tree_hash` исключает Markdown, reStructuredText, AsciiDoc, `docs/`,
сгенерированный `docs/protocol-wire-reference.md`, кэши интерпретатора, результаты и готовые пакеты.
Входы EV3 объявлены в `EV3_SOURCE_INPUTS` в [source_hash.py](../tools/source_hash.py):
штатные C++-исходники и заголовки, действующие сетевые entrypoints, протокол, deployment
и общий ARM toolchain. Тестовые исходники исключены; builder и проверка пакета
используют один список через `--component EV3`. После переноса network/mDNS список
обновляется по фактическим входам C++-сборки.

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
## 2. Проверка и воспроизводимость пакетов

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
## 3. Пакет EV3

Кросс-сборка использует образ `ev3dev/debian-stretch-cross:latest`, закреплённый по digest.
Изменяемый тег используется только для первоначального поиска образа, а не как вход CI/Release.
Платформа — `ARMv5TEJ / armel / gnueabi`; обязательные флаги:
`-march=armv5te -mfloat-abi=soft`. Версии, digest и SHA-256 компилятора берутся из
[toolchain lock](../toolchains/ev3dev-stretch.lock.json); требования CMake — из
[проекта EV3](../ev3/CMakeLists.txt).

Для релиза также фиксируются образ, установленный на EV3, его SHA-256, снимок пакетов,
SBOM и результаты проверки уязвимостей. Значения `UNRESOLVED`/`PENDING` разрешают
разработку и интеграционные тесты, но не подтверждают готовность релиза.

Все устанавливаемые unit-файлы проходят `systemd-analyze verify` на baseline systemd 232.
Директивы `StateDirectory=`, `LogsDirectory=` и `RuntimeDirectoryPreserve=` требуют
совместимого fallback. Устанавливаемые вспомогательные Python-скрипты сохраняют
совместимость с Python 3.5 pinned image; синтаксис проверяется в TEST/BUILD,
а INSTALL не запускает compileall или self-tests.
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
phantom-device-integration-test
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
cross_image_digest
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
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ev3-build.ps1 -Profile Diagnostic
```

Команда компилирует ARM-код, упаковывает его и проверяет готовый пакет.
Тесты запускаются отдельно. Незакоммиченные изменения разрешены;
`git_commit` и `worktree_dirty` записываются честно, но не определяют разрешение установки.
Упаковщик нормализует владельцев, порядок файлов, mtime и заголовок gzip.
Пакеты разных режимов имеют разные `build_id`.
Воспроизводимость проверяется по [§5.3](engineering.md#sec-engineering-build-validation).

<a id="sec-engineering-contracts-quest-package"></a>
## 4. Пакет Quest

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
`ACCESS_LOCAL_NETWORK`, поскольку PHANTOM сам обнаруживает настроенный `robot_id`
и открывает UDP. Доступ NSD через системный выбор службы требует отдельного пересмотра UX/безопасности.
Для прежних сочетаний API проверяется необходимость foreground multicast lock;
он освобождается по lifecycle. Отказ или отзыв разрешения не заменяется жёстко заданным IP.

Манифест сборки фиксирует Unity и пакеты. Версия Horizon OS определяется только на
Quest и записывается в отчёт платформенной проверки вместе с `build_id` и `apk_sha256`.
Оба документа связывают пакет с реально проверенной платформой.

<a id="sec-engineering-contracts-configuration"></a>
## 5. Каноническая конфигурация

Конфигурация разделяет данные, определяющие поведение, и сведения об их происхождении:

```text
semantic_payload:
  schema_version
  revision
  safety/config fields или component hashes
content_hash = SHA-256(JCS(semantic_payload))

provenance_sidecar:         # отдельный файл; не входит в content_hash
  semantic_content_hash
  created_by_build
  created_at
  transaction_id / evidence reference, если применимо
```

При сборке и калибровке `semantic_payload` сохраняется как канонический JCS JSON,
а сведения о происхождении — отдельным файлом. Runtime проверяет SHA-256 установленных
байтов, не сериализуя объект заново. Внешний файл может иметь свой хэш и ссылается
на `semantic_content_hash`; его отсутствие или время создания не меняет совместимость приводов.

`CommissioningBundle` использует тот же принцип:
`commissioning_bundle_hash = SHA-256(JCS(bundle_semantic_payload))` хранится в оболочке,
манифесте или runtime metadata, но не внутри `bundle_semantic_payload`.
Хэш компонента хранится в содержащем его bundle, а не в хэшируемом компоненте.
Время, имя компьютера и локальные metadata не влияют на допуск приводов.

`bundle_id` не входит в `semantic_payload` и вычисляется после хэша:

```text
bundle_id = "cb-" + lowercase_hex(first_16_bytes(commissioning_bundle_hash))
```

Обе стороны получают одинаковый идентификатор без случайного UUID, времени или hostname.

Установка геометрии и данных безопасности выполняется через инженерный доступ,
а не исполнительный UDP. В протоколе v1 нет `SET_ROBOT_GEOMETRY` или передачи файлов
по частям: `RobotGeometry`, `RobotCollisionModel`, PayloadProfiles и `JointSafeSet`
могут превышать размер управляющего пакета и не должны обновляться частично.

1. Сохранить результат инженерной калибровки на Quest или компьютере как канонические данные.
2. Собрать полный `CommissioningBundle` для проверки (`qualification_only=true`);
   проверить схемы, коллизии и связи с требованиями.
3. При запрещённом движении установить одинаковые байты компонентов на обе стороны:
   ADB для Quest, SSH/USB для EV3.
4. После успешной проверки `QualificationEvidenceManifest` подготовить рабочую ревизию
   (`qualification_only=false`). Байты компонентов и их хэши сохраняются; добавляются
   только сведения о результатах проверки. Изменение геометрии/калибровки требует новой приёмки.
5. Активировать ревизию через временный файл, fsync и атомарное переключение,
   сохраняя предыдущую ревизию на случай незавершённой установки.

Установка инвалидирует runtime sessions и привязки. Новый `HELLO` должен вернуть ожидаемый
`commissioning_bundle_hash` до привязки и движения. Неполная установка пары или несовпадение
хэшей блокирует движение; частично установленный bundle не используется.
`SET_DRIVE_CALIBRATION` остаётся ограниченной транзакцией калибровки с обработкой потери ACK
по [протоколу §2.5](protocol-specification.md#sec-4-7-5). Итоговая замена данных следует правилам выше.

Изменения конфигурации обрабатываются так:

| Изменение | Что требуется |
|---|---|
| Передача, крепление мотора, смысл encoder или `encoder_scale` | Новая `DriveCalibration` |
| Крепление QR, ось, `L1`, `L2`, положение пола относительно Shoulder, TCP | Новая ревизия `RobotGeometry` |
| Упор Base, прокладка кабеля или диапазон pitch | Повторная калибровка безопасных границ |
| Перезапуск EV3/controller или новый `controller_boot_id` | Сохранить persistent `DriveCalibration`; инвалидировать runtime `JointReference`, `GripperReference` и старые sessions |
| Новая `DriveCalibration` | Создать неизменяемую bundle revision с заменой соответствующего компонента, `new_bundle_revision = previous_bundle_revision + 1` |
| Активация новой bundle revision | Закрыть прежние sessions; новый `HELLO` подтверждает новый хэш до движения |
| Новый HMAC key | Новая сетевая сессия |
| Только пользовательский интерфейс | `RobotGeometry` и `DriveCalibration` сохраняются |

Quest и EV3 вычисляют хэш кандидата из одинаковых канонических компонентов.
Несовпадение требует исправления настройки или файлов; изменение активной ревизии на месте запрещено.

<a id="sec-engineering-contracts-qualification-bundles"></a>
### 5.1. Ревизии конфигурации для квалификации и Release

Для `build_profile=Release` authoring schema обязана отклонять `qualification_only=true`, `actuator_scope_mask != 0x0F` и `safety_observation_mask != 0x0F`. Нулевой `qualification_evidence_manifest_hash` разрешён в source/generated config только как явно заблокированный `UNQUALIFIED_RELEASE_CANDIDATE`: runtime остаётся fail-closed и такой config нельзя установить/опубликовать как production release. Release **packaging/publication gate**, в отличие от schema/generator и compile-only build, обязательно отклоняет нулевой/отсутствующий evidence hash либо manifest, чей component-set hash не совпадает с production bundle, и проверяет PASS всех обязательных evidence refs. Простая ручная смена `qualification_only:true→false` не создаёт допустимый release и должна fail packaging/release validation. На этапах 3–5 ранний Diagnostic mechanical/safety bundle разрешает только пары масок `0x00/0x00` (network-only) и `0x08/0x08` (Gripper). Соответствующий Quest profile отдельно использует `required_user_inputs=NONE` для Stage 3 и phase-specific QR commissioning либо `GRIPPER_ONLY` для user-driven Stage 5. На этапах 6–7 Diagnostic `COMMISSIONING/CALIBRATION` может использовать versioned scope всех фактически подключённых осей текущего стенда, если их motor/mechanics/safety prerequisites [Спецификация Quest §16.1](quest-specification.md#sec-5-16-1) выполнены; отдельный `CALIBRATION_JOG.axis` выбирает единственную движущуюся ось, а штатный `COMMAND` для A/B/C при этом запрещён. Scoped A/B/C `ACTUATOR_QUALIFICATION` допускается только с полными `RobotGeometry`, `DriveCalibration`, `JointReference A/B/C`, `EMPTY` profile-specific `JointSafeSet`, `safety_observation_mask & 0x07 == 0x07`, `actuator_scope_mask & ~safety_observation_mask == 0` и пройденными **pre-motion** prerequisites [План проверки](test-plan.md#sec-9) (exhaustive safe-set proof, mechanical/fixture inspection, `LOCAL_STOP`/`POWER_CUT`, интеграционные тесты с нулевым выходом приводов и применимые P0 gates). Сам движущийся incremental MANUAL case не может быть prerequisite самому себе: он последовательно создаёт qualification evidence по [Метрики и анализ §4.7.7](metrics-and-logs.md#sec-9-15-7)/[Метрики и анализ §4.9](metrics-and-logs.md#sec-9-17)–[Метрики и анализ §4.10](metrics-and-logs.md#sec-9-19) и [Этапы реализации §11](implementation-stages.md#sec-10-11). Маска motor authority может быть уже (`C`, `B+C` и т.п.), но безопасность всегда вычисляется по реальным observed A/B/C.

Для incremental A/B/C MANUAL узкая authority **не является runtime override** production bundle. Все narrow authority cases (`C`, `B+C`, затем A+B+C narrow/full-authority bring-up до payload qualification) выполняются только с **пустым Gripper без внешнего payload** и используют installed `EMPTY` PayloadProfile + matching `EMPTY` JointSafeSet. После reference tooling явно устанавливает engineering `SET_PAYLOAD_PROFILE=EMPTY` и `SET_PAYLOAD_STATE=EMPTY` при stationary motors и снятом qualification arm; это не product state, а доказуемый input safety gate. `LOADED`, non-empty profile, pickup/release и object-contact-as-payload в narrow qualification запрещены. Loaded-payload cases допускаются только в отдельном full `0x0F/0x0F qualification_only=true` bundle с полными A/B/C/D references и специальными engineering payload gates [Спецификация протокола §2.5](protocol-specification.md#sec-4-7-5). Engineering tooling создаёт каждую immutable derived revision из принятого production-candidate semantic component set: narrow bundles ссылаются на те же geometry/DriveCalibration/collision/SafetyEnvelope hashes и EMPTY profile/safe-set; full qualification bundle может переключать только уже установленные candidate payload profiles/safe-sets, не меняя их bytes. Каждая revision имеет собственный `commissioning_bundle_hash`, проходит двухсторонний deployment/hash check и при активации инвалидирует session/JointReference/GripperReference. После qualification production bundle создаётся/promote-ится отдельной revision; MANUAL никогда не переписывает masks in-place.

<a id="sec-engineering-contracts-credentials"></a>
## 6. Хранение и импорт ключей

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

Для фиксированной пары используется `phantom.cmd PROVISION PAIR`.
Состояние хранится в `%LOCALAPPDATA%\PHANTOM\pair.json`; SSH key, `known_hosts` и CONTROL PSK —
в соседних закрытых каталогах с ограниченным ACL. Запись пары выполняется атомарно
после успешной настройки обеих сторон. Повтор с корректным состоянием возвращает
`ALREADY_PROVISIONED`. Частичное или повреждённое состояние требует явного `-Repair`.
Смена доверенного отпечатка и ключей задаётся отдельно через `-RepinHost`, `-RotateSshKey`,
`-RotateControlSecret`, при запрещённом движении. Обычные тесты, сборка, установка
и запуск не создают и не меняют состояние пары.

CONTROL key EV3 хранится в `/var/lib/phantom/secrets/control.psk`, `key_slot=0`:
каталог `root:phantom-net 0750`, файл `root:phantom-net 0640`.
Только `phantom-net` читает ключ; controller, mDNS и helpers не получают доступ к нему.
Commissioning key хранится отдельным файлом с той же моделью прав, когда он требуется этапу.
Загрузчик принимает 32+ исходных байта или ровно 64 ASCII hex-символа для 32 байт.
Содержимое не выводится даже при ошибке запуска или конфигурации.

<a id="sec-engineering-contracts-quest-credentials"></a>
### 6.1. Импорт ключа на Quest

Без установленного ключа CONTROL-сессия невозможна. Настройка входит в условия Stage 3.

1. На доверенном компьютере выполнить `scripts/quest-provision-credential.ps1 -KeyFile <вне репозитория>`.
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
Сборка, установка, запуск и тесты не копируют, не меняют и не удаляют ключ.

Проверка `scripts/quest-credential-persistence-test.ps1` запускается на реальном Quest явно:
настроить ключ → установить и запустить A → обновить через `adb install -r` до B → запустить B.
Требуются два разных `build_id`. Проверяются сохранение
`dev.phantom.questprototype`, `phantom.credentials.v1`, `dev.phantom.control-credential.v1`
и успешная расшифровка, без записи секрета. Наличие файла не подтверждает готовность:
отсутствие и повреждение различаются.

<a id="sec-engineering-contracts-ev3-install"></a>
## 7. Установка EV3 и права служб

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
scripts\phantom.cmd TRANSFER EV3 -Package <package.tar.gz>
scripts\phantom.cmd INSTALL EV3 -BuildId <ev3_build_id> -PackageSha256 <package_sha256>
scripts\phantom.cmd START EV3 -BuildId <ev3_build_id>
scripts\phantom.cmd DEVICE EV3 -BuildId <ev3_build_id>
```

Остановка/перезапуск `phantom.target` распространяется на все службы через `PartOf=`
или явную остановку, чтобы процессы прежней версии не работали после переключения `current`.
При незавершённой установке восстанавливаются её изменения metadata и прежний `current`;
при первой неуспешной установке `current` удаляется. Это атомарность установки.
Удаление распакованного неуспешного пакета разрешено только после проверки, что его
канонический путь находится внутри `/opt/phantom/releases/`.

Развёртывание во время `TRACKING` запрещено.

<a id="sec-engineering-contracts-network"></a>
## 8. Настройка и защита сети EV3

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
