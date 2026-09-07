# PHANTOM — remediation независимого аудита

> **Тип:** ненормативный status/evidence record. Источником PASS/FAIL остаются
> versioned machine-readable reports в `results/**`. Этот файл только прослеживает,
> что произошло с каждым finding из `docs/AUDIT_REPORT.md`.
>
> **Дата:** 2026-09-07.
> **Аудит:** `docs/AUDIT_REPORT.md` (срез `4c842f9a`).
> **База remediation:** `a1c75802`.

## Статусы

| статус | значение |
|---|---|
| `CLOSED` | первопричина исправлена в коде/схеме/конфигурации, есть исполняемая проверка, документация приведена в соответствие |
| `PRESERVED` | аудит признал решение верным; оно намеренно сохранено без изменений |
| `NOT_APPLICABLE` | на текущем HEAD проблема не воспроизводится или пункт не является дефектом |
| `NOT_RUN_HARDWARE` | код и off-hardware проверки готовы; окончательное доказательство требует физического устройства |

`CLOSED` не используется там, где изменена только документация, а требуемый код отсутствует.

## Сводка

| статус | количество |
|---|---|
| CLOSED | 34 |
| CLOSED (код готов, device evidence отдельно) | 2 |
| PRESERVED | 2 |
| NOT_APPLICABLE | 0 |

## Findings

