# PHANTOM — спецификация протокола Quest↔EV3

Нормативная семантика transport/session/transaction. Точный binary layout принадлежит `protocol/wire_schema.yaml` и generated artifacts.

<!-- BEGIN GENERATED TOC -->
<details>
<summary>Оглавление</summary>

- [1. Сетевое обнаружение EV3](#sec-4-6)
- [2. Сетевой протокол](#sec-4-7)
  - [2.1. Транспорт](#sec-4-7-1)
  - [2.2. Аутентификация](#sec-4-7-2)
  - [2.3. Общий заголовок](#sec-4-7-3)
  - [2.4. Типы сообщений](#sec-4-7-4)
  - [2.5. Сообщения инженерной калибровки и привязки](#sec-4-7-5)
  - [2.6. `COMMAND`](#sec-4-7-6)
  - [2.7. Принятие команды](#sec-4-7-7)
  - [2.8. `TELEMETRY`](#sec-4-7-8)
- [3. Семантика состояний и ошибок](#sec-11-2)
- [4. Нормативный wire contract protocol v1 — source ownership and generation gate](#sec-11-8)
  - [4.1. Schema/code-generation gate](#sec-protocol-specification-4-1)

</details>
<!-- END GENERATED TOC -->

<a id="sec-4-6"></a>
## 1. Сетевое обнаружение EV3

EV3 публикует DNS-SD/mDNS service:

```text
service type: _phantom-ev3._udp
browse domain: local.
full browse name: _phantom-ev3._udp.local.
instance:     PHANTOM-<robot_id>
port:         фактический IPv4 UDP command port
TXT:
  robot_id=phantom01
  protocol_major=1
  controller_boot_id=<32 hex chars>
  build_id=<installed build id>
```

На EV3 publication выполняется через системный Avahi по D-Bus; собственная реализация mDNS-пакетов не используется. В API Avahi `type="_phantom-ev3._udp"`, `domain="local."` (либо default domain, подтверждённый как `local.`), publication ограничена IPv4 для protocol v1. Android Quest передаёт `NsdManager` именно service type `_phantom-ev3._udp`; `.local` не является частью serviceType. Однако платформа возвращает тип в разных написаниях (`_phantom-ev3._udp`, `_phantom-ev3._udp.`, `_phantom-ev3._udp.local`, `_phantom-ev3._udp.local.`), поэтому adapter обязан нормализовать полученное значение до `_service._proto` перед сравнением. Строгое сравнение с одной формой молча отбрасывает реально объявленного робота. TXT содержит только публичную identity/compatibility metadata. Wi-Fi credential, control/commissioning PSK, HMAC material, session id и локальные пути к secret files в TXT запрещены.

Scope v1 допускает обнаружение нескольких DNS-SD instances, но активна только одна выбранная/ожидаемая пара Quest↔`robot_id`; одновременное управление несколькими роботами не реализуется.

Quest должен:

1. выполнять browse при запуске и после потери соединения;
2. выбирать сервис по `robot_id`, а не по IP;
3. разрешать текущее имя сервиса в IPv4/port непосредственно перед установлением сессии; IPv6-only result в v1 не используется для control;
4. при изменении адреса закрывать старую сетевую сессию и создавать новую;
5. не переносить `session_id` или `controller_boot_id` на новый обнаруженный сетевой адрес без повторного установления сессии.

Quest discovery adapter использует platform `NsdManager`/DNS-SD и обязан учитывать platform lifecycle/permission contract: discovery останавливается при уничтожении соответствующего app lifecycle owner и запускается заново при возвращении; на старых Android/SDK-extension комбинациях, где foreground mDNS требует ручного `WifiManager.MulticastLock`, lock удерживается только bounded временем discovery и гарантированно освобождается. Local-network permission policy определяется [Требования к продукту §4.6](product-requirements.md#sec-3-2-6)/[Разработка и развёртывание §5.5](engineering.md#sec-8-8) и не подменяется сохранённым IP.

В инженерном `Diagnostic` допускается ручной ввод адреса для лабораторной диагностики, но он не является штатным пользовательским механизмом и не заменяет проверку `robot_id`/HMAC.

<a id="sec-4-7"></a>
## 2. Сетевой протокол

<a id="sec-4-7-1"></a>
### 2.1. Транспорт

Используется UDP в доверенной локальной сети. **PHANTOM protocol v1 квалифицирует только IPv4 transport**: EV3 listener и DNS-SD publication обязаны предоставлять IPv4 endpoint, а Quest не переключается молча на IPv6. IPv6 может быть добавлен только после отдельной simulator/device/MANUAL qualification без изменения identity semantics. Поток движения реализует семантику «последняя валидная цель заменяет старую».

```text
порт EV3 по умолчанию: 30470
максимальная принимаемая датаграмма: 1024 bytes
```

Точный byte order, scalar encoding, header/auth-tag widths, per-message payload lengths и
protocol numeric fields задаются `protocol/wire_schema.yaml` и generated
`docs/protocol-wire-reference.md`; этот prose их вручную не дублирует.

`HELLO_ACK.reserved0` содержит только нули и проверяется получателем после HMAC.
Документация не передаётся как compatibility identity; допуск определяется
`protocol_contract_hash`, build/profile identity и authoritative configuration/bundle.

<a id="sec-4-7-2"></a>
### 2.2. Аутентификация

Каждая датаграмма завершается:

```text
HMAC-SHA-256(PSK, header || payload)
```

`PSK` содержит не менее 32 случайных байт. HMAC сравнивается constant-time. HMAC не шифрует payload и не скрывает телеметрию.

<a id="sec-4-7-3"></a>
### 2.3. Общий заголовок

Exact header layout/types/widths/reserved values задаются `protocol/wire_schema.yaml` и
generated `docs/protocol-wire-reference.md`. Здесь фиксируется только behavioral semantics полей:

| Поле | Смысл |
|---|---|
| `message_type` | schema-defined тип сообщения |
| `payload_length` | exact schema-defined длина payload конкретного message type |
| `session_id` | нулевой в `HELLO` и authenticated reject; только успешный `HELLO_ACK(result_code=OK)` выдаёт новый ненулевой CSPRNG session id |
| `controller_boot_id` | случайный идентификатор запуска `phantom-controller`; `HELLO` обязан адресовать текущий boot id |
| `sequence` | строго возрастающий номер сообщения отправителя внутри session |
| `sender_monotonic_us` | диагностическое монотонное время отправителя |
| `hmac` | полный authentication tag, размер/расположение которого задаёт schema |

`HELLO` имеет `session_id=0`; его payload содержит `robot_id`, `protocol_minor`, bounded `key_slot`, `session_role` и свежий CSPRNG `client_nonce`. `controller_boot_id` обязан быть взят из актуального DNS-SD TXT. Если он отсутствует/невалиден, Quest не посылает CONTROL `HELLO`, а повторяет discovery; нулевой boot id в v1 не разрешён. После exact HELLO length check принимающая сторона может прочитать фиксированные `key_slot/session_role` **только как недоверенные selectors** для выбора одного заранее установленного PSK, затем проверяет HMAC; `robot_id`, nonce и остальные semantic поля доверяются/валидируются только после HMAC. Только EV3 создаёт `session_id` и возвращает его в `HELLO_ACK` вместе с эхом `client_nonce`. `HELLO_ACK.result_code=OK` означает успешное создание session и требует ненулевой `session_id`; authenticated semantic rejection (`ERR_CONTROL_SESSION_BUSY`, `ERR_COMMISSIONING_NOT_ARMED`, role/key-slot mismatch и аналогичные post-HMAC ошибки) возвращается тем же `HELLO_ACK` с `session_id=0` и ненулевым `result_code`, не создаёт owner/session authority и не разрешает трактовать остальные diagnostic fields как active-session state. Для authenticated rejected `HELLO_ACK` поля `accepted_key_slot/accepted_role` **эхо-повторяют уже HMAC-проверенные selectors запроса**, identity/build/hash/state/reference/capability поля описывают текущий EV3, но не создают authority; safe bounds/limits при отсутствии выбранного применимого runtime profile имеют canonical zero. Для **любого** `HELLO_ACK`, включая successful session, fixed-layout поля с неприменимой для active bundle/runtime семантикой имеют единственное каноническое представление: отсутствующий semantic component hash является all-zero value точной schema-defined ширины; `active_joint_safe_set_hash=0` при `UNSELECTED`/неприменимом JointSafeSet; reference bit для неприменимого domain=`0`; A/B/C `safe_joint_*` и `joint_max_*` равны `0.0f` для оси, не входящей в применимый A/B/C motor/safety domain. Поэтому network-only `0x00/0x00` возвращает нулевые `robot_geometry_hash/drive_calibration_hash/active_joint_safe_set_hash/payload_profiles_hash`, `reference_flags=0` и все A/B/C limits=0, но **ненулевой** `commissioning_bundle_hash` своего network-only bundle. D-only `0x08/0x08` после gripper commissioning может иметь ненулевые hash gripper-geometry/DriveCalibration subset и `GRIPPER_REFERENCE_VALID`, но `JOINT_REFERENCE_VALID=0`, `active_joint_safe_set_hash=0` и все A/B/C limits=0. Partial A/B/C qualification заполняет limits только для реально применимого A/B/C domain bundle; нули вне него означают `N_A`, а не физическое значение ноль. Unknown/uninstalled key slot и bad HMAC остаются silent drop, чтобы unauthenticated traffic не получал oracle/response. Свежесть COMMAND определяется временем приёма EV3, а не сравнением часов устройств.

`HELLO.capabilities_requested` в protocol v1 имеет canonical value `0`. Любое ненулевое значение, обнаруженное после успешной HMAC-проверки, приводит к authenticated `HELLO_ACK(result_code=ERR_UNSUPPORTED, session_id=0)`. Поле зарезервировано для versioned negotiation будущего protocol minor и не меняет layout v1.

Перед type-specific payload parsing выполняются exact generated length checks из `protocol/wire_schema.yaml`/`docs/protocol-wire-reference.md` согласно [§4](#sec-11-8). Total datagram не превышает security limit `1024` bytes из `NFR-SEC-03`; header/payload/auth-tag widths берутся только из current schema-generated contract.

Session lifecycle:

- одновременно существует не более одной `CONTROL` session; пока она свежая или `TRACKING` активен, иной криптографически валидный `CONTROL HELLO` получает rejected `HELLO_ACK(result_code=ERR_CONTROL_SESSION_BUSY, session_id=0)`;
- `COMMISSIONING` session создаётся только при отсутствии активной CONTROL session, состоянии `DISCOVERY` и действующем локальном arm-window `LOCAL_COMMISSION_ARM`; успешный `HELLO role=COMMISSIONING` напрямую переводит EV3 `DISCOVERY → COMMISSIONING`. Normal CONTROL и commissioning session одновременно не существуют. Protocol v1 **не имеет `SESSION_CLOSE` datagram**: добровольный отказ Quest от CONTROL выполняется bounded OFF/HOLD burst → прекращение CONTROL traffic → локальное удаление session; EV3 после `session_stale_ms` инвалидирует owner/session. Если приложение уже имело CONTROL context, commissioning допускается только после фактического исчезновения fresh CONTROL owner и локального перехода/подтверждения `DISCOVERY`; network packet не может ускорить этот переход. Та же commissioning session может после калибровки перейти во внутреннюю фазу `ACTUATOR_QUALIFICATION`; потеря session немедленно завершает эту фазу;
- `HELLO role=CONTROL` в `STOPPED` допускается как **recovery-only CONTROL session**, если HMAC/key/robot/boot valid и активной commissioning session нет. Пока blocking latch не очищены, такая session никогда не получает actuator authority и допускает только `PING`, telemetry/diagnostics и recovery transactions `FAULT_ACK`/`RESET_STOPPED`; после успешного recovery она продолжает обычный CONTROL lifecycle, но начинает dearmed с `release_seen=false`;
- после timeout/перехода в `HOLD`/`SAFE_HOLD` новая валидная CONTROL session может заменить старую, при этом moving target/sequence/armed-latch/release latch старой session инвалидируются;
- duplicate `HELLO` с тем же `(endpoint, role, client_nonce)` внутри `hello_retry_window_ms` возвращает тот же cached semantic `HELLO_ACK`/session id **только пока соответствующая session/config generation остаётся authoritative**. Любая invalidation session, смена `commissioning_bundle_hash`, `controller_boot_id`, role-owner state или explicit config-commit invalidation немедленно инвалидирует HELLO cache; после этого тот же nonce не может воскресить старую session и обрабатывается как новый/current-state handshake либо reject;
- после retry window такой HELLO является новым handshake и получает новый server-generated session id; replay старых COMMAND не подходит к нему по `session_id`/HMAC;
- `sequence` строго возрастает отдельно по направлению внутри session, начинается с `1` после handshake, wrap запрещён;
- защита от L2/UDP replay-DoS не заявляется как криптографическая гарантия v1; trusted/isolated LAN остаётся обязательным допущением [Требования к продукту §4.6](product-requirements.md#sec-3-2-6).

Нормативным single source of truth **структуры** wire format является `/protocol/wire_schema.yaml`. Он обязан задавать для **каждого** message type точный порядок полей, scalar type/width, enum numeric values, bit positions, fixed array lengths, reserved bytes и exact payload length; machine-readable межреализационная semantics принадлежит `/protocol/semantics.yaml`, human-readable mirror генерируется как `docs/protocol-wire-reference.md`, а [§4](#sec-11-8) задаёт ownership/generation policy. Контекстные ranges/transition guards, зависящие от active `CommissioningBundle`, остаются в owning prose. Из sources генерируются structural/semantic/contract canonical artifacts, C++14/C# constants/size maps и golden vectors. Production codecs могут быть hand-written, но CI проверяет их общими vectors. Build manifests содержат `protocol_schema_hash`, `protocol_semantics_hash` и `protocol_contract_hash`; `HELLO_ACK` передаёт compatibility `protocol_contract_hash`. Whitespace/line endings authoring files не входят в identity.

<a id="sec-4-7-4"></a>
### 2.4. Типы сообщений

| Сообщение | Направление | Назначение |
|---|---|---|
| `HELLO` | Quest→EV3 | начало логической сессии |
| `HELLO_ACK` | EV3→Quest | идентификатор робота, сборка, конфигурация и возможности |
| `CALIBRATION_QUERY` | Quest→EV3 | запрос атомарного снимка исходных отсчётов энкодеров |
| `CALIBRATION_SAMPLE` | EV3→Quest | исходные отсчёты энкодеров и `sample_id` |
| `SET_JOINT_REFERENCE` | Quest→EV3 | установить текущую QR↔энкодер привязку |
| `REFERENCE_ACK` | EV3→Quest | результат привязки |
| `COMMISSIONING_SAMPLE` | Quest→EV3 | принятое после остановки QR↔энкодерное измерение для журнала инженерной калибровки; успешное/идемпотентно повторённое принятие подтверждается `CONTROL_ACK(operation_type=COMMISSIONING_SAMPLE)` |
| `CALIBRATION_JOG` | Quest→EV3 | ограниченное малое калибровочное перемещение одной оси |
| `JOG_ACK` | EV3→Quest | результат перемещения и атомарный итоговый снимок энкодеров |
| `SET_DRIVE_CALIBRATION` | Quest→EV3 | передать проверенную `DriveCalibration` после контроля на независимых положениях |
| `DRIVE_CALIBRATION_ACK` | EV3→Quest | результат проверки и атомарного сохранения калибровки |
| `FAULT_ACK` | Quest→EV3 | подтверждение устранённой неисправности |
| `CONTROL_ACK` | EV3→Quest | идемпотентный ACK управляющей операции |
| `RESET_STOPPED` | Quest→EV3 | запрос выхода из latched `STOPPED` после физического отпускания `LOCAL_STOP`; требует re-arm |
| `SET_PAYLOAD_PROFILE` | Quest→EV3 | выбрать установленный в active bundle `PayloadProfile` и его safe-set; production требует evidence-qualified profile, qualification-only допускает только candidate profile по [§2.5](#sec-4-7-5); production: startup `ROBOT_CALIBRATION` после full reference либо `READY/HOLD`; engineering: только разрешённые qualification cases [§2.5](#sec-4-7-5); всегда stationary |
| `SET_PAYLOAD_STATE` | Quest→EV3 | подтвердить `EMPTY`/`LOADED`; production: startup `ROBOT_CALIBRATION` либо `READY/HOLD`; engineering: только qualification cases [§2.5](#sec-4-7-5); всегда stationary и arm-invalidating |
| `COMMAND` | Quest→EV3 | последняя абсолютная цель движения |
| `TELEMETRY` | EV3→Quest | штатное фактическое состояние |
| `DIAGNOSTIC_TELEMETRY` | EV3→Quest | расширенные данные только в Diagnostic |
| `PING` | оба | RTT/доступность |
| `PONG` | оба | ответ |

Exact numeric `message_type` values принадлежат `protocol/wire_schema.yaml` и generated `docs/protocol-wire-reference.md`; они намеренно не дублируются в hand-written spec.
Операции, изменяющие persistent/session state или физическое состояние (`FAULT_ACK`, `RESET_STOPPED`, `SET_PAYLOAD_PROFILE`, `SET_PAYLOAD_STATE`, `COMMISSIONING_SAMPLE`, `CALIBRATION_JOG`, reference/calibration writes) сериализованы: Quest не отправляет вторую state-changing transaction, пока первая не завершена/не истёк её bounded retry policy. `transaction_id:u64` строго возрастает **в пределах одной session**.

Transaction layer начинается только после успешных HMAC, session/boot, wire-sequence и exact type-length checks, когда `transaction_id` безопасно доступен. Для `id==last+1` controller вычисляет `canonical_request_hash = SHA-256(message_type_le_u16 || exact_payload_bytes)` **до semantic field/range/state checks**, затем выполняет operation validation. Любой сформированный operation-specific ACK (`OK` или детерминированный `ERR_FORMAT/ERR_RANGE/ERR_STATE/ERR_REFERENCE/ERR_FAULT/ERR_HASH_MISMATCH/...`) считается завершённой transaction: `{id,hash,response_message_type,ack_payload_bytes}` сохраняется и `last_transaction_id` продвигается. Исправленная операция поэтому использует **следующий** transaction id; повтор того же id с изменённым payload является conflict. Пакеты, отброшенные до transaction layer (bad HMAC/session/boot/wire sequence/exact length), transaction id не consume-ят. `ERR_TRANSACTION_STALE/CONFLICT/GAP` также не продвигают `last_transaction_id`.

Exact retry `id==last && hash==last_hash` не повторяет side effect и возвращает тот же semantic ACK payload/result; `phantom-network` оборачивает его в новую ответную wire-datagram с очередным EV3→Quest `sequence`, актуальным `sender_monotonic_us` и заново вычисленным HMAC. Повтор byte-identical старой datagram запрещён. `id==last && hash!=last_hash` → `ERR_TRANSACTION_CONFLICT`; `id<last` → `ERR_TRANSACTION_STALE`; `id>last+1` → `ERR_TRANSACTION_GAP`. В новой session `last_transaction_id=0`, первая операция имеет `transaction_id=1`; session boundary не переносит idempotency физического side effect автоматически. Wire header намеренно не входит в canonical request hash, поэтому retry может иметь новый Quest→EV3 `sequence`.

<a id="sec-4-7-5"></a>
### 2.5. Сообщения инженерной калибровки и привязки

`CALIBRATION_QUERY` не двигает моторы. Для **startup/reference snapshot** EV3 атомарно читает все оси из `safety_observation_mask` и возвращает `CALIBRATION_SAMPLE` с уникальным `sample_id`, текущим `controller_boot_id`, скоростью и монотонным временем. Поля массивов A/B/C/D сохраняют fixed wire layout: оси вне `safety_observation_mask` передаются canonical zero/`N_A`; отсутствие/невалидность оси внутри safety-observation является hardware/config failure. Это принципиально шире motor authority при partial A/B/C qualification. Для движущегося `CALIBRATION_JOG` по-прежнему используется только `actuator_scope_mask`. Маски не передаются отдельными полями протокола — они входят в `CommissioningBundle`, хэш которого обязан совпадать на Quest и EV3; EV3 authoritative.

`CALIBRATION_JOG` разрешён только в `COMMISSIONING/CALIBRATION`, когда одновременно активны: session-local authority, полученная из физического `LOCAL_COMMISSION_ARM`, сессия role=`COMMISSIONING`, commissioning PSK, `MOTION_ENABLE=0` и остальные применимые safety predicates. UDP-команда сама по себе не может перевести EV3 в `COMMISSIONING`. Пакет содержит минимум:

```text
transaction_id
axis                    # A/B/C/D; axis обязан входить в actuator_scope_mask
signed_direction        # +1 / -1
max_encoder_delta
max_duration_ms
max_speed_counts_s
max_duty_permille
```

EV3 **не принимает из Quest целевой физический угол для `CALIBRATION_JOG`**. Он только ограниченно вращает вал выбранного мотора и прекращает движение при первом из условий: `max_encoder_delta`, `max_duration_ms`, локальное ограничение скорости или `duty`, признак препятствия/заклинивания, `LOCAL_STOP`, потеря heartbeat процесса безопасности или другая неисправность. Ограничения из пакета могут быть только строже локальных: фактический предел равен `min(requested_limit, local_engineering_limit)`, поэтому Quest не может сетевой командой увеличить разрешённые скорость, `duty`, длительность или изменение энкодера.

После управляемого плавного торможения и `BRAKE` EV3 возвращает `JOG_ACK`:

```text
transaction_id
result_code
axis
start_encoder_count
final_encoder_count
final_motor_speed
stop_reason
sample_id
```

Quest принимает `JOG_ACK`, ждёт полной остановки механики и только затем измеряет новый физический угол или раскрытие по QR. Exact retry `CALIBRATION_JOG` допустим только внутри той же session по общим transaction rules и возвращает сохранённый `JOG_ACK` result без второго движения. Если `JOG_ACK` не получен и session прекращена, Quest помечает шаг `OUTCOME_UNKNOWN` и **не replay-ит старый jog** после reconnect: требуется новый физический `LOCAL_COMMISSION_ARM`, новая commissioning session, подтверждённая stationary condition, новый `CALIBRATION_QUERY`/encoder snapshot и QR-наблюдение фактической позы; только затем рассчитывается следующий bounded jog от реально наблюдаемого состояния. `COMMISSIONING_SAMPLE` содержит согласованную пару `sample_id + encoder_count + physical_value/q_qr/jaw_opening + direction + QR quality` для журнала процедуры. Это сериализованная state-changing transaction: после durable принятия/пометки `sample_id` использованным EV3 возвращает `CONTROL_ACK(operation_type=COMMISSIONING_SAMPLE)`; exact retry того же `transaction_id+payload` в той же session обязан получить тот же ACK payload/result без повторной записи/повторного consume `sample_id`, но с новым response header sequence/timestamp/HMAC. Quest не использует sample как доказательство принятого commissioning evidence до успешного ACK. Если session потеряна после возможного принятия sample без полученного ACK, старый sample не автоматически replay-ится: новая commissioning session получает новый snapshot/sample evidence и продолжает процедуру от наблюдаемого состояния. Расчёт `DriveCalibration` выполняется на Quest/PC, а не в 50-Hz цикле EV3.

После проверки на независимых контрольных положениях Quest передаёт `SET_DRIVE_CALIBRATION`. Полезная часть содержит `transaction_id`, хэш применимой `RobotGeometry`, новую редакцию/хэш калибровки, измеренные параметры и метрики проверки. Для Gripper передаются две ограниченные по размеру монотонные таблицы `(d_counts, opening_mm)` — для открытия и закрытия — плюс calibration-session closed anchor, signed safety-owned open travel `gripper_open_limit_delta_counts`, QR-измеренный safe-open endpoint и люфт. Wire-поле `gripper_open_limit_delta_counts` здесь является **validation echo** текущего authoritative `SafetyEnvelope`: транзакция обязана совпасть с ним byte-for-value и не может расширить/заменить safety bound; persistent `DriveCalibration[D]` не получает отдельный independently mutable hard-limit field. Число узлов таблицы фиксируется схемой протокола и выбирается минимальным, достаточным для прохождения ошибки [Метрики и анализ §4.6](metrics-and-logs.md#sec-9-14); произвольный неограниченный массив в пакет не допускается.

`SET_DRIVE_CALIBRATION` сохраняет **только calibration subset active scope**. Fixed wire payload остаётся прежним: значения осей вне scope обязаны быть каноническими нулями и не валидируются как физическая калибровка. В gripper-only scope `0x08` учитываются поля D/curves/validation[D], а A/B/C игнорируются. `robot_geometry_hash` при этом относится к qualification bundle, содержащему как минимум версионированную gripper geometry (`JAW_* → contact` transforms); полная геометрия роборуки не требуется и такой bundle не разрешает `READY`.

EV3 принимает `SET_DRIVE_CALIBRATION` только при `MOTION_ENABLE=0`, полностью остановленных **всех физически обнаруженных моторах**, инженерном состоянии калибровки, совпавшей применимой `RobotGeometry`, корректном active scope и отсутствии неисправности безопасности. Он проверяет конечность и допустимость чисел, schema/ranges/монотонность таблиц, записывает candidate через временный файл + `fsync` + атомарное переименование и только после успешного повторного чтения возвращает `DRIVE_CALIBRATION_ACK`. Неуспешная транзакция не повреждает последнюю подтверждённую `DriveCalibration`.

Успешный `SET_DRIVE_CALIBRATION` **создаёт новую `CommissioningBundle` revision**, а не редактирует активный bundle «на месте». Для этой сериализованной transaction обе стороны детерминированно используют `new_bundle_revision = previous_bundle_revision + 1`; переполнение/неожиданный revision gap является config error. **До отправки** Quest durable-сохраняет `pending_candidate={old_bundle_hash,candidate_bundle_hash,candidate_drive_hash,transaction_id}`. EV3 атомарно формирует candidate bundle из новой revision, текущих неизменённых semantic components + принятого `DriveCalibration`, canonicalize по JCS и только затем активирует новый `commissioning_bundle_hash`.

Поскольку transport UDP, commit и получение ACK разделены. После commit EV3 переводит session в `CONFIG_STALE_ACK_ONLY`: actuator authority=0, но в bounded `config_commit_ack_grace_ms` принимает только exact retry последней committed state-changing transaction и возвращает тот же `DRIVE_CALIBRATION_ACK` payload/result, обёрнутый в новую datagram с новым outbound sequence/timestamp/HMAC; новые calibration/motion операции запрещены. После grace session закрывается. Quest после ACK либо после reconnect сверяет `HELLO_ACK.commissioning_bundle_hash`: если он равен durable pending candidate hash — pending revision атомарно становится active local bundle; если равен old hash — commit не состоялся и может быть повторён в новой commissioning session; любое третье значение является `ERR_HASH_MISMATCH`/manual reconciliation. ACK loss поэтому не может оставить Quest и EV3 в неразрешимом split-brain.

Любое принятое изменение `DriveCalibration` инвалидирует текущие `JointReference` и `GripperReference`: reference текущего запуска связан с конкретной calibration revision/hash и не переносится через её изменение. После ACK-only/reconciliation следующая reference/qualification выполняется только после нового discovery/`HELLO` уже с активной revision.

`SET_JOINT_REFERENCE` содержит `transaction_id`, хэш `DriveCalibration`, `sample_id`, `q_qr[3]`, `jaw_opening_qr_mm` и соответствующий атомарный снимок энкодеров A/B/C/D. EV3 принимает привязку только для текущего запуска, exact current `sample_id`/`controller_boot_id`, совместимой конфигурации и полей, требуемых `safety_observation_mask`; отвечает `REFERENCE_ACK` с вычисленными `q_actual`, `grip_actual` и reference flags. Если `REFERENCE_ACK` потерян и session затем прекращена, Quest не предполагает успех по возможному side effect: после нового `HELLO` выполняются новый stationary `CALIBRATION_QUERY`, свежая QR-observation и новый `SET_JOINT_REFERENCE` с новым transaction id. Существующая controller-side reference может быть безопасно заменена свежей; stale UI/cache не является evidence. Этот recovery path обязателен для MANUAL regression.

Reference-domain определяется **`safety_observation_mask`**:

- network-only `0x00`: A/B/C/D поля canonical zero/`N_A`, обе reference false;
- gripper-only `0x08`: Quest передаёт `q_qr[3]=0`, `raw_encoder_count[A/B/C]=0`; EV3 проверяет JAW gap + D и устанавливает только `GripperReference` (`JOINT_REFERENCE_VALID=0`, `GRIPPER_REFERENCE_VALID=1`);
- partial A/B/C `ACTUATOR_QUALIFICATION`: safety-observation обязана включать все A/B/C; Quest передаёт реальные `q_qr[3]` и raw A/B/C из **одного** snapshot, EV3 устанавливает `JointReference A/B/C` независимо от того, какая их часть находится в `actuator_scope_mask`. Если D не safety-observed, D/jaw fields canonical `N_A`; если D наблюдаем — дополнительно создаётся `GripperReference`;
- полный Release `0x0F`: создаются полные A/B/C/D references.

Motor-disabled safety-observed axis поэтому никогда не получает motor authority, но её реальная reference доступна `JointSafeSet`.

`FAULT_ACK` принимается только для текущего latched `fault_code`, когда причина объективно устранена и fault class не требует незавершённого maintenance. ACK очищает fault latch, но не снимает отдельный `LOCAL_STOP` stop latch и никогда не armed motion. После очистки последнего blocking latch recovery state выбирается по тем же правилам ниже.

`RESET_STOPPED` принимается только когда физический `LOCAL_STOP` уже released, **все физически обнаруженные моторы stationary**, нет unresolved maintenance-required fault и operation transaction новая. Успех снимает только local-stop latch, не очищает независимый fault latch, не вооружает движение и не восстанавливает session-local commissioning authority: после очистки всех blocking latch при живой CONTROL session следующий state выбирается между `HOLD`/`CONNECTED_UNREFERENCED` по reference, а после бывшей commissioning session — `DISCOVERY`.

`SET_PAYLOAD_PROFILE` выбирает только установленный в active `CommissioningBundle` профиль **вместе с его `JointSafeSet`**. В `qualification_only=false` profile обязан быть покрыт active `QualificationEvidenceManifest`; в `qualification_only=true` допускается только candidate profile, разрешённый engineering scope [§2.5](#sec-4-7-5), и его использование само по себе не делает profile production-qualified. После boot active profile=`UNSELECTED` (reserved runtime sentinel, не допустимый ID установленного PayloadProfile), `active_joint_safe_set_hash=0`. Startup-вызов `SET_PAYLOAD_PROFILE` разрешён также в `ROBOT_CALIBRATION` **только после принятой полной JointReference/RobotLocalization**, при `MOTION_ENABLE=0`, stationary A/B/C/D и отсутствии latched fault; успешный ACK является первым payload gate перехода в `READY`. Во время эксплуатации смена профиля остаётся разрешённой только в `READY/HOLD` при тех же stationary условиях. `SET_PAYLOAD_STATE` содержит `transaction_id + profile_id + payload_state + payload_confirmation_nonce`; startup-подтверждение `EMPTY/LOADED` разрешено в `ROBOT_CALIBRATION` только **после** успешного выбора profile, при полной reference/localization, stationary A/B/C/D, `MOTION_ENABLE=0` и отсутствии latched fault. В эксплуатации операция разрешена только в `READY/HOLD`. Успешный startup ACK `SET_PAYLOAD_STATE` является вторым payload gate, и `ROBOT_CALIBRATION→READY` запрещён при `PayloadState=UNKNOWN`. В production CONTROL `payload_confirmation_nonce` генерируется Quest CSPRNG только после явного подтверждения оператора. В `COMMISSIONING/ACTUATOR_QUALIFICATION` MANUAL nonce генерируется авторизованным case runner после того, как исходный payload state задан и проверен fixture/case prerequisite **до запуска соответствующего motion segment**; дополнительное действие человека после старта AUTO-case не требуется и запрещено [План проверки §6.2](test-plan.md#sec-9-23). Nonce служит только audit/correlation evidence, не заменяет HMAC/session/state authorization, а exact retry той же transaction обязан повторять тот же nonce. До ACK нового профиля EV3 загружает/валидирует его safe-set вне 50-Hz loop и атомарно меняет active profile+safe-set; при отсутствии/несовпадении hash операция отклоняется `FAULT_PAYLOAD_PROFILE`.

Смена профиля всегда устанавливает runtime `PayloadState=UNKNOWN` и очищает armed-latch. `UNSELECTED` нельзя передать через `SET_PAYLOAD_PROFILE`; это только локальный startup sentinel. После controller continuity loss ранее активный profile/safe-set не используется как authoritative без нового startup selection. `SET_PAYLOAD_STATE` от оператора принимает только `EMPTY` или `LOADED`; `UNKNOWN` устанавливается системой и не является операторской командой. `LOADED` отклоняется, если выбран профиль `EMPTY` или отсутствует совместимый installed PayloadProfile/JointSafeSet. Для подхода к ожидаемому предмету оператор выбирает non-empty profile, затем при stationary `READY/HOLD` явно подтверждает текущий пустой захват как `EMPTY`; с этого момента уже действуют консервативные limits/safe-set выбранного profile. После подтверждённого object/early contact [Спецификация EV3 §15.3](ev3-specification.md#sec-7-15-3) state снова становится `UNKNOWN` и A/B/C остаются в `HOLD` до явного `LOADED` либо release→`EMPTY`. После boot/controller continuity loss payload state также `UNKNOWN`; автоматический optimistic `EMPTY` запрещён.

`SET_PAYLOAD_PROFILE`/`SET_PAYLOAD_STATE` имеют отдельную fail-closed engineering semantics и **никогда не превращают `COMMISSIONING` в product `READY/HOLD`**:

- gripper-only `actuator_scope_mask=0x08`: обе операции недоступны; этапы 4–5 квалифицируют D без payload profile/state;
- narrow A/B/C qualification (`actuator_scope_mask` является строгим подмножеством `0x07` либо `0x0F`, но содержит A/B/C): после полной `JointReference A/B/C`, выбранного installed `EMPTY` profile+matching EMPTY `JointSafeSet`, stationary всех safety-observed/motor-authorized осей, `MOTION_ENABLE=0`, локальной commissioning authority и снятого qualification arm разрешается только `SET_PAYLOAD_PROFILE=EMPTY` и `SET_PAYLOAD_STATE=EMPTY`. `LOADED`, non-empty profile, pickup/contact-as-payload и release cases отклоняются `ERR_STATE`;
- full `actuator_scope_mask=safety_observation_mask=0x0F` qualification-only: при валидных A/B/C/D references, stationary A/B/C/D, active commissioning role/local authority, `MOTION_ENABLE=0`, qualification armed-latch=false и отсутствии fault разрешается выбирать установленный квалифицируемый PayloadProfile и подтверждать `EMPTY/LOADED`. Это используется **только** для MANUAL payload/contact/release evidence до promotion production bundle.

Любой успешный engineering profile/state transition инвалидирует moving target, очищает `release_seen/armed-latch` и требует нового OFF/HOLD→rising edge перед следующим qualification motion. Если ACK payload operation потерян и session затем исчезла, новая session не наследует операторское подтверждение как authority: tooling заново сверяет telemetry/profile hashes и повторяет безопасную явную selection/confirmation transaction перед motion; старый transaction id не переносится.

<a id="sec-4-7-6"></a>
### 2.6. `COMMAND`

Exact `COMMAND` field order/types/reserved bytes и numeric bit positions задаются
`protocol/wire_schema.yaml`/generated `docs/protocol-wire-reference.md`.

Behavioral fields, используемые control semantics: `motion_flags`, `q_base_rad`,
`q_shoulder_rad`, `q_elbow_rad`, `grip_intent`; reserved fields всегда проходят
schema-generated canonical-zero validation. `motion_flags` использует symbolic flags
`MOTION_ENABLE`, `HOLD_REQUEST`, `TRACKING_VALID`, `GRASP_VALID`.

В полном `TRACKING` валидное движение требует `MOTION_ENABLE=1`, `HOLD_REQUEST=0`, `TRACKING_VALID=1`; при включённом D дополнительно требуется `GRASP_VALID=1` для изменения gripper target.

В `COMMISSIONING/ACTUATOR_QUALIFICATION` тот же wire `COMMAND` используется без отдельного gripper-протокола. EV3 исполняет **только** поля приводов active `actuator_scope_mask`. Для gripper-only `0x08` поля `q_base/q_shoulder/q_elbow` обязаны быть finite и канонически равны `0`, но не участвуют в actuator path; требуются `MOTION_ENABLE=1`, `HOLD_REQUEST=0`, `TRACKING_VALID=1`, `GRASP_VALID=1`. Здесь `TRACKING_VALID` означает валидность input stack, требуемого active scope, и не подразумевает Body Shoulder/Wrist.

Stop-like `COMMAND` с `MOTION_ENABLE=0` **или** `HOLD_REQUEST=1` всегда обрабатывается fail-safe раньше movement predicates и не требует `TRACKING_VALID`/`GRASP_VALID` для снятия разрешения. Но deliberate-release latch имеет более строгий canonical contract: `release_seen=true` устанавливается **только** после валидного release OFF/HOLD packet с `MOTION_ENABLE=0 && HOLD_REQUEST=1`; противоречивый `MOTION_ENABLE=1,HOLD_REQUEST=1` обязан остановить/удержать, но не может сам по себе доказать release или вооружить следующий edge. **Для любой motion-capable CONTROL/COMMISSIONING session** EV3 держит session-local `release_seen` и `last_motion_enable`: при новой session, входе в `SAFE_HOLD`, **входе в `STOPPED` по `LOCAL_STOP` или latched fault**, STOP/fault recovery, reference-space/lifecycle invalidation, bundle/profile change и иных arm-invalidating events `release_seen=false`, `last_motion_enable=false`. Канонический release OFF/HOLD packet устанавливает `release_seen=true`; первый последующий moving packet допускается только как новый false→true enable edge при `release_seen=true`, после чего обычные scope/input predicates снова обязательны. Quest при deliberate re-arm запоминает sequence первого/актуального release OFF/HOLD как `release_off_sequence` и **не** устанавливает локальный `armed=true`, пока свежая `TELEMETRY` текущей session/boot не покажет `last_accepted_command_sequence >= release_off_sequence`. До подтверждения он может повторять bounded priority OFF/HOLD по обычному sender/rate-limit policy, но moving packet запрещён. Потеря telemetry/session/boot до подтверждения оставляет dearmed. Поэтому retained/replayed `MOTION_ENABLE=1` после reconnect/recovery сам по себе не может возобновить motion.

Все float-поля проверяются на finite и допустимый протокольный диапазон. Ось вне scope всегда hard-inhibited локально независимо от содержимого пакета.

<a id="sec-4-7-7"></a>
### 2.7. Принятие команды

Общие условия:

```text
HMAC valid
session binding (включая expected robot_id)/controller_boot valid
sequence > last_accepted_sequence
нет latched fault
numeric fields valid
CommissioningBundle/profile hash compatible
```

Далее применяется state/scope gate:

```text
если state == TRACKING:
    qualification_only == false
    actuator_scope_mask == 0x0F
    JointReference A/B/C valid
    GripperReference valid, если D участвует
    full DriveCalibration/RobotGeometry/JointSafeSet valid
    active PayloadProfile + matching JointSafeSet valid
    PayloadState in {EMPTY, LOADED}; UNKNOWN никогда не допускает A/B/C motion
    PayloadState=LOADED допустим только с non-empty active PayloadProfile

если state == COMMISSIONING и phase == ACTUATOR_QUALIFICATION:
    session role == COMMISSIONING
    qualification_only == true
    local qualification confirmation current
    requested fields outside actuator_scope_mask never execute
    calibration/reference valid для всех motor-authorized приводов и всех осей из safety_observation_mask
    actuator_scope_mask & ~safety_observation_mask == 0
    если scope == 0x08:
        GripperReference + DriveCalibration[D] valid
        JointReference/RobotLocalization/JointSafeSet не требуются
    если actuator_scope включает A/B/C:
        safety_observation_mask обязан включать все A/B/C + каждый motor-authorized bit
        это допускается только после полной RobotGeometry + DriveCalibration + JointReference A/B/C + применимого profile-specific JointSafeSet + pre-motion gates этапа 9
        narrow scope: active PayloadProfile/State обязаны быть EMPTY/EMPTY
        full 0x0F qualification-only: PayloadState in {EMPTY, LOADED}, LOADED только с совместимым non-empty profile/safe-set
        сам движущийся MANUAL case является результатом qualification, а не её prerequisite
```

Таким образом `JointReference` не является глобальным prerequisite Motor D, что согласуется с инвариантами S6/S7. Любая несовместимость scope или попытка задействовать disabled axis отклоняется без motor write и журналируется.

Порядок допуска A/B/C и постепенного расширения scope определён в
[Этапах реализации §11](implementation-stages.md#sec-10-11), проверки — в
[Плане проверки §4.7.7](metrics-and-logs.md#sec-9-15-7) и
[Плане проверки §7](test-plan.md#sec-9-26).

<a id="sec-4-7-8"></a>
### 2.8. `TELEMETRY`

`TELEMETRY` передаёт состояние EV3, фактическое положение, подтверждение принятой
команды и данные watchdog. Состав и типы полей определены в
[`docs/protocol-wire-reference.md`](protocol-wire-reference.md), генерируемом из wire schema.
Здесь определены правила интерпретации этих полей.

В `qualification_only` profile значения `q_actual/q_speed` передаются реальными только для осей из `safety_observation_mask`; оси вне этой маски имеют canonical zero/`N_A`. Поэтому при partial A/B/C `ACTUATOR_QUALIFICATION` неподвижная ось без motor authority всё равно может иметь реальный `q_actual`, если она требуется coupled-safety. Quest знает обе маски из локального `CommissioningBundle`, совпадение которого доказано `commissioning_bundle_hash`; отдельные wire-поля масок не вводятся. `safety_observation_mask` не расширяет motor authority. Все motor writes по-прежнему hard-inhibited вне `actuator_scope_mask`.

До startup profile selection поле `active_payload_profile_id` в EV3→Quest `TELEMETRY` нормативно содержит reserved runtime sentinel ASCII `UNSELECTED` в `id32`, `active_joint_safe_set_hash` состоит из 32 нулевых байт, а `status_flags.payload_profile_valid=0` и `status_flags.active_joint_safe_set_valid=0`; в таком состоянии `ROBOT_CALIBRATION→READY` запрещён. `UNSELECTED` допустим только как EV3→Quest runtime sentinel и никогда не является установленным `PayloadProfile`/допустимым аргументом `SET_PAYLOAD_PROFILE`. После успешного выбора profile telemetry обязана отражать его canonical installed ID и ненулевой совместимый safe-set hash.

`incident_id` равен нулю/пустому значению при отсутствии активного инцидента и содержит текущий корреляционный ID при latched fault/incident package.

`last_accepted_command_sequence` — наибольший wire `sequence` **принятого `COMMAND` текущей session**, включая OFF/HOLD `COMMAND`; rejected/malformed/auth-failed packets его не изменяют. `command_age_ms` — возраст по EV3 monotonic receive time последнего принятого `COMMAND` текущей session, также включая OFF/HOLD. Эти поля не являются общим ACK произвольных transaction messages, но нормативно используются Quest для подтверждения deliberate release-handshake: свежая telemetry с тем же boot/session context и `last_accepted_command_sequence >= release_off_sequence` доказывает, что соответствующий OFF/HOLD дошёл до command acceptance path. После новой session acceptance-context начинается заново и старое подтверждение не переносится.

Wire `state` по-прежнему остаётся `COMMISSIONING`, но active subphase должна быть наблюдаема: `TELEMETRY.status_flags.commissioning_actuator_qualification_active`. Бит устанавливается **только EV3** после успешного локального `ENTER` и всех qualification prerequisites и сбрасывается при reconnect/session loss, `LOCAL_STOP`, fault или выходе из phase. Quest может показывать собственный workflow-state, но разрешает qualification UI/moving command только когда видит authoritative `commissioning_actuator_qualification_active` flag в свежей telemetry; UI-state сам по себе actuator authority не создаёт.

`status_flags` bit layout v1 задан `protocol/wire_schema.yaml` и generated `docs/protocol-wire-reference.md` согласно [§4](#sec-11-8) и включает `joint_reference_valid`, `gripper_reference_valid`, `commissioning_bundle_valid`, `local_stop_active`, `safety_supervisor_alive`, `grasp_contact`, `battery_derated`, `payload_profile_valid`, `active_joint_safe_set_valid` и authoritative `commissioning_actuator_qualification_active`; остальные reserved bits остаются нулевыми.

`loop_health_flags` сообщает нормальное состояние или факт недавнего overrun без передачи полного массива диагностических timing-счётчиков.

Поля `raw_encoder_count`, `q_ref`, `duty_permille`, детальные временные показатели цикла, счётчики парсера и измерения инженерной калибровки относятся к `DIAGNOSTIC_TELEMETRY` и не должны постоянно передаваться в штатном `Release`-режиме.

<a id="sec-11-2"></a>
## 3. Семантика состояний и ошибок

Exact numeric values `TELEMETRY.state` и `TELEMETRY.fault_code` принадлежат
`protocol/wire_schema.yaml` и generated `docs/protocol-wire-reference.md`; здесь они намеренно не
дублируются.

Переходы состояний описаны в [Архитектура системы §5](system-architecture.md#sec-4-3);
перечни wire symbols генерируются в [protocol.md](protocol-wire-reference.md).

Отдельного wire-state `FAULT` нет. Schema-defined no-fault value означает отсутствие latched
fault; любой активный fault принудительно сочетается с `state=STOPPED` до recovery. UI может
отображать это как `FAULT/ОШИБКА`.

Legacy symbol `FAULT_CONTROLLER_PROCESS` в v1 покрывает потерю любого обязательного
process-liveness peer пары `phantom-controller`/`phantom-safety`; structured event
`axis_or_subsystem`/`event_code` обязан различать `CONTROLLER` и `SAFETY`. Оба случая используют этот wire fault symbol.


<a id="sec-11-8"></a>
## 4. Нормативный wire contract protocol v1 — source ownership and generation gate

Exact byte layout, offsets, payload sizes and numeric enum/bit definitions, которые представимы
в schema, **не дублируются вручную в этом файле**. Контекстные ranges/transition guards
остаются нормативными в owning prose. Production serializers/deserializers могут быть
hand-written, но не являются отдельным source of truth.

Authoritative protocol identity sources:

1. `protocol/wire_schema.yaml` — machine-readable wire structure source;
2. `protocol/semantics.yaml` — machine-readable cross-runtime behavioral contract;
3. generated `wire_schema.structural.json`, `protocol_semantics.canonical.json` and
   `protocol_contract.canonical.json` — RFC 8785 JCS identity inputs;
4. `docs/protocol-wire-reference.md` — generated human-readable mirror;
5. generated C++/C# constants/size maps/compile-time definitions;
6. `protocol/golden_vectors/v1.json` — cross-language wire fixtures.

If generated artifacts disagree with `wire_schema.yaml`, CI must fail. If behavioral prose in
this document disagrees with the machine schema, the change is incomplete: resolve the
semantic disagreement deliberately before release; do not silently pick whichever side makes
a test pass.

After changing structure or semantics, run at minimum:

```powershell
python tools/protocolgen.py
python tools/protocolgen.py --check
python tools/test_protocol.py
```

A semantic protocol change must first update `protocol/semantics.yaml`, relevant
tests/evidence and the owning normative prose. Documentation checks run separately from BUILD.


Для `SET_DRIVE_CALIBRATION` дополнительно обязательно: `gripper_open_limit_delta_counts != 0 && != INT32_MIN`; его значение **в точности** совпадает с authoritative `SafetyEnvelope`; `D_open_counts=abs(value)` помещается в configured/MANUAL-qualified bound; все используемые `CurveNode.delta_encoder` находятся в `[0,D_open_counts]`, строго возрастают по `d_counts`, endpoint nodes покрывают `0` и `D_open_counts`, а `opening_mm` монотонен с допуском schema. Calibration-session `gripper_e_closed` не превращается в persistent runtime hard limit.

Для всех `f32` приёмник обязан проверить `isfinite`; диапазоны определяются schema и active `CommissioningBundle`. `DIAGNOSTIC_TELEMETRY` не расширяет actuator authority. `payload_length` обязан **точно** совпадать с указанной длиной; variable-length payload v1 отсутствуют. Для gripper curves длина остаётся fixed 16+16 узлов, а реальные counts задают число используемых элементов — это исключает allocator/parser ambiguity.

`actuator_scope_mask` и `safety_observation_mask` намеренно **не добавляются в v1 datagram layouts**: обе являются частью versioned `CommissioningBundle`, а стороны обязаны сверять `commissioning_bundle_hash`. `actuator_scope_mask` определяет motor-write authority; `safety_observation_mask` — какие реальные encoder/reference values необходимы safety logic. Поэтому в partial A/B/C qualification `q_actual/q_speed` safety-observed, но motor-disabled осей **не** канонизируются в zero; zero/`N_A` используется только вне `safety_observation_mask`. `COMMAND` fields вне motor authority не исполняются; effective coupled-safety target строится EV3 с fixed локальными coordinates этих осей ([Спецификация EV3 §16](ev3-specification.md#sec-7-16)). Fixed payload lengths остаются неизменными.

`protocol_minor=0` сам по себе не является доказательством compatibility внутри pre-release
v1. `protocol_schema_hash` идентифицирует только бинарную структуру; переименование поля без
изменения layout не меняет его. `protocol_semantics_hash` идентифицирует machine-readable
behavioral contract. Authoritative compatibility identity — exact
`protocol_contract_hash=SHA-256(JCS({protocol_schema_hash,protocol_semantics_hash}))`, который
передаётся в schema-defined compatibility поле `HELLO_ACK` и проверяется до actuator
authority. Изменение layout меняет schema и contract hashes; изменение semantics при том же
layout меняет semantics и contract hashes. Любое несовпадение contract hash fail-closed;
старый client не может продолжить motion только потому, что major/minor или payload length
совпали.

<a id="sec-protocol-specification-4-1"></a>
### 4.1. Schema/code-generation gate

CI обязан:

1. parse `wire_schema.yaml` → deterministic structural projection → RFC 8785 JCS `wire_schema.structural.json`; отдельно canonicalize `semantics.yaml` и сформировать contract object из обоих hashes;
2. сгенерировать C++14/C# constants/size maps, все три identity constants/canonical artifacts и compile-time size assertions; hand-written production codecs скомпилировать против этих definitions;
3. выполнить cross-codec golden-vector decode/round-trip для каждого message type и отдельные semantic/negative vectors для каждого enum/error path;
4. проверить corrupted length/reserved/NaN/Inf/endian/HMAC/fuzz cases;

5. проверить machine-readable extractor-ом, что generated `docs/protocol-wire-reference.md`, constants/size maps и golden vectors соответствуют текущему `wire_schema.yaml`; [§4](#sec-11-8) проверяет ownership/generation policy, а hand-written PHANTOM prose не содержит competing exact wire tables.
