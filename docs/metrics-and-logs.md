<a id="sec-metrics-and-logs"></a>
# PHANTOM — метрики, журналы и анализ

Сбор диагностических данных при обычной работе, калибровке и тестировании.
Документ задаёт требуемое поведение; реализованное покрытие — в [current-status.md](current-status.md).

<!-- BEGIN GENERATED TOC -->
<details>
<summary>Оглавление</summary>

- [1. Когда и что собирается](#sec-metrics-collection)
- [2. Журналы и инциденты](#sec-metrics-logging)
  - [2.1. Хранение и целостность](#sec-8-13)
    - [2.1.1. Release](#sec-8-13-1)
    - [2.1.2. Diagnostic](#sec-8-13-2)
    - [2.1.3. Ротация и целостность](#sec-8-13-3)
  - [2.2. Наблюдаемые показатели](#sec-8-14)
  - [2.3. Структурированные события](#sec-metrics-event-format)
  - [2.4. Данные EV3 FlightRecorder](#sec-metrics-flight-records)
  - [2.5. Аварийное событие phantom-safety](#sec-metrics-safety-events)
  - [2.6. Контекст инцидента на Quest](#sec-metrics-quest-incidents)
  - [2.7. Снимок состояния сетевой службы EV3](#sec-metrics-network-status)
- [3. Автоматический анализ и доступность измерений](#sec-test-plan-manual-criteria)
- [4. Метрики и критерии отклонений](#sec-metrics-thresholds)
  - [4.1. Отслеживание плеча и кисти, измерение длины руки](#sec-9-6)
  - [4.2. Локализация QR](#sec-9-10)
  - [4.3. Инженерная калибровка RobotGeometry](#sec-9-11)
  - [4.4. Инженерная калибровка `DriveCalibration` Base/Shoulder/Elbow](#sec-9-12)
  - [4.5. QR→энкодерная `JointReference` при запуске](#sec-9-13)
  - [4.6. Калибровка и проверка захвата по QR](#sec-9-14)
  - [4.7. Механические характеристики](#sec-9-15)
    - [4.7.1. Соосность](#sec-9-15-1)
    - [4.7.2. Shoulder HOLD](#sec-9-15-2)
    - [4.7.3. Безопасные границы](#sec-9-15-3)
    - [4.7.4. Слежение суставов](#sec-9-15-4)
    - [4.7.5. Повторяемость TCP](#sec-9-15-5)
    - [4.7.6. Потеря питания и независимый POWER_CUT](#sec-9-15-6)
    - [4.7.7. JointSafeSet, coupled collision и проверка пути](#sec-9-15-7)
  - [4.8. Защита моторов](#sec-9-16)
    - [4.8.1. Препятствие и заклинивание основных суставов](#sec-9-16-1)
    - [4.8.2. Реверс и выбор люфта](#sec-9-16-2)
    - [4.8.3. Длительная нагрузка / `MotorStressScore`](#sec-9-16-3)
    - [4.8.4. Перегрузка при удержании](#sec-9-16-4)
    - [4.8.5. Контакт и заклинивание захвата](#sec-9-16-6)
  - [4.9. EV3: физические критерии, временной бюджет и ресурсы](#sec-9-17)
  - [4.10. Реальные задержки защиты EV3](#sec-9-19)
  - [4.11. Сквозной тест повторения движения руки](#sec-9-20)
  - [4.12. Производительность Quest](#sec-9-22)
- [5. Автоматические отчёты](#sec-9-1-8)
- [6. Приложение: автоматическая связь с требованиями](#sec-9-25)
  - [6.1. Критерии продукта и процедуры](#sec-test-plan-25-1)
  - [6.2. Требования и владельцы](#sec-test-plan-25-2)
  - [6.3. Проверка ссылок](#sec-test-plan-25-3)

</details>
<!-- END GENERATED TOC -->

<a id="sec-metrics-collection"></a>
## 1. Когда и что собирается

Данные собираются при обычной работе приложения и EV3, а не только во время тестов.

| Профиль | Сбор и запись |
|---|---|
| Релизный (`Release`) | Обязательные state/safety/error events и низкочастотные summaries; bounded FlightRecorder сохраняется при инциденте. Постоянные DEBUG-логи и подробная траектория выключены |
| Отладочный (`Diagnostic`) | Всё обязательное плюс расширенные tracking/encoder/network counters и инженерные данные при явном включении; ограниченные частота/объём и индикатор записи |

Runtime safety и контроль лимитов работают в обоих основных профилях. Доступность данных
для последующего p95/p99 анализа зависит от включённой записи и достаточности samples.
Release не должен включать постоянную подробную запись ради анализа метрик.
Границы профилей — [engineering.md](engineering.md#sec-engineering-build-profiles).

<a id="sec-metrics-logging"></a>
## 2. Журналы и инциденты

События связываются с временем, компонентом, session/incident и identity комплекта.
FlightRecorder хранит ограниченный контекст входов/реакций вокруг сбоя. Ошибка записи,
rotation или экспорта не задерживает control loop и защиту; фиксируется LOG_STORAGE_DEGRADED.
При внезапной потере питания данные, не успевшие записаться, не восстанавливаются выдуманными
значениями; незавершённое завершение обнаруживается при следующем boot.

Нельзя записывать secrets, passthrough image/video и запрещённую подробную историю.
Расширенная Diagnostic запись включается явно и показывает индикатор.
Требования к неблокирующему logger EV3 — [EV3 §20](ev3-specification.md#sec-7-20).
Форматы [событий](#sec-metrics-event-format), [FlightRecorder](#sec-metrics-flight-records),
[контекст Quest](#sec-metrics-quest-incidents) и [сетевой snapshot](#sec-metrics-network-status)
определены ниже.

<a id="sec-8-13"></a>
### 2.1. Хранение и целостность

<a id="sec-8-13-1"></a>
#### 2.1.1. Release

Обычные локальные журнал событий и incident packages хранятся до первого ограничения:

```text
7 суток
или
250 MB
```

Incident package содержит metadata/event log и сохранённый FlightRecorder вокруг конкретного сбоя. Passthrough image/video не сохраняются.

<a id="sec-8-13-2"></a>
#### 2.1.2. Diagnostic

Расширенные логи имеют отдельную rotation policy и могут занимать больший лимит, заданный engineering config. Запись частой XR/motor telemetry включается явно и имеет видимый индикатор диагностической записи.

<a id="sec-8-13-3"></a>
#### 2.1.3. Ротация и целостность

- сначала удаляются наиболее давние non-incident diagnostic files;
- затем обычные журнал событий вне retention window;
- incident package не должен удаляться раньше минимального retention срока, если есть место для безопасной работы системы;
- запись выполняется через temporary file + atomic rename, где это применимо;
- при старте controller создаётся маленький `runtime-active` маркер, удаляемый только при корректном shutdown; если маркер найден после следующего boot, создаётся `UNCLEAN_SHUTDOWN` event, что позволяет зафиксировать power loss/process termination даже когда предыдущий процесс физически не успел записать fault;
- неполный файл после power loss распознаётся при следующем запуск и помечается как incomplete;
- ошибка удаления/записи не влияет на цикл управления моторами и приводит к `LOG_STORAGE_DEGRADED` telemetry/event при первой возможности.

<a id="sec-8-14"></a>
### 2.2. Наблюдаемые показатели

Quest Diagnostic UI может показывать:

```text
state / fault
service discovery status / current endpoint
RTT p50/p95/p99
packet loss / telemetry age
q_target / q_actual
QR visibility and residuals
workspace projection count
Body_RightShoulder/Wrist tracking quality/status and age
human_arm_reach calibration quality
tracking loss/dropout counters
XR CPU/GPU frame time / dropped frames / app refresh target
managed allocation / GC counters в frame-critical path
auth failure counters
incident/log storage status
```

EV3 Diagnostic измеряет:

```text
loop dt p50/p95/p99/max
loop overruns
command age
accepted/dropped/auth-failed packets
raw encoder / q_ref / q_actual error
duty saturation time
stall candidates
motor stress / high-duty time
backlash take-up state
LOCAL_STOP state
fault counters
battery voltage
process CPU time / RSS
RX/telemetry/logger queue high-water marks
log drops
```

В `Release` наружу выводятся только агрегированные/критические subset, необходимый для эксплуатации.

<a id="sec-metrics-event-format"></a>
### 2.3. Структурированные события

Каждое существенное событие получает фиксированную структуру:

```text
monotonic_us
wall_time_if_valid
incident_id
session_id
controller_boot_id
build_id
commissioning_bundle_hash
active_joint_safe_set_hash
robot_geometry_hash
drive_calibration_hash
state_before
state_after
event_code
axis_or_subsystem
command_sequence
human_readable_context_id
```

Для motor/safety events snapshots различают authority и observation: full A/B/C — `q_target/q_ref/q_actual`, speed/duty; partial A/B/C qualification — реальные encoder/`q_actual` всех safety-observed A/B/C плюс target/duty только motor-authorized subset; gripper-only — D encoder/speed/duty и gripper FSM/target/actual; network-only motor snapshot не выдумывается. Battery и временные показатели цикла сохраняются во всех профилях.

События, которые обязательно логируются:

- запуск/штатное завершение и unclean previous shutdown;
- все state transitions;
- latched fault condition (`STOPPED + fault_code`), `STOPPED`, `SAFE_HOLD` с причиной;
- `OBSTRUCTION_CANDIDATE`, stall, motor overload/stress derating;
- `LOCAL_STOP`;
- watchdog timeout/переподключение;
- controller/safety process loss;
- превышение периода цикла/временной предел anomaly;
- calibration/reference success/rejection с quality metrics;
- config/hash incompatibility;
- `WIFI_AVAILABLE`, `WIFI_LOST`, `WIFI_RECOVERED`, `WIFI_RECOVERY_FAILED` без SSID credential;
- `NETWORK_READY`, `UDP_LISTENER_STARTED`, `DNS_SD_PUBLISHED`/publication failure;
- `HELLO_ACCEPTED`/`HELLO_REJECTED`, `SESSION_CREATED`/`SESSION_ENDED`, `STALE_REPLAY_REJECTED`, категоризированный `AUTH_FAILURE`, `CONTROLLER_RESTART`;
- maintenance lock / encoder discontinuity / подтверждённое механическое вмешательство;
- parser/HMAC anomaly aggregates;
- log subsystem failure.

<a id="sec-metrics-flight-records"></a>
### 2.4. Данные EV3 FlightRecorder

Даже в Release цикл управления моторами пишет **не на диск**, а в фиксированный RAM ring buffer. По умолчанию буфер хранит последние `10 s` с частотой цикла управления моторами (`50 Hz`); размер записи фиксирован и задаётся при сборке/старте.

Каждая запись содержит общий header (`monotonic_us`, active profile, `actuator_scope_mask`, `safety_observation_mask`, `state/status_flags/fault_code`, command sequence/age, battery, loop timing, safety flags) и scope-specific payload. Full A/B/C записывает raw encoders, `q_target/q_ref/q_actual/q_speed`, duty/stress и gripper. Partial A/B/C qualification сохраняет `q_actual`/raw encoder всех safety-observed A/B/C, но target/duty authority только motor-enabled осей; duty disabled осей остаётся zero. Gripper-only — D encoder/speed/duty/stress и gripper target/actual/FSM; network-only — controller/session/network counters и battery/loop health без фиктивных q. Реализация может использовать один fixed-size union/record с canonical zero для полей вне `safety_observation_mask`, но semantics обязана явно маркировать обе маски и не трактовать нули как измерения.

При incident:

```text
1. сначала выполнить safety action / BRAKE
2. atomically freeze pre-fault ring generation
3. присвоить incident_id
4. продолжить краткий post-fault capture в отдельный bounded tail buffer
5. logger thread асинхронно сохранить incident metadata + flight data
```

Цикл управления моторами никогда не ждёт завершения записи.

<a id="sec-metrics-safety-events"></a>
### 2.5. Аварийное событие phantom-safety

Если основной controller погиб/завис, `phantom-safety` после выполнения `BRAKE` обязан самостоятельно записать маленькое emergency event:

```text
controller_boot_id
last_heartbeat_monotonic_us
stop_reason
LOCAL_STOP state
motor addresses/states if readable
safety process build_id
```

Торможение имеет приоритет над файловой записью. Failure emergency log не отменяет stop action.

<a id="sec-metrics-quest-incidents"></a>
### 2.6. Контекст инцидента на Quest

Quest держит собственный короткий RAM ring buffer без изображений камер. Общие поля: profile/scope, monotonic time, state/fault, network sequence/RTT/telemetry age и correlation id. Scope-specific payload: full path — Wrist/Body_RightShoulder validity/quality/timestamps, requested/control/projected TCP и `q_target`; gripper-only — grasp validity/value, Left Grip, `grip_intent`/gripper telemetry; network-only — discovery/session/config/telemetry transitions без mandatory tracking fields.

При получении EV3 fault condition либо локальном XR/network fault Quest сохраняет ring buffer под тем же `session_id` и согласованным `incident_id`/event correlation id. Это позволяет восстановить именно применимую цепочку «input/network → command/session → EV3 response → fault» без фиктивных samples.

Для расследования качества плеча Quest сохраняет validity/quality/fidelity,
source age, временное рассогласование с Wrist, dropout/reacquire, скачки и оценки
скорости/ускорения, SDK/runtime version, qualification profile, state и Left Grip.
В Release доступны агрегаты и bounded FlightRecorder; подробный поток включается
явно в Diagnostic. Потеря tracking, нарушение sanity bounds и восстановление имеют
отдельные события. Метрики без независимого эталона не доказывают абсолютную точность.

<a id="sec-metrics-network-status"></a>
### 2.7. Снимок состояния сетевой службы EV3

Stage-3 network worker раз в секунду atomically заменяет bounded snapshot `/run/phantom/network/status.json` внутри принадлежащего `phantom-net` runtime directory. Он содержит только public profile/identity, текущий boot id, session-active flag и счётчики `rx`, `rx_drop`, `hmac_fail`, `parser_reject`, `hello_accept`, `hello_reject`, `replay_reject`, `pong`, `telemetry`, `command_scope_zero`, `motor_write_attempts_rejected`, `controller_snapshot_stale`; PSK, HMAC tags, nonce, session id и payload в файл не попадают.

<a id="sec-test-plan-manual-criteria"></a>
## 3. Автоматический анализ и доступность измерений

Во время тестов система автоматически собирает доступные метрики и события.
Ручного заполнения отчёта нет. При нарушении configured runtime limit в логи/отчёт
добавляется сообщение с метрикой, значением, порогом, временем и доступным контекстом.
Safety faults по-прежнему обрабатывает EV3; анализ не заменяет немедленную защиту.

После сессии анализ проверяет p95/p99 при достаточных валидных samples. Превышение критериев
ниже создаёт ошибку для исследования. Без эталона/данных/timestamp метрика отмечается
не измеренной; отсутствие сообщения не означает PASS. Это требуемое поведение анализа,
не утверждение, что весь анализ уже реализован.

| Источник | Что можно анализировать |
|---|---|
| Encoders, q_target/q_ref/q_actual, duty, battery, timestamps, telemetry | Ошибку относительно encoder, encoder drift при HOLD, duty/stress, cadence/latency, пропуски и faults |
| QR при калибровке/привязке | Residuals, repeatability, согласованность encoder↔QR; не независимую истинную точность |
| Независимый jig/угломер/линейка или внешняя tracking reference с известной погрешностью | Абсолютную ошибку TCP/плеча/кисти, физический люфт и смещение после передачи |
| Пользователь | Видимые скачки, проседание и неудобство UI/haptics, без численного p95 |

Сбор данных с эталоном выполняется при инженерной настройке/расследовании.
Обычная сессия не может сама вычислить истинную ошибку плеча: для p95 требуется независимое
реальное положение плеча. Собственная tracking-оценка не заменяет эталон.

<a id="sec-metrics-thresholds"></a>
## 4. Метрики и критерии отклонений

Пороги ниже применяются только к измерениям с указанным источником и условиями.
Невыполненный сбор или отсутствие независимого эталона означает «не измерено», не PASS.
Инженерная настройка и подготовка физического опыта соблюдают [safety.md](safety.md).

<a id="sec-9-6"></a>
### 4.1. Отслеживание плеча и кисти, измерение длины руки

**Ручные кейсы:** M-05/M-06, после применимого [P0](test-plan.md#sec-test-plan-6-1).

Используется штатная full-arm комбинация providers/features из
[Quest specification](quest-specification.md#sec-5-1).

Для анализа абсолютной ошибки собирается dataset с независимым эталоном shoulder/wrist
известной погрешности: не менее 10 пользователей и 20 неподвижных поз на пользователя.
Это инженерное измерение, а не визуальный ручной сценарий. Метрики автоматически
вычисляются по этому dataset. Тестовое крепление
WRIST_TEST не является входом управления. Отсутствующие sensor timestamps не выдумываются.

| Метрика | Критерий |
|---|---:|
| p95 ошибка положения плеча в статических контрольных позах | `<=30 мм` |
| p95 ложное смещение плеча при только головы yaw/pitch | `<=20 мм` |
| ошибка изменения положения после шага/приседания | `<=30 мм` |
| автоматическое восстановление после краткого пропуска | без пользовательской перекалибровки |
| p95 ошибка stationary `Wrist` относительно тестового крепления | `<=20 мм` |
| p95 ошибка длины `Shoulder→Wrist` | `<=30 мм` |
| p95 ошибка направления `Shoulder→Wrist` | `<=3°` |
| накопленный offset после возврата в ту же неподвижную позу | отсутствует; ошибка остаётся в том же статистическом диапазоне |

human_arm_reach: >=5 runs на каждого пользователя; 3 принятые устойчивые выпрямленные
позы на run (непринятые можно повторять); разница медиан <=20 mm. Reach не меняется после
поворота/перемещения. Stationary vector p95 jitter <=15 mm, filter latency p95 <=30 ms.
Сквозная точность проверяется по [§4.11](#sec-9-20).

<a id="sec-9-10"></a>
### 4.2. Локализация QR

```text
coarse ShoulderCenter repeatability p95 <= 25 mm
coarse RobotBaseFrame yaw repeatability p95 <= 5°
accepted commissioning/startup q_qr uncertainty95 <= configured qr_joint_angle_uncertainty95_max_deg
base relocation after RobotLocalization without re-localization → A/B/C motion authority = 0
localization source = MRUK QR Trackables only
```

Coarse gates не заменяют uncertainty95 budget принятого stationary окна; jitter/conditioning/propagated uncertainty фиксируются. Недостаточная точность не ослабляет gate.

<a id="sec-9-11"></a>
### 4.3. Инженерная калибровка RobotGeometry

```text
QR geometry residual p95 <= 25 mm
FK TCP error against independent measurement p95 <= 15 mm
```

<a id="sec-9-12"></a>
### 4.4. Инженерная калибровка `DriveCalibration` Base/Shoulder/Elbow

**Критерии физической калибровки** по [Quest §16](quest-specification.md#sec-5-16):
для каждой A/B/C >=10 независимых runs; >=5 stationary точек в каждом направлении
и отдельные hold-out observations, дополненные независимой метрологией.

```text
sign(k_axis) stable across runs
scale repeatability p95 <= 0.5% relative
fit residual p95 <= 1.0°
hold-out encoder→QR prediction p95 <= 1.5°
hold-out max error <= 3.0°
backlash_total_angle <= 3.0°
forward/reverse same-pose discrepancy p95 <= 2.0°
```

После >=1000 квалифицированных циклов physical error не растёт. Nominal 5:1 ~0.2°/count —
только sanity check. Метрология и pre-motion fixture/HOLD prerequisites обязательны;
неудовлетворительный люфт/нелинейность исправляются механически. Алгоритм калибровки
и безопасный порядок приводов определяются владельцем, без повторения процедуры здесь.

<a id="sec-9-13"></a>
### 4.5. QR→энкодерная `JointReference` при запуске

**Критерии физической startup reference** по [Quest §16](quest-specification.md#sec-5-16):
>=30 независимых запусков, stationary capture и отдельная контрольная QR observation.

```text
second QR verification vs q_actual p95 <= 1.5°
second QR verification max <= 3.0°
post-move encoder→QR prediction p95 <= 2.0°
```

Evidence подтверждает одну неподвижную capture-позу и реальные observed A/B/C reference/q
при partial scope; disabled оси имеют zero writes.

<a id="sec-9-14"></a>
### 4.6. Калибровка и проверка захвата по QR

**Критерии физической калибровки Gripper** по [Quest §16](quest-specification.md#sec-5-16):
>=10 независимых runs, stationary bidirectional observations и hold-out.

```text
jaw opening reconstruction p95 <= 2 mm
hold-out opening error <= 4 mm
center shift due to symmetric opening p95 <= 2 mm
startup grip_actual error <= 0.05 normalized
forward/reverse same-opening discrepancy <= configured gripper backlash limit
```

До движения независимо доказан signed safe-open limit. Немонотонность/асимметрия
исправляются механически; software calibration не маскирует дефект конструкции.

<a id="sec-9-15"></a>
### 4.7. Механические характеристики



<a id="sec-9-15-1"></a>
#### 4.7.1. Соосность

Shoulder и Elbow без приводных gears должны свободно вращаться, не закусывать и не раздвигать рамы.

<a id="sec-9-15-2"></a>
#### 4.7.2. Shoulder HOLD

Наиболее тяжёлая горизонтальная поза собранной руки без внешнего предмета, `60 s`:

```text
TCP drift <= 10 mm
joint drift <= 1.5°
steady duty average <= 40%
steady duty p95 <= 50%
```

<a id="sec-9-15-3"></a>
#### 4.7.3. Безопасные границы

При калибровке проверяется:

- Base software bounds имеют cable slack с обеих сторон;
- Base mechanical hard-stop срабатывает раньше натяжения connector/cable;
- Shoulder software flexion никогда не превышает `90°`;
- Elbow software flexion никогда не превышает `90°`;
- физические механические ограничители расположены за software bounds и до опасной геометрии.

Фиксация основания проходит измерение проскальзывания при worst-case нагрузке;
после отключения QR нет заявленного online base-slip detection. Метод и условия —
[Спецификация механики](mechanical-specification.md).

<a id="sec-9-15-4"></a>
#### 4.7.4. Слежение суставов

**Критерии физического слежения:** dynamic q error p95 <=2.5°, max transient <=8°,
steady velocity tracking bias в qualified limit. FeedForwardMap квалифицирован в фактическом
q/torque/battery/payload domain. Regulator/unit/sign и out-of-domain behavior принадлежат
[EV3 §6](ev3-specification.md#sec-7-6), а не каталогу сценариев этого плана.

<a id="sec-9-15-5"></a>
#### 4.7.5. Повторяемость TCP

Одна точка достигается с разных направлений:

```text
TCP repeatability p95 <= 10 mm
max <= 15 mm
```

<a id="sec-9-15-6"></a>
#### 4.7.6. Потеря питания и независимый POWER_CUT

**Критерии физической потери питания:** POWER_CUT снимает энергию независимо от
Linux; оператор находится вне swept volume. Для EMPTY и каждого разрешённого PayloadProfile
квалифицированы worst-case poses по [Механике §15](mechanical-specification.md#sec-6-15):
peak TCP speed <=power_loss_peak_tcp_speed_limit_mps, displacement/time-to-rest,
отсутствие cable tension/part or payload ejection и безопасное containment.
POWER_CUT actuation→power removed <=qualified power_cut_max_disconnect_ms.

<a id="sec-9-15-7"></a>
#### 4.7.7. JointSafeSet, coupled collision и проверка пути

**Критерии допуска coupled safety:** для EMPTY и каждого разрешённого PayloadProfile
проверена каждая SAFE cell независимым conservative whole-cell proof; недоказанных SAFE cells=0.
Metadata/hash соответствует collision model/profile/bounds/grid/inflation. Физическое
boundary evidence содержит cell indices/path/effective q/hashes и motor result.

Partial A/B/C qualification использует полные реальные references, EMPTY/EMPTY и
safety_observation_mask=0x07|actuator_scope_mask; disabled нагрузочные оси fixture/support-ятся
без motor writes. Это pre-motion prerequisites, не сценарии ручной приёмки.
Владельцы coupled safety — [EV3](ev3-specification.md) и [Механика](mechanical-specification.md).

<a id="sec-9-16"></a>
### 4.8. Защита моторов



<a id="sec-9-16-1"></a>
#### 4.8.1. Препятствие и заклинивание основных суставов

**Критерии физической квалификации:** candidate response и stall fault укладываются
в соответствующий configured timeout + 1 motor-loop period; после candidate duty не растёт,
после fault нет high-duty retry; incident/FlightRecorder сохраняются.

Используется квалифицированное fixture; блокировка рукой или хрупким предметом запрещена.

<a id="sec-9-16-2"></a>
#### 4.8.2. Реверс и выбор люфта

**Критерии физической квалификации:** measured backlash/take-up и acceleration
соответствуют [EV3](ev3-specification.md); нет motor kick, gear impact или скачка q_actual
на motor-side backlash. Допуск действует во всём qualified user-speed диапазоне.

<a id="sec-9-16-3"></a>
#### 4.8.3. Длительная нагрузка / `MotorStressScore`

**Критерии физической квалификации:** нагрузка не повреждает устройство,
WARN/CRITICAL и high-duty limits соответствуют [EV3](ev3-specification.md).
MotorStressScore не является температурой. Exposure segment <=60 s; длительный горизонт
проверяется virtual time/qualified threshold injection.

<a id="sec-9-16-4"></a>
#### 4.8.4. Перегрузка при удержании

**Критерии физической квалификации:** hold_duty_limit_permille не превышен
в квалифицированных позах; safety policy при перегрузке соответствует
[EV3 §14.5](ev3-specification.md#sec-7-14-5). Снятие активного момента не создаёт разрушительного
падения по критериям потери питания и механики.

<a id="sec-9-16-6"></a>
#### 4.8.5. Контакт и заклинивание захвата

**Критерии физической квалификации Gripper:**

| Метрика | Критерий |
|---|---|
| Contact dataset | >=100 cycles; empty/compliant/rigid предметы до qualified максимального раскрытия |
| False contact | <=1/100 |
| Реальный контакт | Нет дальнейшего роста усилия и видимого повреждения от forcing |
| Полный ход | В commissioned timing range |
| Opening jam | Не классифицируется как нормальный closing contact |
| Scope D-only | Nonzero A/B/C writes=0 |

Contact/take-up/jam/release thresholds получены из квалифицированного dataset;
их изменение требует повторной физической проверки. Правила contact/payload —
[EV3](ev3-specification.md) и [Протокол](protocol-specification.md).

<a id="sec-9-17"></a>
### 4.9. EV3: физические критерии, временной бюджет и ресурсы

Метрики собираются при рабочей сети и разрешённой нагрузке Diagnostic/logging.
Для каждого движения соблюдается ограничение из [§6.1.2](test-plan.md#sec-9-1-6).

| Метрика | Gate |
|---|---|
| Motor loop | 50 Hz; interval p99 <=25 ms; normal max <50 ms |
| Deadlines | scheduler-induced SAFE_HOLD=0; unexplained misses=0 |
| HMAC + exact-length parse | Service time p99 <2 ms |
| Cadence | Quest configured ~60 Hz независимо от render; EV3 telemetry ~20 Hz |
| Resources | Bounded heap/queues после READY; tick без filesystem/path lookup, JSON/YAML/HMAC/send |
| Backpressure | Сначала снижается Diagnostic; logger stalls допускают log_drop_count, не потерю reserved safety events/loop budget |

Не требуется физически снижать напряжение до повреждения устройства.

<a id="sec-9-19"></a>
### 4.10. Реальные задержки защиты EV3

Проверяются реальные задержки перехода к безопасному выходу и остановки механизма
по [EV3 §2](ev3-specification.md#sec-7-2) и [Безопасности](safety.md).

| Метрика | Критерий |
|---|---|
| Watchdog expiry → zero/brake | p99 <=controller_watchdog_takeover_limit_ms |
| LOCAL_STOP input edge → zero/brake | p99 <=local_stop_response_limit_ms |
| Grip release → HOLD/scoped inhibit | p95 <=80 ms |
| Full link loss → SAFE_HOLD | p95 <=150 ms |
| Механическая остановка | Измеренные stopping displacement/time-to-rest в qualified bounds |
| Владение приводами | Concurrent writers=0; после завершения нет активного motor воздействия |

Evidence включает реальные peer credentials/permissions, эксклюзивный lease и terminal safe
state. Motion-capable restart требует reset, network-only сохраняет zero-output.

<a id="sec-9-20"></a>
### 4.11. Сквозной тест повторения движения руки

**Критерии физической сквозной точности:** для центральных unclipped движений
`|P_actual-P_projected| p95 <=25 mm`. C-01 подтверждён независимыми измерениями направления
и масштаба Shoulder→TCP; совпадение actual с projected само по себе недостаточно.

Evidence содержит реальные Shoulder/Wrist observations, requested/projected target,
q_target/q_ref/q_actual и независимый P_actual; различает tracking/mapping/following errors.
Live данные получаются при ручной проверке. Пользователь наблюдает обычную
работу в M-02/M-05/M-06; программные invariants проверяются по [§3](test-plan.md#sec-9-1-2).

<a id="sec-9-22"></a>
### 4.12. Производительность Quest

При M-05/M-10 измеряются tracking и производительность установленного Quest.
NFR-PERF-12 проверяется при холодном запуске, после прогрева и в допустимом thermally-limited
режиме; отчёт содержит refresh rate, frame time, missed frames и temperature.
После прогрева нет повторяющихся allocations в control/UI; отключение QR подтверждается
profiler. Критерии производительности — [требования к продукту](product-requirements.md).

Stage 5/D-only проверяет Hand/grasp, левый Touch Plus, JAW reference и engineering UI;
Body/Wrist/full QR/mapping — N_A(OUT_OF_SCOPE). Full-arm использует полную platform matrix.
Synthetic observations не подтверждают качество реального tracking.

<a id="sec-9-1-8"></a>
## 5. Автоматические отчёты

Runners создают отчёты программных и интеграционных проверок; runtime — журналы сессий
и инциденты. Пользователь не заполняет формы: при дефекте сообщает о проблеме и
прилагает автоматический отчёт или выполняет штатный экспорт.

| Вид | Что содержит |
|---|---|
| Тесты | Команда/suite/case, PASS/FAIL/NOT_RUN/N_A, причина, время, identity проверенного кандидата |
| Сборка | Компонент/режим, build_id, хэш пакета, входы и результат упаковки |
| Установка и запуск | Назначенные устройства, версия, время и результат шагов, первый отказ и конечное безопасное состояние |
| Измерения | Источник, доступные samples, условия, порог, результат анализа; без данных — не измерено |
| Инцидент | События и ограниченный FlightRecorder вокруг сбоя, контекст Quest/EV3 |

Операции на устройствах имеют deadline и показывают progress. Их JSON-формат —
[lifecycle_result.schema.json](../config/schema/lifecycle_result.schema.json).
Журнальные сообщения не смешиваются с JSON transport. Отчёт не доказывает то, что не запускалось:
отсутствие жалоб не даёт автоматический PASS ручному сценарию, host-тест не подтверждает устройство.

Локальные отчёты создаются инструментами в `results/**`; они не редактируются вручную
и не служат условием следующей операции. Результаты, подтверждающие этап или релиз,
публикуются неизменяемыми внешними файлами. Запись статуса/релиза хранит URI, SHA-256
и идентичность проверенного кандидата. Это публикация отчёта, а не обязательный GitHub CI job.
Очистка локальных файлов не отменяет опубликованный результат и не меняет работу системы.
Хранение журналов и защита данных — [§2.1](#sec-8-13),
пробелы реализации — [current-status.md](current-status.md).

<a id="sec-9-25"></a>
## 6. Приложение: автоматическая связь с требованиями

Таблицы служат автоматической проверке полноты ID и ссылок, не являются формой для пользователя.
Описание ручных действий находится в [плане тестирования](test-plan.md#sec-9-23).

<a id="sec-test-plan-25-1"></a>
### 6.1. Критерии продукта и процедуры

Сценарии покрывают наблюдаемую часть всех критериев; точные ошибки, задержки и скрытые
гарантии проверяются автоматическими тестами/анализом.

| Критерий продукта | Что должно быть доказано | Приёмочные процедуры |
|---|---|---|
| [C-01](product-requirements.md#criterion-c-01) | M-02, M-06; Направление и масштаб проверены по независимым измерениям, а не только по совпадению target/actual. | [§3](test-plan.md#sec-9-1-2), [§4.1](#sec-9-6), [§4.11](#sec-9-20) |
| [C-02](product-requirements.md#criterion-c-02) | M-05; Локоть, поворот кисти и головы не меняют цель при фиксированных плече и запястье; движения корпуса учитываются. | [§3](test-plan.md#sec-9-1-2), [§4.1](#sec-9-6), [§4.11](#sec-9-20) |
| [C-03](product-requirements.md#criterion-c-03) | M-06, M-04; Повторные движения, HOLD/re-arm и восстановление отслеживания не оставляют смещения; фильтр сходится к абсолютной цели. | [§3](test-plan.md#sec-9-1-2), [§4.5](#sec-9-13), [§4.6](#sec-9-14), [§4.9](#sec-9-17), [§4.11](#sec-9-20) |
| [C-04](product-requirements.md#criterion-c-04) | M-02, M-07, M-08; Безопасны цель, весь путь, ограничения приводов и квалифицированная нагрузка, включая неуправляемые связанные суставы. | [§4.7](#sec-9-15), [§4.8](#sec-9-16), [§4.9](#sec-9-17), [§4.11](#sec-9-20) |
| [C-05](product-requirements.md#criterion-c-05) | M-03, M-08; Проверены пропорциональность, контакт, открывание, opening jam и запуск из неизвестной предыстории захвата. | [§3](test-plan.md#sec-9-1-2), [§4.6](#sec-9-14), [§4.8.5](#sec-9-16-6) |
| [C-06](product-requirements.md#criterion-c-06) | M-09, M-12; Проверены release/re-arm, потери входов и связи, отказы процессов/I/O, LOCAL_STOP и независимый POWER_CUT. | [§3](test-plan.md#sec-9-1-2), [§4.7.6](#sec-9-15-6), [§4.9](#sec-9-17), [§4.10](#sec-9-19) |
| [C-07](product-requirements.md#criterion-c-07) | M-01, M-11; Для текущего режима подтверждены входы, P0, QR-локализация, калибровка и независимая проверка стартовой привязки. | [§3](test-plan.md#sec-9-1-2), [§4.1](#sec-9-6), [§4.2](#sec-9-10), [§4.3](#sec-9-11), [§4.4](#sec-9-12), [§4.5](#sec-9-13), [§4.6](#sec-9-14) |
| [C-08](product-requirements.md#criterion-c-08) | M-01, M-04; Проверены обнаружение после смены адреса, identity, владелец, HMAC/replay, идемпотентность, LAN permission и изоляция. | [§3](test-plan.md#sec-9-1-2), [§4.12](#sec-9-22), [§2.1](metrics-and-logs.md#sec-8-13) |
| [C-09](product-requirements.md#criterion-c-09) | M-01, M-02, M-04; Пользователи проходят русский мастер, понимают запреты и остановку; обычный запуск укладывается в 90 с по медиане и не требует PC. | [§4.12](#sec-9-22), [§6.2](test-plan.md#sec-9-23) |
| [C-10](product-requirements.md#criterion-c-10) | M-13; Инцидент содержит сопоставимый контекст Quest/EV3; отказы записи и ротации не задерживают защиту. | [§4.9](#sec-9-17), [§3](test-plan.md#sec-9-1-2) |
| [C-11](product-requirements.md#criterion-c-11) | M-01, M-11, M-13; Зафиксированы exact artifacts, механика, конфигурация и runtime; проверены совместимость и единое ядро Release/Diagnostic. | [§1](test-plan.md#sec-9-1), [§4.1](#sec-9-6), [§4.10](#sec-9-19), [§5.1](engineering.md#sec-engineering-build-profiles), [§5.3](engineering.md#sec-engineering-build-validation), [§7](test-plan.md#sec-9-26) |
| [C-12](product-requirements.md#criterion-c-12) | M-14; Проверены отсутствие запрещённых данных/секретов, явное включение расширенной записи, retention, права и экспорт. | [§3](test-plan.md#sec-9-1-2), [§2.1](metrics-and-logs.md#sec-8-13) |
| [C-13](product-requirements.md#criterion-c-13) | M-10; Измерены cadence, stop latency, ресурсы и thermal behavior при штатной и квалифицированной неблагоприятной нагрузке. | [§4.9](#sec-9-17), [§3](test-plan.md#sec-9-1-2), [§4.10](#sec-9-19), [§4.12](#sec-9-22) |

<a id="sec-test-plan-25-2"></a>
### 6.2. Требования и владельцы

Каждый ID указан явно; ссылка на семейство или диапазон ID не заменяет покрытие
отдельного требования. Текст требования хранится только в требованиях к продукту.
Ссылки указывают стадию проверки и критерии PASS;
инженерный scope не заменяет финальную приёмку полного продукта.

| Область требований | ID | Владельцы решения | Проверка |
|---|---|---|---|
| [Положение руки и движения корпуса](product-requirements.md#sec-product-3-1-1) | `FR-TRK-01`, `FR-TRK-07`, `FR-CAL-01`, `FR-CAL-04`, `FR-TRK-08` | [Quest §4.3](quest-specification.md#sec-5-4-3), [Quest §6](quest-specification.md#sec-5-6), [Quest §8](quest-specification.md#sec-5-8) | [§3](test-plan.md#sec-9-1-2), [§4.1](#sec-9-6), [§4.11](#sec-9-20) |
| [Сжатие кисти](product-requirements.md#sec-product-3-1-2) | `FR-TRK-03`, `FR-CAL-05` | [Quest §9](quest-specification.md#sec-5-9), [Quest §11](quest-specification.md#sec-5-11) | [§3](test-plan.md#sec-9-1-2), [§4.8.5](#sec-9-16-6) |
| [Разрешение движения через Left Grip](product-requirements.md#sec-product-3-1-3) | `FR-TRK-02`, `FR-TRK-04`, `FR-TRK-05` | [Quest §4.2](quest-specification.md#sec-5-4-2), [EV3 §13](ev3-specification.md#sec-7-13) | [§3](test-plan.md#sec-9-1-2), [§6.2](test-plan.md#sec-9-23) |
| [Повторное разрешение движения](product-requirements.md#sec-product-3-1-4) | `FR-TRK-06`, `FR-TRK-09`, `FR-TRK-10` | [Quest §4.2](quest-specification.md#sec-5-4-2), [Протокол §2.7](protocol-specification.md#sec-4-7-7), [EV3 §13](ev3-specification.md#sec-7-13) | [§3](test-plan.md#sec-9-1-2), [§6.2](test-plan.md#sec-9-23) |
| [Проверка готовности перед движением](product-requirements.md#sec-product-3-2-1) | `FR-XR-01`, `FR-XR-02`, `FR-XR-06`, `FR-XR-07` | [Quest §2](quest-specification.md#sec-5-2), [Архитектура §6](system-architecture.md#sec-4-4) | [§3](test-plan.md#sec-9-1-2), [§4.1](#sec-9-6), [§4.12](#sec-9-22), [§6.2](test-plan.md#sec-9-23) |
| [Изменение пространства, пауза и восстановление](product-requirements.md#sec-product-3-2-2) | `FR-XR-03`, `FR-XR-04`, `FR-XR-05` | [Quest §2](quest-specification.md#sec-5-2), [Quest §5](quest-specification.md#sec-5-5), [Quest §18](quest-specification.md#sec-5-18) | [§3](test-plan.md#sec-9-1-2), [§4.12](#sec-9-22) |
| [Калибровка пользователя](product-requirements.md#sec-3-1-3) | `FR-CAL-03` | [Quest §7](quest-specification.md#sec-5-7) | [§4.1](#sec-9-6) |
| [Отображение руки в движение робота](product-requirements.md#sec-3-1-4) | `FR-MAP-01`, `FR-MAP-02`, `FR-MAP-03`, `FR-MAP-05`, `FR-MAP-08` | [Quest §10](quest-specification.md#sec-5-10), [Quest §13](quest-specification.md#sec-5-13), [Quest §14](quest-specification.md#sec-5-14), [EV3 §10](ev3-specification.md#sec-7-10) | [§3](test-plan.md#sec-9-1-2), [§4.7.7](#sec-9-15-7), [§4.11](#sec-9-20) |
| [Движение по сжатию кисти](product-requirements.md#sec-product-3-5-1) | `FR-GRP-01`, `FR-GRP-02`, `FR-GRP-03` | [Quest §9](quest-specification.md#sec-5-9), [Quest §11](quest-specification.md#sec-5-11), [EV3 §15.1](ev3-specification.md#sec-7-15-1) | [§3](test-plan.md#sec-9-1-2), [§4.6](#sec-9-14), [§4.8.5](#sec-9-16-6) |
| [Контакт с предметом и заклинивание](product-requirements.md#sec-product-3-5-2) | `FR-GRP-04`, `FR-GRP-05` | [EV3 §15](ev3-specification.md#sec-7-15) | [§4.8.5](#sec-9-16-6), [§3](test-plan.md#sec-9-1-2) |
| [Пространственная локализация](product-requirements.md#sec-product-3-6-1) | `FR-QR-01`, `FR-QR-02`, `FR-QR-10` | [Quest §5](quest-specification.md#sec-5-5), [Quest §15](quest-specification.md#sec-5-15), [Quest §16.9](quest-specification.md#sec-5-16-9), [Механика §9](mechanical-specification.md#sec-6-9), [Механика §11](mechanical-specification.md#sec-6-11) | [§4.2](#sec-9-10), [§4.3](#sec-9-11), [§4.7.3](#sec-9-15-3) |
| [Стартовая привязка и работа после неё](product-requirements.md#sec-product-3-6-2) | `FR-QR-05`, `FR-QR-06`, `FR-QR-07`, `FR-QR-08`, `FR-GRP-06`, `FR-GRP-08` | [Quest §16.9](quest-specification.md#sec-5-16-9), [EV3 §5.4](ev3-specification.md#sec-7-5-4), [EV3 §6](ev3-specification.md#sec-7-6) | [§4.5](#sec-9-13), [§4.6](#sec-9-14), [§4.12](#sec-9-22) |
| [Инженерная калибровка приводов](product-requirements.md#sec-product-3-6-3) | `FR-QR-03`, `FR-QR-04`, `FR-QR-09`, `FR-GRP-07` | [Quest §16](quest-specification.md#sec-5-16), [EV3 §5](ev3-specification.md#sec-7-5), [Механика §14.4](mechanical-specification.md#sec-6-14-4) | [§4.3](#sec-9-11), [§4.4](#sec-9-12), [§4.6](#sec-9-14) |
| [Обнаружение и обновление адреса](product-requirements.md#sec-product-3-7-1) | `FR-NET-01`, `FR-NET-02`, `FR-NET-03` | [Протокол §1](protocol-specification.md#sec-4-6), [EV3 §22](ev3-specification.md#sec-7-22), [Разработка §6.3](engineering.md#sec-8-12) | [§3](test-plan.md#sec-9-1-2), [§4.12](#sec-9-22) |
| [Передача целей и принятие операций](product-requirements.md#sec-product-3-7-2) | `FR-NET-04`, `FR-NET-05`, `FR-NET-06`, `FR-NET-07` | [Протокол §2](protocol-specification.md#sec-4-7), [EV3 §2.2](ev3-specification.md#sec-7-2-2), [EV3 §8](ev3-specification.md#sec-7-8) | [§3](test-plan.md#sec-9-1-2), [§4.10](#sec-9-19) |
| [Рабочие пределы, траектория и нагрузка](product-requirements.md#sec-product-3-8-1) | `FR-MAP-04`, `FR-SAFE-04`, `FR-SAFE-06`, `FR-SAFE-07`, `FR-SAFE-08`, `FR-SAFE-09`, `FR-SAFE-10` | [Quest §14](quest-specification.md#sec-5-14), [EV3 §10](ev3-specification.md#sec-7-10), [EV3 §16](ev3-specification.md#sec-7-16), [Безопасность §1](safety.md#sec-11-3) | [§4.7.3](#sec-9-15-3), [§4.7.7](#sec-9-15-7), [§4.8](#sec-9-16), [§4.11](#sec-9-20) |
| [Обнаружение заклинивания и перегрузки](product-requirements.md#sec-product-3-8-2) | `FR-SAFE-01`, `FR-SAFE-02`, `FR-SAFE-05` | [EV3 §14](ev3-specification.md#sec-7-14) | [§4.8](#sec-9-16), [§3](test-plan.md#sec-9-1-2) |
| [Удержание и реакция на потерю управления или неисправность](product-requirements.md#sec-product-3-8-3) | `FR-HOLD-01`, `FR-HOLD-02`, `FR-CAL-06`, `FR-MAP-07`, `FR-SAFE-03`, `FR-SAFE-11`, `FR-SAFE-12` | [Quest §18](quest-specification.md#sec-5-18), [EV3 §13](ev3-specification.md#sec-7-13), [EV3 §14.6](ev3-specification.md#sec-7-14-6), [EV3 §14.7](ev3-specification.md#sec-7-14-7), [EV3 §24](ev3-specification.md#sec-7-24) | [§3](test-plan.md#sec-9-1-2), [§4.9](#sec-9-17), [§4.10](#sec-9-19) |
| [Физическая остановка и восстановление питания](product-requirements.md#sec-product-3-8-4) | `FR-STOP-01`, `FR-STOP-02`, `FR-STOP-03` | [Механика §10](mechanical-specification.md#sec-6-10), [Механика §15](mechanical-specification.md#sec-6-15), [EV3 §17](ev3-specification.md#sec-7-17), [EV3 §18](ev3-specification.md#sec-7-18) | [§4.7.6](#sec-9-15-6), [§4.10](#sec-9-19), [§3](test-plan.md#sec-9-1-2) |
| [Состояния и отображение движения](product-requirements.md#sec-product-3-9-1) | `FR-UI-01`, `FR-UI-04`, `FR-MAP-06` | [Quest §17.4](quest-specification.md#sec-5-17-4), [Quest §17.6](quest-specification.md#sec-5-17-6) | [§4.11](#sec-9-20), [§4.12](#sec-9-22), [§6.2](test-plan.md#sec-9-23) |
| [Мастер запуска и пространственные подсказки](product-requirements.md#sec-product-3-9-2) | `FR-UI-02`, `FR-UI-03`, `FR-UI-07`, `FR-UI-08` | [Quest §17.1](quest-specification.md#sec-5-17-1), [Quest §17.3](quest-specification.md#sec-5-17-3), [Quest §17.7](quest-specification.md#sec-5-17-7) | [§4.12](#sec-9-22), [§6.2](test-plan.md#sec-9-23) |
| [Инженерные проверки и отдельные режимы](product-requirements.md#sec-product-3-9-3) | `FR-UI-05`, `FR-UI-06`, `FR-UI-09`, `FR-GRP-09` | [Quest §17.3](quest-specification.md#sec-5-17-3), [Quest §17.7](quest-specification.md#sec-5-17-7), [EV3 §15](ev3-specification.md#sec-7-15), [Безопасность §2.2](safety.md#sec-11-4-2) | [§4.8.5](#sec-9-16-6), [§4.12](#sec-9-22), [§6.2](test-plan.md#sec-9-23) |
| [Регистрация событий и разбор инцидентов](product-requirements.md#sec-product-diagnostics) | `FR-DIAG-02`, `FR-DIAG-03`, `FR-DIAG-05`, `FR-DIAG-06`, `FR-DIAG-07` | [EV3 §20](ev3-specification.md#sec-7-20), [Метрики и журналы §2.1](metrics-and-logs.md#sec-8-13), [Метрики и журналы §2.2](metrics-and-logs.md#sec-8-14) | [§3](test-plan.md#sec-9-1-2) |
| [Качество измерений и подавление шума](product-requirements.md#sec-product-4-1-1) | `NFR-ACC-01`, `NFR-ACC-08` | [Quest §4.3](quest-specification.md#sec-5-4-3), [Quest §8](quest-specification.md#sec-5-8), [EV3 §11](ev3-specification.md#sec-7-11) | [§3](test-plan.md#sec-9-1-2), [§4.1](#sec-9-6), [§4.7.4](#sec-9-15-4), [§4.11](#sec-9-20) |
| [Повторяемость цели и положения суставов](product-requirements.md#sec-product-4-1-2) | `NFR-ACC-02`, `NFR-ACC-04`, `NFR-ACC-07` | [Quest §10](quest-specification.md#sec-5-10), [EV3 §5.1](ev3-specification.md#sec-7-5-1), [EV3 §6](ev3-specification.md#sec-7-6), [Справочник §2.4](reference.md#sec-11-1-4) | [§3](test-plan.md#sec-9-1-2), [§4.5](#sec-9-13), [§4.6](#sec-9-14), [§4.9](#sec-9-17), [§4.11](#sec-9-20) |
| [Точность калибровки и контрольной привязки](product-requirements.md#sec-product-4-1-3) | `NFR-ACC-03`, `NFR-ACC-05`, `NFR-ACC-06` | [Quest §16](quest-specification.md#sec-5-16), [EV3 §5.6](ev3-specification.md#sec-7-5-6), [Механика §9](mechanical-specification.md#sec-6-9) | [§4.2](#sec-9-10), [§4.3](#sec-9-11), [§4.4](#sec-9-12), [§4.5](#sec-9-13), [§4.6](#sec-9-14) |
| [Частоты и стабильность обновления](product-requirements.md#sec-product-4-2-1) | `NFR-PERF-01`, `NFR-PERF-02`, `NFR-PERF-03`, `NFR-PERF-04` | [EV3 §7](ev3-specification.md#sec-7-7), [EV3 §19](ev3-specification.md#sec-7-19), [Архитектура §7](system-architecture.md#sec-4-5) | [§4.9](#sec-9-17), [§4.12](#sec-9-22) |
| [Задержки прекращения движения](product-requirements.md#sec-product-4-2-2) | `NFR-PERF-05`, `NFR-PERF-06`, `NFR-PERF-07`, `NFR-PERF-13` | [Quest §18](quest-specification.md#sec-5-18), [EV3 §9](ev3-specification.md#sec-7-9), [EV3 §17](ev3-specification.md#sec-7-17), [EV3 §2.4](ev3-specification.md#sec-7-2-4) | [§3](test-plan.md#sec-9-1-2), [§4.10](#sec-9-19) |
| [Ресурсы и плавность работы приложения](product-requirements.md#sec-product-4-2-3) | `NFR-PERF-08`, `NFR-PERF-09`, `NFR-PERF-11`, `NFR-PERF-12` | [EV3 §7.3](ev3-specification.md#sec-7-7-3), [Quest §3](quest-specification.md#sec-5-3), [Quest §16.9](quest-specification.md#sec-5-16-9) | [§4.9](#sec-9-17), [§4.12](#sec-9-22), [§5.1](engineering.md#sec-engineering-build-profiles) |
| [Устойчивость к отказам связи и процессов](product-requirements.md#sec-product-4-3-1) | `NFR-REL-01`, `NFR-REL-02`, `NFR-REL-03`, `NFR-REL-13` | [EV3 §2.2](ev3-specification.md#sec-7-2-2), [EV3 §2.4](ev3-specification.md#sec-7-2-4), [EV3 §9](ev3-specification.md#sec-7-9), [EV3 §24](ev3-specification.md#sec-7-24) | [§3](test-plan.md#sec-9-1-2), [§4.10](#sec-9-19) |
| [Механические пределы и допустимая нагрузка](product-requirements.md#sec-product-4-3-2) | `NFR-REL-05`, `NFR-REL-06`, `NFR-REL-10`, `NFR-REL-12` | [Механика §8](mechanical-specification.md#sec-6-8), [Механика §12](mechanical-specification.md#sec-6-12), [EV3 §14.5](ev3-specification.md#sec-7-14-5), [EV3 §16](ev3-specification.md#sec-7-16), [Quest §14](quest-specification.md#sec-5-14) | [§4.7.2](#sec-9-15-2), [§4.7.3](#sec-9-15-3), [§4.7.7](#sec-9-15-7), [§4.8.4](#sec-9-16-4) |
| [Безопасность при препятствии, отказе или потере питания](product-requirements.md#sec-product-4-3-3) | `NFR-REL-09`, `NFR-REL-04`, `NFR-REL-11` | [Механика §15](mechanical-specification.md#sec-6-15), [EV3 §14](ev3-specification.md#sec-7-14), [EV3 §18](ev3-specification.md#sec-7-18), [Безопасность §1](safety.md#sec-11-3) | [§4.7.6](#sec-9-15-6), [§4.8](#sec-9-16), [§3](test-plan.md#sec-9-1-2) |
| [Ограничения записи журналов](product-requirements.md#sec-3-2-4) | `NFR-LOG-02`, `NFR-LOG-05`, `NFR-LOG-06` | [EV3 §20](ev3-specification.md#sec-7-20), [Метрики и журналы §2.1](metrics-and-logs.md#sec-8-13) | [§4.9](#sec-9-17), [§3](test-plan.md#sec-9-1-2) |
| [Удобство использования](product-requirements.md#sec-3-2-5) | `NFR-UX-01`, `NFR-UX-05`, `NFR-UX-07` | [Quest §17](quest-specification.md#sec-5-17) | [§6.2](test-plan.md#sec-9-23) |
| [Защита секретов](product-requirements.md#sec-product-4-6-1) | `NFR-SEC-02`, `NFR-SEC-08` | [Разработка §6.1](engineering.md#sec-8-11), [Разработка §6.3](engineering.md#sec-8-12) | [§3](test-plan.md#sec-9-1-2), [§2.1](metrics-and-logs.md#sec-8-13) |
| [Подлинность сообщений и защита от повторов](product-requirements.md#sec-product-4-6-2) | `NFR-SEC-01`, `NFR-SEC-04` | [Протокол §2.2](protocol-specification.md#sec-4-7-2), [Протокол §2.7](protocol-specification.md#sec-4-7-7) | [§3](test-plan.md#sec-9-1-2) |
| [Изоляция сети и разрешения доступа](product-requirements.md#sec-product-4-6-3) | `NFR-SEC-05`, `NFR-SEC-06`, `NFR-SEC-09` | [Разработка §6.3](engineering.md#sec-8-12), [Quest §2](quest-specification.md#sec-5-2), [Протокол §1](protocol-specification.md#sec-4-6) | [§3](test-plan.md#sec-9-1-2), [§4.12](#sec-9-22) |
| [Ограничение входящего трафика](product-requirements.md#sec-product-4-6-4) | `NFR-SEC-03`, `NFR-SEC-07` | [Протокол §2.3](protocol-specification.md#sec-4-7-3), [EV3 §23](ev3-specification.md#sec-7-23) | [§3](test-plan.md#sec-9-1-2), [§4.9](#sec-9-17) |
| [Совместимость конфигурации и калибровки](product-requirements.md#sec-product-4-7-1) | `NFR-MNT-01`, `NFR-MNT-03` | [Разработка §8](engineering.md#sec-8-9), [Quest §16.10](quest-specification.md#sec-5-16-10), [EV3 §5.6](ev3-specification.md#sec-7-5-6) | [§4.4](#sec-9-12), [§4.5](#sec-9-13), [§4.6](#sec-9-14), [§5.3](engineering.md#sec-engineering-build-validation) |
| [Идентификация сборки, механики и платформы](product-requirements.md#sec-product-4-7-2) | `NFR-MNT-02`, `NFR-MNT-05`, `NFR-MNT-07` | [Разработка §5.4](engineering.md#sec-8-6), [Разработка §5.1](engineering.md#sec-engineering-build-profiles), [Механика §19](mechanical-specification.md#sec-6-19) | [§4.1](#sec-9-6), [§5.3](engineering.md#sec-engineering-build-validation), [§7](test-plan.md#sec-9-26) |
| [Сохранение ядра управления и поддержка платформ](product-requirements.md#sec-product-4-7-3) | `NFR-MNT-04`, `NFR-MNT-06` | [Архитектура §4](system-architecture.md#sec-4-2), [EV3 §1](ev3-specification.md#sec-7-1), [Разработка §4](engineering.md#sec-8-5), [Разработка §5.1](engineering.md#sec-engineering-build-profiles) | [§4.10](#sec-9-19), [§5.1](engineering.md#sec-engineering-build-profiles), [§5.3](engineering.md#sec-engineering-build-validation) |
| [Конфиденциальность](product-requirements.md#sec-3-2-8) | `NFR-PRIV-01`, `NFR-PRIV-02`, `NFR-PRIV-03`, `NFR-PRIV-04` | [EV3 §20](ev3-specification.md#sec-7-20), [Метрики и журналы §2.1](metrics-and-logs.md#sec-8-13) | [§3](test-plan.md#sec-9-1-2), [§2.1](metrics-and-logs.md#sec-8-13) |

<a id="sec-test-plan-25-3"></a>
### 6.3. Проверка ссылок

Doclint автоматически проверяет ID, владельцев и ссылки матрицы.
Пользователи не заполняют evidence и не отмечают вручную прохождение сценариев.