| Finding | Было | Что изменено | Tests/evidence | Status |
|---|---|---|---|---|
| **C-01** нет пути provisioning CONTROL PSK на Quest | `Provision()` не вызывался ниоткуда; на устройстве клиент всегда уходил в `AuthenticationFailure` | `PhantomCredentialStore.importProvisioningDrop()`/`isProvisioned()`; `AndroidPrivateControlCredentialStore.TryImportProvisioningDrop/IsProvisioned/DecodeKeyMaterial`; импорт в `PhantomRuntime` (только Diagnostic) с shredding plaintext; host-скрипт `scripts/quest-provision-credential.ps1`; DEVICE AUTO строка `quest-control-credential-present`; §8.11.1 | `tools/quest_android_nsd_check.py` (наличие пути + запрет эха ключа); `tools/security_scan.py`; device-строка остаётся `NOT_RUN` | CLOSED (код), NOT_RUN_HARDWARE (device evidence) |
| **C-02** `LOCAL_STOP` завершал controller; система не восстанавливалась и рапортовала исправность | выход из главного цикла с кодом 0, boot-id оставался, network продолжал отвечать | `stop_latched_`/`fault_latched_` внутри `ControllerCore`; процесс остаётся живым и тормозит; `request_reset_stopped()`/`acknowledge_fault()` с нормативными предусловиями; `retire_controller_boot_id()` при любом завершении; `Restart=always`, `BindsTo=` для network/mDNS | `ev3 phantom-core-tests` (латч переживает release, reset без arming, повторный reset отклонён); `phantom-controller --self-test` | CLOSED |
| **H-01** telemetry синтезировалась network-процессом | `state/fault/status` были константами, battery читалась из sysfs | `ControllerTelemetrySnapshotV1` + `TELEMETRY_QUERY` в `protocol/ipc_schema.yaml`; controller публикует snapshot; `phantom_network.telemetry()` сериализует только свежий snapshot, иначе не отправляет ничего; `HELLO` без snapshot отбрасывается; sysfs-чтение из worker убрано | `ev3 phantom-core-tests`; `phantom-network-ipc-tests`; `ev3/network/test_phantom_network.py` (3 новых теста) | CLOSED |
| **H-02** `protocol/protocol.md` не генерировался | 10-строчная заметка, объявленная generated mirror | `tools/protocolgen.py` генерирует 585-строчный mirror (enums, bitfields, типы, offsets, IPC) и проверяет его в `--check`; `protocol/README.md` стал коротким указателем | `python tools/protocolgen.py --check` | CLOSED |
| **H-03** §5.19/§7.21 расходились со схемой | prose описывала несуществующую структуру | schema объявлена единственным владельцем структуры; §7.21/§5.19 переписаны как semantics + таблица загружаемых полей + явный список полей будущих этапов; схемы `ev3`/`quest` дополнены и закрыты (`additionalProperties:false`); недостающие поля добавлены в source | `tools/test_configgen.py` (20 тестов); `configgen --check` | CLOSED |
| **H-04** safety/timing параметры зашиты в код | `RuntimeProfile` имел 4 поля, всё остальное — константы | реальный JSON-парсер (`ev3/src/json_reader.cpp`); `RuntimeProfile` загружает и валидирует network/safety/logging; двухуровневый порог `loop_safe_hold_ms`/`loop_fault_ms`; FlightRecorder глубина из конфигурации | `ev3 phantom-config-tests` (значения + 5 fail-closed случаев); `phantom-core-tests` | CLOSED |
| **H-05** нет structured events и incident-capture | controller не эмитил ни одного события; ring buffer не читался | `EventLog` (bounded, non-blocking, `LOG_STORAGE_DEGRADED`); события старта/переходов/`LOCAL_STOP`/`STOPPED`/`SAFE_HOLD`/потери supervisor; `RuntimeActiveMarker` → `UNCLEAN_SHUTDOWN`; incident freeze + `incident_id` + chunked экспорт `IncidentWriter` | `ev3 phantom-core-tests` (события, escaping, marker, incident id, freeze) | CLOSED (motor/calibration классы событий — этапы 4+, см. implementation-map) |
| **H-06** потеря supervisor давала `SAFE_HOLD`, предикаты обходились при scope 0 | ветка network-only выполнялась раньше проверок и сбрасывала fault | проверки heartbeat/loop вынесены до scope-ветки; потеря supervisor → latched `STOPPED` + `FAULT_CONTROLLER_PROCESS` (§7.24); startup-grace, чтобы boot не латчился | `ev3 phantom-core-tests` (latch при scope 0, grace, FAULT_ACK) | CLOSED |
| **H-07** IPC не покрыт cross-implementation проверкой | три рукописные кодировки | `protocol/ipc_schema.yaml` → `ipc_constants.hpp`, `ipc_layout.py`, `golden_vectors/ipc_v1.json` с побайтовыми полями; обе стороны сверяют offsets | `tools/test_ipc_contract.py`; `ev3 phantom-ipc-vector-tests` (58 полей) | CLOSED |
| **M-01** тавтологичный `nonzero_motor_writes` | счётчик всегда 0, 7 утверждений и gate | счётчик удалён; добавлен реально инкрементируемый `motor_write_attempts_rejected`; утверждения заменены на структурную проверку отсутствия actuator-поверхности | `ev3/network/test_phantom_network.py::assertNoMotorAuthority`, `test_motion_request_at_zero_scope_is_counted_as_rejected` | CLOSED |
| **M-02** нет MulticastLock, ломкая нормализация типа | разрешение объявлено, кода не было | bounded `MulticastLock` с гарантированным release на всех путях; `ACCESS_WIFI_STATE`; нормализация до `_service._proto` в Java и C#; §4.6 дополнен | `tools/quest_android_nsd_check.py`; device-проверка остаётся `NOT_RUN` | CLOSED (код), NOT_RUN_HARDWARE (device) |
| **M-03** interop только против симулятора | симулятор расходится с рабочим сервером | `tools/quest_validation/real_server_harness.py` запускает **shipped** `phantom_network.py`; отдельный сценарий в `run_udp_integration.ps1`; отчёт различает два источника | `run_udp_integration.ps1`: 9 сценариев симулятора + production-worker сценарий | CLOSED |
| **M-04** `PhantomConfig.cs` мёртвый код с hardcoded IP и MEASURED-значениями | компилировался в runtime-сборку | файл удалён; `WorkspaceConfig.Default` переименован в `UnqualifiedTestFixture` с явной пометкой | `compile_and_smoke.ps1`; grep подтверждает отсутствие потребителей | CLOSED |
| **M-05** формула отображения без `max_mapping_scale`, геометрия зашита | ограничение отсутствовало; `_nearAxis=0.05` | `MappingProfile` + `Map()` с `min(robot_nominal_reach_m, human_arm_reach*max_mapping_scale)`; невалидный профиль не даёт цель; `PhantomInverseKinematics` требует `yaw_singularity_hold_radius_m`; три параметра зарегистрированы в MEASURED | `CoreSmoke` (потолок и `ProfileUnqualified`); `configgen` prose↔registry контракт | CLOSED |
| **M-06** валидация конфигурации слабее спецификации; MEASURED инвертирован | `json.loads` last-wins, `additionalProperties:true`, запрет непустых значений | `object_pairs_hook` отклоняет дубликаты; неизвестные ключевые слова схемы fail-closed; схемы закрыты; `check_measured_registry` допускает измерение с evidence и блокирует по `required_before` | `tools/test_configgen.py` (20 тестов, включая границы MEASURED) | CLOSED |
| **M-07** нет ротации логов и деградации | безлимитный рост, исключение в кадр | `enforce_log_retention` (EV3) и `QuestJsonlLogger.EnforceRetention` (возраст/размер/число); ротация `safety-emergency.log`; логгер деградирует безопасно и один раз сообщает `LOG_STORAGE_DEGRADED`; `runtime-active`/`UNCLEAN_SHUTDOWN` | `ev3 phantom-core-tests` (retention, marker); DEVICE AUTO `quest-log-storage-healthy` | CLOSED |
| **M-08** PRE-INSTALL не проверял актуальность spec manifest | gate авторизовал установку с устаревшей identity | добавлены `specgen --check`, `docindex --check`, `doclint`, `implementation_map_check`, `skills_sync --check` | `scripts/pre-install-auto.ps1` | CLOSED |
| **M-09** CI покрывал часть PRE-INSTALL | не было network/security, artifact-gate, анализаторов | CI расширен до всего детерминированного подмножества; §8.5 фиксирует правило соответствия | `.github/workflows/ci.yml` | CLOSED |
| **M-10** нет watchdog IPC-сессии | потерянный invalidate оставлял вечную session | `last_ipc_us_` + `expire_stale_session()` по `session_stale_ms` | `phantom-network-ipc-tests` (истечение и счётчик) | CLOSED |
| **M-11** `security_scan.py` уже декларируемого audit | 2 regex, исключение любого `/test` | сканер покрывает repo, generated config, build manifests и APK; поимённый allowlist с обоснованием; entropy/base64/PEM/Wi-Fi/keystore детекторы; секрет никогда не печатается | `tools/test_security_scan.py` (17 тестов) | CLOSED |
| **M-12** bench не документирован и оставлял NOPASSWD root | production-установка наследовала правило | `ev3/bench/README.md` описывает границу с production; §8.1 фиксирует статус вне safety-периметра; `install-release` удаляет `/etc/sudoers.d/phantom-ev3-bench` и отказывается ставить, если не удалось; противоречие port mapping устранено | `bash -n deploy/scripts/install-release`; §8.1 | CLOSED |
| **M-13** канонизация не RFC 8785 | расхождение появилось бы на первом float | `protocol/jcs.py` — единственный канонизатор (UTF-16 порядок ключей, ECMAScript числа); используется во всех Python-компонентах и шипится на brick; golden vectors | `tools/test_jcs.py` (9 тестов, включая доказательство отличия от `json.dumps`) | CLOSED |
| **M-14** мелкие расхождения IPC/heartbeat | группа сокета, неограниченный drain, молчаливый takeover | `chown` в `phantom-safety-ipc`; bounded drain (16/вызов); takeover только когда прежний владелец процессуально исчез, иначе `ERR_CONTROL_SESSION_BUSY`; поведение задокументировано в §7.2.2 | `ev3 phantom-core-tests` (flood не теряет liveness); `phantom-network-ipc-tests` | CLOSED |
| **M-15** `PhantomStateMachine`: свой enum, `Fault` state, нет S9 | тест утверждал контракт, которого не было | `PhantomState`/`PhantomFault` выведены из `WireV1`; `Fault` убран из состояний (латч отдельно); реализован S9: `NoteReleaseCommandSent` + подтверждение через `last_accepted_command_sequence`; тесты переименованы и расширены | `ProtocolAndStateTests` (5 тестов); `CoreSmoke`; `QuestSyntheticQualification` | CLOSED |
| **M-16** бюджет `wifi-autoconnect` превышал `TimeoutStartSec` | попытки 4–12 недостижимы, rollback установки | 4 попытки, bounded `scan`/`connect`/`sleep`, худший случай 80 с; `TimeoutStartSec=90`; параметры переопределяемы | прогон helper на host: оба события и bounded exit | CLOSED |
| **M-17** `AGENTS.md` предполагал Codex | правила и skills не действовали для других агентов | добавлен `CLAUDE.md` (`@AGENTS.md`); skills зеркалируются в `.claude/skills/` из единственного источника; формулировки сделаны условными | `tools/skills_sync.py --check` | CLOSED |
| **L-01** дерево §8.1 неполно, `fuzz_corpus/` не существует | вводило в заблуждение | дерево приведено к фактическому; ложное упоминание каталога удалено (пустой каталог не создавался); добавлены `results/`, `mechanical/`, `ev3/bench/`, обе схемы, `implementation-map.json` | `doclint`; §8.1 | CLOSED |
| **L-02** `_pct` при `permille` в схеме | расхождение в 10 раз | во всех нормативных документах единицы duty приведены к `permille`; конверсия на EV3 стала явной и протестированной | `ev3 phantom-core-tests::permille_to_percent`; grep: `duty_pct` отсутствует | CLOSED |
| **L-03** три написания пути bundle-схемы | — | единый `config/schema/commissioning_bundle.schema.json` | grep | CLOSED |
| **L-04** дублирование `protocol/README.md` и `protocol.md` | два mutable mirror | README стал навигационной таблицей; `protocol.md` — generated mirror | `protocolgen --check` | CLOSED |
| **L-05** среда разработчика не задокументирована, пути зашиты | правка пяти скриптов при другом окружении | `tools/toolchain.ps1` + `toolchains/host-tools.json` с override-переменными; §8.1.1; README | все PowerShell-скрипты используют резолвер | CLOSED |
| **L-06** литералы вместо generated констант | `0x383u`, `!=2` | `NetworkOnlyForbiddenStatusFlags` собран из generated bitfield-констант; `WireV1.PayloadState.Unknown` | `compile_and_smoke.ps1`; `Stage3CoreTests` | CLOSED |
| **L-07** `gripper_capabilities` без определения | валидировался как 2-битный, семантики не было | биты определены в `wire_schema.yaml`: `GRIPPER_PRESENT`, `GRIPPER_REFERENCE_CAPABLE`, `0 = none`; сгенерированы константы C++/C# | `protocolgen --check`; golden vectors | CLOSED |
| **L-08** HUD смешивал языки | сырые enum и числовой код | русские названия состояний и ошибок; числовой код сохранён как provenance | `compile_and_smoke.ps1` | CLOSED |
| **L-09** canonical-zero IPC проверялся частично | — | проверяются `command_payload`/`client_nonce`/`wire_sequence` по типам, `remote_family`, все reserved | `phantom-network-ipc-tests` (6 негативных случаев) | CLOSED |
| **L-10** нет политики очистки `build/` | 24 накопленных пакета | `scripts/build-clean.ps1` (dry-run по умолчанию, защищает текущие build_id); правило записано в `AGENTS.md` | dry-run выполнен: 16 файлов помечены, ничего не удалено | CLOSED |
| **L-11 / L-12** `AGENTS.md` не описывал области репозитория и prose↔schema | — | добавлен раздел «Области репозитория за пределами production»; добавлено явное правило разрешения «поле в prose, но не в schema» | `doclint`; `configgen` проверяет обратное направление | CLOSED |
| **I-01** дисциплина evidence | признано сильной стороной | сохранено без изменений; новые gates следуют той же дисциплине | — | PRESERVED |
| **I-02** отсутствие TODO/FIXME | — | не введено ни одного TODO; все пункты реализованы или помечены как этап в implementation-map | grep | PRESERVED |
| **I-03** `run-direct` каждый вызов, потеря разрешения duty | — | `run-direct` пишется один раз при входе в режим; конверсия permille→percent явная, симметричная, с округлением | `ev3 phantom-core-tests` (8 случаев) | CLOSED |
| **I-04** Unity template/sample ассеты | — | не удалялись вслепую; поведение сборки описано, зависимость проекта не нарушена | — | PRESERVED (см. вопрос ниже) |
| **I-05** `results/**` вне инженерной навигации | — | §8.1 описывает состав и роль `results/**`; ссылки добавлены в `ARCHITECTURE.md` | `doclint` | CLOSED |
| **I-06** нет карты «требование → этап» | — | `docs/PHANTOM/implementation-map.json` (27 записей) + `tools/implementation_map_check.py` | `implementation_map_check` в CI и PRE-INSTALL | CLOSED |

## Изменение identity

Добавление bitfield `gripper_capabilities` изменило wire schema, поэтому:

```text
protocol_schema_hash: 48d85291… → 960d64e3…
ipc_schema_hash:      (новый)   → 34918932…
specification_sha256: c665c4c4… → ab5745c6…
```

Все зависимые generated артефакты, config hashes и build identities перегенерированы штатными
инструментами. Прежние PASS и artifact identities остаются **только provenance** и не
переносятся на новый candidate: требуется свежая сборка и повторный PRE-INSTALL перед любой
установкой.

## Что осталось `NOT_RUN` (аппаратное)

Ничего из перечисленного не может быть закрыто на рабочей станции:

| проверка | почему |
|---|---|
| Quest DEVICE AUTO, включая `quest-control-credential-present` и `quest-log-storage-healthy` | нужен физический Quest 3 |
| реальный Android NSD discovery и удержание `MulticastLock` | нужен физический Quest 3 в реальной сети |
| EV3 DEVICE AUTO (все Stage-3 строки) | нужен физический brick |
| Quest ↔ реальный EV3 integration | нужны оба устройства и provisioned Wi-Fi |
| физический `LOCAL_STOP` press → latched `STOPPED` → `RESET_STOPPED` | нужен fixture с кнопкой на `in4` |
| тайминг 50-Hz цикла на ARMv5TEJ | нужен brick |
| `systemd-analyze verify` на systemd 232 | нужен brick |

Symulator, host-тесты и успешная сборка не превращаются в hardware `PASS`.
