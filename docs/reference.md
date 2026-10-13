<a id="sec-11"></a>
# PHANTOM — нормативный справочник

Нормативный словарь, ссылки на формулы компонентов и правила измерения параметров.

<!-- BEGIN GENERATED TOC -->
<details>
<summary>Оглавление</summary>

- [1. Основные обозначения](#sec-1-3)
- [2. Формулы](#sec-11-1)
  - [2.1. Абсолютное отображение движения пользователя](#sec-11-1-1)
  - [2.2. IK](#sec-11-1-2)
  - [2.3. FK](#sec-11-1-3)
  - [2.4. QR↔энкодерная инженерная калибровка](#sec-11-1-4)
  - [2.5. Захват](#sec-11-1-5)
  - [2.6. Номинальная скорость передачи](#sec-11-1-6)
  - [2.7. Статический момент](#sec-11-1-7)
- [3. Параметры, фиксируемые измерением](#sec-11-6)

</details>
<!-- END GENERATED TOC -->

<a id="sec-1-3"></a>
## 1. Основные обозначения

| Обозначение | Смысл |
|---|---|
| `6DoF` | шесть степеней свободы позы: три координаты положения и три компоненты ориентации |
| `ACK` | подтверждение приёма/выполнения дискретной протокольной операции |
| `API` | Application Programming Interface; программный интерфейс платформы/библиотеки |
| `backlash` | служебное имя величины механического люфта передачи: диапазона движения моторного вала при смене направления до движения выходного звена |
| `Base` | поворотное основание манипулятора |
| `BOOT` | начальное состояние EV3 без допуска движения; startup и переходы — [Архитектура системы §5](system-architecture.md#sec-4-3) и [Спецификация EV3 §4](ev3-specification.md#sec-7-4) |
| `build_id` | component/profile-specific 32-byte SHA-256 build identity: Quest и EV3 имеют разные `build_id`, а Release/Diagnostic также имеют разные `build_id`; текстовое представление — 64 lowercase hex symbols. `build_id` детерминированно вычисляется как SHA-256 от RFC 8785 JCS canonical object semantic build inputs с явными именами полей и не включает hash итогового контейнера/артефакта или wall-clock provenance |
| `USER_CALIBRATION` | подготовка пользовательских входов активного профиля; состав входов — [Спецификация Quest §2](quest-specification.md#sec-5-2), калибровка длины руки — [Спецификация Quest §7](quest-specification.md#sec-5-7) |
| `DISCOVERY` | состояние поиска ожидаемого `robot_id` через DNS-SD/mDNS до создания authenticated session |
| `CONNECTED_UNREFERENCED` | authenticated CONTROL connection без допуска product `READY`; scope-specific смысл — [Архитектура системы §5](system-architecture.md#sec-4-3) |
| `ROBOT_CALIBRATION` | обычная startup-процедура QR-локализации и привязки энкодеров без автоматического движения робота |
| `COMMISSIONING` | инженерное состояние с фазами `CALIBRATION` и `ACTUATOR_QUALIFICATION`; локальная авторизация и переходы — [Архитектура системы §5](system-architecture.md#sec-4-3) |
| `Body Tracking` | Meta XR Movement SDK Body Tracking; непрерывная оценка позы тела пользователя |
| `Body_RightShoulder` | сустав правого плеча Meta Body Tracking; источник `HumanShoulderCenter` во время работы. Это оценка Body Tracking, а не физически прямой датчик плеча. |
| `TrackingQualificationProfile` | зафиксированная комбинация runtime/SDK/feature flags и критериев качества входов активного actuator scope; qualification — [Метрики и анализ §4.1](metrics-and-logs.md#sec-9-6) |
| `BRAKE` | пассивное электрическое торможение ev3dev после снятия управляющей мощности; не является активным удержанием позиции и не гарантирует удержание нагрузки |
| `CALIBRATION_JOG` | инженерная транзакция ограниченного движения одной оси; используется только при инженерной калибровке до QR-измерения |
| `ACTUATOR_QUALIFICATION` | фаза `COMMISSIONING` для квалификации штатного command path в ограниченном scope; условия допуска — [Архитектура системы §5](system-architecture.md#sec-4-3) и [Спецификация протокола §2.7](protocol-specification.md#sec-4-7-7) |
| `actuator_scope_mask` | 4-битная маска **motor-write authority**: bit0=A, bit1=B, bit2=C, bit3=D. В `COMMISSIONING/CALIBRATION` она задаёт оси, которые вообще могут быть выбраны `CALIBRATION_JOG`; одновременно движется только один `axis`. В `ACTUATOR_QUALIFICATION` это жёсткая верхняя граница приводов, которым штатный `COMMAND` может создать motor write. Полный Release использует `0x0F`; gripper-only — `0x08`; network-only — `0x00`. Маска не определяет, какие неподвижные оси необходимо наблюдать ради coupled-safety; для этого существует `safety_observation_mask`. Обе маски входят в semantic `CommissioningBundle`, EV3 authoritative. |
| `safety_observation_mask` | 4-битная маска приводов, чьи реальные encoder/reference-based положения должны быть валидно наблюдаемы для safety calculation независимо от motor-write authority. Она **никогда не разрешает motor write**. Всегда требуется `actuator_scope_mask ⊆ safety_observation_mask`: любой motor-authorized привод обязан одновременно наблюдаться. Для partial A/B/C `ACTUATOR_QUALIFICATION` все A/B/C, участвующие в 3D `JointSafeSet`, обязаны быть safety-observed (`mask & 0x07 == 0x07`) даже если motor authority выдана только C или B+C; их `q_actual` используется как fixed coordinate. Network-only=`0x00`, D-only=`0x08`, полный Release=`0x0F`. |
| `required_user_inputs` | hash-bound поле **Quest application/profile config**, а не `CommissioningBundle`: `NONE` — network-only без XR actuator inputs; `GRIPPER_ONLY` — grasp+Left Grip/lifecycle для user-driven D; `FULL_ARM` — Wrist+Body_RightShoulder+Left Grip/Multimodal и применимый Gripper input. Для QR commissioning/MANUAL input requirements определяются phase-specific `P0CompatibilityScope`/test profile. Поле не выдаёт motor authority; Quest schema валидирует его согласованность с mode/phase/scope. |
| `CI` | Continuous Integration; автоматический конвейер сборки, модульных/property-тестов и проверок артефактов |
| `COMMAND` | штатная аутентифицированная UDP-команда с последними абсолютными `q_target` и `grip_intent`; не содержит PWM |
| `controller_boot_id` | случайный идентификатор текущего запуска `phantom-controller`; меняется после его перезапуска |
| `count_per_rot` | количество отсчётов энкодера на один полный оборот вала мотора; для EV3 ожидается `360`, значение проверяется при запуске |
| `DHCP` | Dynamic Host Configuration Protocol; механизм сети, из-за которого IP EV3 может изменяться между подключениями |
| `Diagnostic` | профиль с расширенной диагностикой того же control/state/safety core; разрешённые engineering surfaces — [Разработка и развёртывание §5.5.2](engineering.md#sec-8-8-2) и [EV3 §5.2](ev3-specification.md#sec-7-5-2); объём записи — [Метрики и журналы §1](metrics-and-logs.md#sec-metrics-collection) |
| `DIAGNOSTIC_TELEMETRY` | расширенная телеметрия, разрешённая только в профиле Diagnostic |
| `DNS-SD/mDNS` | обнаружение сервиса EV3 в локальной сети без фиксированного IP; service type/domain и identity — [Спецификация протокола §1](protocol-specification.md#sec-4-6) |
| `DriveCalibration` | измеренная модель соответствия абсолютного отсчёта энкодера мотора физическому углу/раскрытию, включая знак, коэффициент и оценку люфта |
| `E_closed` | абсолютный отсчёт энкодера Gripper в закрытом положении **внутри конкретной инженерной calibration session**, зафиксированный по `GRIPPER_HOME`. Он используется для построения относительной кривой, но не переносится как абсолютный runtime limit через reboot/controller restart. |
| `D_open_counts` | модуль независимо подтверждённого безопасного encoder travel Gripper от `GRIPPER_HOME` до открытой границы; вместе с `open_encoder_sign` образует persistent signed `gripper_open_limit_delta_counts`. Абсолютный encoder count открытой границы существует только внутри конкретной calibration/reference session и через reboot не переносится. |
| `Elbow` | локтевой силовой сустав PHANTOM |
| `ELBOW_LEFT/RIGHT` | пара QR по сторонам физической оси Elbow; после поправок их середина задаёт `ElbowCenter` |
| `ElbowCenter` | вычисленный физический центр оси Elbow, полученный как середина исправленных точек `ELBOW_LEFT/RIGHT` |
| `encoder_count` | абсолютный счётчик встроенного датчика вращения EV3; для мотора EV3 один отсчёт соответствует одному градусу вала мотора |
| `EV3` | LEGO Mindstorms EV3 Brick; встроенный компьютер PHANTOM, выполняющий локальное управление моторами и логику безопасности |
| `FAULT` | latched fault condition; не отдельное wire-state protocol v1. Совместное представление через `STOPPED` и `fault_code` — [Спецификация протокола §3](protocol-specification.md#sec-11-2) |
| `FBS` | Full Body Synthesis Meta; отдельная функция синтеза full-body pose. Не следует смешивать с `Full Body joint set`; для pinned v1 profile FBS выключен и его compatibility с Multimodal контролируется P0/platform matrix. |
| `FMM` | Fast Motion Mode Meta Hand Tracking; режим повышенной устойчивости к быстрым движениям кисти. В pinned actuator profile PHANTOM v1 выключен; его совместимость с Multimodal проверяется по exact platform matrix/P0, а не предполагается. |
| `FD` | файловый дескриптор Linux; PHANTOM заранее открывает sysfs-файлы моторов и переиспользует FD в критическом цикле |
| `feed-forward` | упреждающая добавка к управляющему воздействию для компенсации гравитации/трения до появления ошибки положения |
| `FK` | Forward Kinematics, прямая кинематика: вычисление положения `TCP`/маркеров по известным углам суставов и `RobotGeometry` |
| `FlightRecorder` | фиксированный кольцевой буфер в RAM с последними управляющими измерениями, сохраняемый на диск только при инциденте |
| `floor_z_B` | координата плоскости пола по оси Z в `RobotBaseFrame`, начало которого находится в центре Shoulder; значение отрицательное и измеряется на конкретной сборке |
| `ForearmVector` | физический вектор направления второго кинематического звена `TCP - ElbowCenter`; в v1 исправленный `GripperCenter` обязан совпадать с кинематическим `TCP` в пределах `tcp_reference_tolerance_m` |
| `FSM` | конечный автомат; детерминированный автомат состояний системы/захвата |
| `fuzz` | автоматическое тестирование парсера большим количеством повреждённых, случайных и граничных входных данных |
| `GC` | Garbage Collector; сборщик мусора управляемой среды Unity/C#, паузы и выделения памяти которого контролируются в тестах производительности |
| `grip_actual` | фактическая нормализованная степень закрытия захвата по энкодеру и калибровке |
| `GRIP_CAL_HOME` | инженерное состояние Gripper для низкоскоростного поиска `GRIPPER_HOME`; неожиданный stall до срабатывания home остаётся неисправностью. |
| `grip_intent` | требуемая степень закрытия захвата `0..1` |
| `Gripper` | двухгубочный захват PHANTOM |
| `gripper_curve` | служебное представление нелинейной монотонной калибровочной зависимости между смещением энкодера Medium Motor D и фактическим раскрытием губок; отдельные ветви используются для открытия и закрытия |
| `GRIPPER_LEFT/RIGHT` | пара QR на жёсткой, неподвижной относительно предплечья части корпуса захвата; она не перемещается при открытии губок и после поправок задаёт `GripperCenter` независимо от текущего раскрытия |
| `GripperCenter` | вычисленная по исправленным `GRIPPER_LEFT/RIGHT` кинематическая опорная точка захвата. В protocol/kinematics v1 она **совпадает с `TCP` в пределах `tcp_reference_tolerance_m`**; ненулевой `GripperCenter→TCP` offset в v1 запрещён, иначе требуется новая non-planar/offset-aware geometry revision |
| `GripperReference` | стартовая привязка энкодера захвата к QR-измеренному фактическому раскрытию текущего запуска; стартовая hysteresis-ветвь всегда `UNKNOWN` и выбирается только первым последующим направлением движения. |
| `GRIPPER_HOME` | отдельный EV3 Touch Sensor/концевик закрытого положения захвата; используется как воспроизводимая home/reference граница при инженерной калибровке. |
| `Haptic feedback` | служебное название виброотклика Touch Plus Controller для подтверждений и предупреждений |
| `HELLO/HELLO_ACK` | обмен сообщениями для создания и проверки сетевой сессии Quest↔EV3 и `controller_boot_id` |
| `MANUAL` | Hardware-in-the-Loop; испытание ПО с реальным EV3/механикой и управляемыми входными сценариями |
| `HMAC-SHA-256` | код аутентификации сообщения на основе SHA-256; защищает datagram от подмены |
| `HMD` | Head-Mounted Display; шлем Meta Quest 3 и его отслеживаемая поза |
| `HOLD` | штатное **активное** удержание текущей физической позы программным регулятором при работоспособном `phantom-controller`; отличается от пассивного `BRAKE` |
| `HUD` | Head-Up Display; компактная панель состояния, видимая пользователю во время работы |
| `human_arm_reach` | откалиброванная рабочая длина полностью выпрямленной правой руки пользователя `Shoulder→Wrist` |
| `humanGrip` | нормализованная степень сжатия правой кисти `0..1` |
| `HumanShoulderCenter` | текущая позиция правого плечевого сустава пользователя в `LOCAL_FLOOR`, полученная из `Body_RightShoulder` |
| `HumanWristCenter` | текущая позиция отслеживаемого `Wrist` в `LOCAL_FLOOR` |
| `IK` | Inverse Kinematics, обратная кинематика: преобразование целевого положения `TCP` в углы Base/Shoulder/Elbow |
| `incident_id` | идентификатор инцидента, связывающий журналы событий EV3/Quest и сохранённые буферы `FlightRecorder` |
| `IOBT` | Inside-Out Body Tracking; более высокоточный режим Meta Body Tracking, на который PHANTOM не должен полагаться как на обязательную возможность |
| `IP` | Internet Protocol address; сетевой адрес узла, который в PHANTOM обнаруживается автоматически и не является идентификатором робота |
| `JAW_LEFT/RIGHT` | отдельная от `GRIPPER_LEFT/RIGHT` пара: по одному QR на каждой движущейся губке; используется для калибровки фактического раскрытия по нелинейной эллиптической траектории губок |
| `marker_id` | постоянный уникальный идентификатор конкретного напечатанного QR-маркера/fixture, 64-bit random value в 16 lowercase hex symbols. Он служит identity/anti-mixup полем, не является секретом, nonce или криптографической аутентификацией. Ожидаемое соответствие `marker_role ↔ marker_id` хранится в `qr_marker_manifest` конкретной `RobotGeometry`. |
| `JawContactPoint` | откалиброванная физическая точка/рабочая поверхность губки, положение которой вычисляется из QR через постоянное преобразование и используется для измерения реального зазора |
| `JointReference` | привязка абсолютного отсчёта энкодера текущего запуска к физическому углу Base/Shoulder/Elbow, установленная по QR |
| `JSON` / `YAML` | текстовые форматы конфигураций и диагностических данных; их разбор запрещён в критическом 50-Hz цикле управления моторами |
| `k_axis` | измеренный коэффициент `DriveCalibration`: физический угол выходного сустава в радианах на один отсчёт энкодера мотора |
| `L1` / `L2` | измеренные длины первого и второго кинематических звеньев PHANTOM между осями суставов |
| `Left Grip` | аналоговая кнопка Grip/Squeeze левого Touch Plus Controller; непрерывное разрешение физического движения |
| `LOCAL_FLOOR` | OpenXR система координат с устойчивой локальной системой координат и уровнем пола |
| `LOCAL_STOP` | физический локальный вход EV3, имеющий приоритет над сетевым управлением; не является сертифицированным E-stop |
| `POWER_CUT` | независимый от EV3/Linux физический способ снять энергию с приводов; доступен оператору вне swept volume и обязателен для физической квалификации v1 |
| `MEASURED` | placeholder authoring-спецификации для величины, получаемой измерением. Значение получается инженерным процессом и хранится в постоянных данных конкретного робота вне исходников; safety-critical значения обязаны быть разрешены до допуска движения. |
| `MOTION_ENABLE` | логическое разрешение исполнения движущейся цели; не является непосредственной командой мотору |
| `MotorStressScore` | leaky-integral оценка накопленной нагрузки в условных `equivalent full-duty seconds` по `duty²` и времени; используется для derating/остановки и не является измерением температуры |
| `MRUK` | Meta Mixed Reality Utility Kit; API для пространственной сцены и QR trackables |
| `MRUKTrackable` | объект MRUK для отслеживаемого QR; предоставляет позу, статус отслеживания, данные QR и границы плоскости через базовый `MRUKAnchor` |
| `Multimodal Input` | режим Meta Quest, позволяющий одновременно использовать Hand Tracking одной руки и Touch Plus другой руки |
| `OBSTRUCTION_CANDIDATE` | кратковременное защитное состояние, в котором признаки препятствия уже запрещают рост усилия, но stall ещё не зафиксирован окончательно |
| `One Euro filter` | адаптивный фильтр нижних частот для отслеживания: сильнее подавляет шум неподвижного сигнала и уменьшает сглаживание при быстром движении |
| `OpenXR` | открытый стандарт XR API, используемый приложением для базового отслеживания и ввода |
| `OVRBody` | один из возможных adapters Meta Movement SDK Body Tracking. PHANTOM не считает его автоматически совместимым с Multimodal: production provider выбирается через `TrackingQualificationProfile` и P0 exact-version qualification |
| `p95` / `p99` | 95-й/99-й процентиль измеряемой величины; используются для критериев задержки, ошибки и времени цикла |
| `passthrough` | сквозное изображение реального мира на Quest; пользователь видит физический PHANTOM и пространственный UI поверх него |
| `PD` | пропорционально-дифференциальный регулятор положения/скорости сустава на EV3 |
| `PHANTOM` | система телеуправления физическим манипулятором LEGO Mindstorms EV3 с Meta Quest 3 |
| `phantom-controller` | основной процесс EV3, который принимает команды, выполняет 50-Hz цикл управления моторами и штатно является единственным процессом, записывающим команды в выходы моторов |
| `phantom-safety` | отдельный supervisory-процесс на том же EV3, контролирующий heartbeat `phantom-controller` и выполняющий software takeover/`BRAKE`; снижает риск отказа процесса, но не является независимым аппаратным safety channel |
| `payload_confirmation_nonce` | CSPRNG 128-bit audit/correlation token `SET_PAYLOAD_STATE`. В production CONTROL его создаёт Quest только после явного действия оператора; в `COMMISSIONING/ACTUATOR_QUALIFICATION` MANUAL его создаёт авторизованный case runner только после machine-known fixture/case prerequisite текущего payload state. Это не доказательство присутствия человека, криптографическая авторизация или anti-replay механизм — эти свойства обеспечивают session/HMAC, `transaction_id` и state gates. Exact retry той же транзакции повторяет тот же nonce. |
| `PING/PONG` | пара протокольных сообщений для проверки доступности и измерения `RTT` |
| `PSK` | Pre-Shared Key; секрет для HMAC. V1 использует как минимум разные роли `control` и `commissioning`, чтобы инженерные команды не были доступны обычной управляющей сессии. |
| `PWM` / `duty` | управляющее воздействие на мотор; `duty` задаётся в процентах `-100..100`; Quest его не передаёт |
| `q_actual` | текущая оценка физических углов суставов из абсолютных энкодеров, `DriveCalibration`, `JointReference` и модели люфта |
| `q_qr` | физические углы суставов, измеренные Quest по QR в остановленном состоянии; являются независимыми от motor encoder, но не от QR/Quest sensor stack |
| `q_ref` | локальная сглаженная опорная траектория EV3 после ограничений скорости/ускорения |
| `q_target` | целевые физические углы Base/Shoulder/Elbow, вычисленные Quest |
| `QR` | Quick Response code; визуальный маркер, распознаваемый Quest во время инженерной калибровки и привязки при запуске |
| `QrMarkerCenter` | геометрический центр квадратного QR-символа; размерная точка крепления и расчётов PHANTOM |
| `QrMarkerFrame` | локальная система координат QR-маркера с началом в `QrMarkerCenter` |
| `Quest 3` | Meta Quest 3; XR-шлем, выполняющий отслеживание, распознавание QR, отображение движения/IK и пользовательский интерфейс |
| `RAM` | оперативная память; используется для ограниченных рабочих буферов и `FlightRecorder` без постоянной записи на SD-карту |
| `READY` | product-level состояние полностью собранного/откалиброванного PHANTOM с валидной CONTROL session/reference, **явно выбранными совместимыми PayloadProfile/JointSafeSet**, startup-подтверждённым `PayloadState=EMPTY|LOADED` и без stop/fault. `READY` означает готовность оценивать motion gates, а не безусловное actuator authority: после уже состоявшегося запуска смена profile/contact/release может снова установить `PayloadState=UNKNOWN`; в таком runtime `READY/HOLD` A/B/C motion запрещён до нового confirmation. Startup никогда не подставляет `EMPTY` profile/state оптимистически: до выбора profile и подтверждения state система остаётся `ROBOT_CALIBRATION`/не-READY |
| `Release` | штатный профиль сборки с минимальной стоимостью логирования/диагностики |
| `robot_id` | постоянный логический идентификатор конкретного PHANTOM в локальной сети; не равен IP-адресу |
| `RobotBaseFrame` | неподвижная система координат PHANTOM с началом в центре Shoulder; строится по `SHOULDER_LEFT/RIGHT` и вертикали `LOCAL_FLOOR` |
| `RobotGeometry` | измеренная геометрия конкретной сборки: оси, длины звеньев, TCP, QR-крепления и `RobotCollisionModel`. |
| `RobotCollisionModel` | консервативная геометрическая модель коллизий Base/Upper Arm/Forearm/Gripper в виде ограниченного набора примитивов; используется Quest для workspace-проверки и генерации EV3 `JointSafeSet`. |
| `SafetyEnvelope` | versioned набор независимых safety-critical ограничений конкретной механической/электрической конфигурации: joint/cable bounds, payload/swept-volume/pinch margins, motor/battery/commissioning hard limits и обязательность `POWER_CUT`; входит в semantic `CommissioningBundle` и проверяется EV3 локально там, где применимо |
| `JointSafeSet` | локально проверяемое EV3 множество допустимых сочетаний углов суставов, сгенерированное из `RobotCollisionModel` и safety margin; защищает от опасных межзвенных/половых коллизий даже при ошибке Quest. |
| `RobotLocalization` | преобразование между `LOCAL_FLOOR` и `RobotBaseFrame`, вычисленное по опорной паре `SHOULDER_LEFT/RIGHT` |
| `RSS` | Resident Set Size; фактический объём оперативной памяти процесса EV3, контролируемый в серии ограниченных ресурсных cases |
| `RTT` | Round-Trip Time; измеренное время прохождения `PING→PONG` по сети туда и обратно |
| `SAFE_HOLD` | безопасное удержание после временной ошибки отслеживания, сети или среды выполнения |
| `sample_id` | уникальный идентификатор атомарного снимка энкодеров, предотвращающий связывание QR-измерения с другим моментом времени |
| `SD` | microSD EV3; постоянное хранилище ПО, конфигураций и журналов инцидентов |
| `SDK` | Software Development Kit; набор библиотек и API платформы |
| `session_id` | криптографически случайный 128-битный идентификатор **одной** логической сессии Quest↔EV3; генерируется EV3 после валидного `HELLO`, возвращается в `HELLO_ACK` и никогда не выбирается клиентом |
| `SET_DRIVE_CALIBRATION` | инженерная транзакция атомарного сохранения проверенной двунаправленной `DriveCalibration` после проверки на независимых контрольных позициях |
| `SET_JOINT_REFERENCE` | транзакция привязки при запуске, связывающая измеренные после остановки `q_qr`/раскрытие губок и атомарный снимок энкодеров |
| `Shoulder` | плечевой силовой сустав PHANTOM |
| `SHOULDER_LEFT/RIGHT` | неподвижная относительно основания пара QR по сторонам Shoulder; после поправок её середина задаёт `ShoulderCenter`, а поперечный вектор вместе с OpenXR `LOCAL_FLOOR +Y` задаёт неподвижный `RobotBaseFrame` через явный Y-up→Z-up adapter |
| `TURRET_LEFT/RIGHT` | отдельная пара QR на вращающейся вместе с Base-yaw части turret; её исправленный поперечный вектор задаёт физический `q_base_qr` независимо от наклона Upper Arm |
| `ShoulderCenter` | вычисленный физический центр оси Shoulder, полученный как середина исправленных точек `SHOULDER_LEFT/RIGHT` |
| `Space Setup` | стандартная системная процедура Meta Quest для Scene/Room-функций. В v1 она не является обязательным gate обычного управления: actuator path требует `LOCAL_FLOOR`, Spatial Data permission и работоспособный QR Trackable service; сохранённая room mesh/floor anchor нужна только опциональным scene-aware UX-функциям. |
| `GripRemapProfile` | опциональный пользовательский профиль монотонного affine remap стандартного OpenXR `grasp_ext/value`; по умолчанию используется identity `[0,1]→[0,1]`, remap не является обязательной калибровкой. |
| `IGripSignalProvider` | интерфейс источника `graspValue/graspReady`; основной v1 backend — `OpenXrGraspProvider`, альтернативный backend допускается только как отдельно квалифицированный build profile, без незаметного runtime-переключения. |
| `XrSpaceBridge` | единственный adapter, приводящий Wrist, Body Tracking и QR poses к одному `LOCAL_FLOOR`/`t_control`; запрещает смешивать Unity world/TrackingSpace координаты напрямую в actuator path. |
| `P0CompatibilityScope` | scope-specific Quest platform compatibility gate: `COMMISSIONING_QR` для QR/MRUK/OpenXR commissioning path без Body/Hand, `D_ONLY_USER` для grasp+левого Touch+Multimodal D-only path и `FULL_ARM_USER` для Wrist+Body_RightShoulder+Multimodal A/B/C path. Неиспользуемые providers получают `N_A(OUT_OF_SCOPE)`, а не `FAIL`. |
| `QualificationEvidenceManifest` | canonical versioned manifest доказательств физической qualification конкретного полного semantic component set. Он ссылается на hashes mechanical revision, `RobotGeometry`, `DriveCalibration`, `RobotCollisionModel`, `SafetyEnvelope`, всех production PayloadProfile/JointSafeSet, exact build/platform matrix и обязательных MANUAL/P0 reports. `qualification_only=false` production bundle может быть создан только после PASS manifest; его `qualification_evidence_manifest_hash` входит в semantic `CommissioningBundle`. Qualification-only bundles используют тот же candidate component set, но не являются production evidence сами по себе. |
| `PayloadProfile` | versioned semantic профиль допустимого класса нагрузки: `id`, mass/CoG envelope, conservative motion/duty scale, payload collision primitive/`JointSafeSet` и feed-forward parameters/model reference. `EMPTY` — отдельный обязательный профиль. В production используются только profiles, покрытые текущим `QualificationEvidenceManifest`; до promotion full qualification может использовать candidate profiles только внутри `qualification_only=true` bundle. |
| `PayloadState` | консервативное состояние фактической нагрузки `EMPTY`, `LOADED` или `UNKNOWN` для выбранного `PayloadProfile`. После boot/controller continuity loss runtime profile=`UNSELECTED`, active safe-set hash=0, state=`UNKNOWN`; optimistic auto-`EMPTY` запрещён. Production startup после QR-reference выполняет profile selection и явное `EMPTY/LOADED`, и только после обоих ACK возможен `READY`; далее production transitions — только `READY/HOLD`. Engineering exception существует только в `COMMISSIONING/ACTUATOR_QUALIFICATION`: narrow A/B/C — explicit `EMPTY/EMPTY`, full `0x0F` — candidate `EMPTY/LOADED` qualification transitions при stationary/dearmed/local-authorized gates. Любой переход arm-invalidating; `UNKNOWN` никогда не разрешает A/B/C motion. |
| `LOCAL_COMMISSION_ARM` | локальный ограниченный по времени допуск engineering commissioning, активируемый только физическими кнопками EV3; не может быть включён сетью. |
| `STOPPED` | движение запрещено локальной остановкой или процедурой, требующей явного восстановления |
| `sysfs` | файловый интерфейс Linux/ev3dev для чтения энкодеров и управления моторами; файлы открываются заранее до критического цикла |
| `TCP` | Tool Center Point; рабочая точка в центре захвата |
| `TELEMETRY` | компактная штатная телеметрия EV3 для управления состоянием и UI |
| `Touch Plus` | контроллер Meta Quest Touch Plus; в PHANTOM левый контроллер используется для `Left Grip`, UI и виброотклика |
| `TRACKING` | состояние активного следования робота за текущим вектором правой руки после явного re-arm и нового фронта `Left Grip` |
| `UDP` | User Datagram Protocol; транспорт команд и телеметрии Quest↔EV3 |
| `UI` | User Interface; пользовательский интерфейс приложения Quest |
| `UpperArmVector` | физический вектор направления верхнего звена `ElbowCenter - ShoulderCenter` |
| `USB` | интерфейс EV3 USB Host, к которому подключается штатный Wi-Fi-модуль |
| `watchdog` | таймер контроля свежести команд/heartbeat; при превышении тайм-аута переводит систему в безопасное состояние |
| `Wrist` | отслеживаемый OpenXR-сустав правого запястья; управляющая точка человеческой руки |
| `WMM` | Wide Motion Mode Meta Hand Tracking; режим, использующий body-assisted оценку положения руки вне прямого поля зрения. В actuator profile PHANTOM v1 выключен; runtime не должен незаметно подменять им прямой Wrist path. |
| `XR` | Extended Reality; общее обозначение пространственной среды выполнения и API шлема |
| Инженерная калибровка | процедура после сборки или изменения механики, создающая/обновляющая `RobotGeometry`, `DriveCalibration` и безопасные границы |

<a id="sec-11-1"></a>
## 2. Формулы

<a id="sec-11-1-1"></a>
### 2.1. Абсолютное отображение движения пользователя

Абсолютная цель, масштабирование, ограничение длины и обработка почти нулевого
вектора определены в [Спецификации Quest §10](quest-specification.md#sec-5-10).
Разделение pure request и фильтрованной управляющей цели — в
[Спецификации Quest §4.3](quest-specification.md#sec-5-4-3).
`Left Grip` разрешает выполнение цели и не меняет её origin/offset.

<a id="sec-11-1-2"></a>
### 2.2. IK

Уравнения обратной кинематики и численные допуски: [Спецификация Quest §13.1](quest-specification.md#sec-5-13-1).
Перед вычислением применяется проверка yaw singularity и workspace из [Спецификация Quest §14](quest-specification.md#sec-5-14).

<a id="sec-11-1-3"></a>
### 2.3. FK

Уравнения прямой кинематики и система координат: [Спецификация Quest §13.2](quest-specification.md#sec-5-13-2).
FK преобразует `q_actual` в расчётное положение TCP для отображения и проверки геометрии.

<a id="sec-11-1-4"></a>
### 2.4. QR↔энкодерная инженерная калибровка

Модель передачи и люфта определяется при инженерной калибровке
[Quest §16.5](quest-specification.md#sec-5-16-5). Текущая привязка и вычисление
`q_actual` из абсолютного encoder count принадлежат
[EV3 §5.4](ev3-specification.md#sec-7-5-4) и
[EV3 §5.5](ev3-specification.md#sec-7-5-5).
Скорость не интегрируется в положение; перезапуск требует новой привязки.

<a id="sec-11-1-5"></a>
### 2.5. Захват

Безопасный encoder travel, две калибровочные ветви раскрытия и восстановление
расстояния между губками при неизвестном предыдущем направлении определены в
[Спецификации EV3 §6](ev3-specification.md#sec-7-6).
Поведение контакта и открывания — в [Спецификации EV3 §15](ev3-specification.md#sec-7-15).
Абсолютный count инженерной сессии не является границей следующего запуска.

<a id="sec-11-1-6"></a>
### 2.6. Номинальная скорость передачи

Для механического sanity check:

```text
omega_joint[rpm] = omega_motor[rpm] / R_nominal
omega_joint[deg/s] = omega_motor[rpm] * 6 / R_nominal
```

Управление углом использует измеренный `k_axis`, а не только `R_nominal`.

<a id="sec-11-1-7"></a>
### 2.7. Статический момент

```text
tau ≈ m * g * r
```

Формула применяется при расчёте собственного веса подвижных узлов и настройки противовеса.

<a id="sec-11-6"></a>
## 3. Параметры, фиксируемые измерением

| Параметр | Процедура |
|---|---|
| `L1`, `L2`, `robot_nominal_reach_m`, `yaw_singularity_hold_radius_m`, `floor_z_B`, `TCP` | инженерная калибровка `RobotGeometry` + kinematic conditioning/workspace MANUAL |
| координаты креплений QR | инженерная калибровка `RobotGeometry` |
| `k_base`, `k_shoulder`, `k_elbow` | двунаправленная многопозиционная QR↔энкодерная `DriveCalibration` |
| `backlash_half_angle` A/B/C | прямой/обратный QR↔энкодерный проход + контрольные положения |
| нелинейные кривые `d_counts→opening`, calibration-session `E_closed_cal` по GRIPPER_HOME, QR-зазор в authoritative `D_open_counts` endpoint и люфт | автоматическая QR-калибровка Gripper по [Спецификация Quest §16.8](quest-specification.md#sec-5-16-8); curve-domain сверяется с SafetyEnvelope |
| пороги jitter QR, pair baseline, residual, conditioning и propagated joint-angle uncertainty | квалификация QR + повторные тесты запуска |
| `RobotCollisionModel`, `JointSafeSet`, general floor/collision margins и `tcp_floor_clearance_m` | CAD/измеренная механика + exhaustive simulation + MANUAL boundary tests |
| PayloadProfiles, PayloadState policy и допустимые масса/CoG/motion scale | статические/динамические нагрузочные MANUAL-тесты каждого разрешённого класса + state-transition tests |
| JointSafeSet grid resolution/inflation/max bytes | exhaustive offline collision generation + boundary MANUAL; unsafe false-negative запрещён |
| Quest pinned platform matrix / `P0CompatibilityScope` | scope-specific P0 на реальном Quest 3: `COMMISSIONING_QR`, `D_ONLY_USER`, `FULL_ARM_USER`; изменение exact matrix инвалидирует применимые PASS |
| пределы первого/последующих `CALIBRATION_JOG`: изменение энкодера, время, скорость, `duty`, критерий остановки | моторный стенд + поэтапная QR-калибровка, начиная с консервативного малого перемещения |
| `gripper_open_limit_delta_counts`, calibration duration/speed/duty bounds | безопасный пустой Gripper стенд/fixture: open endpoint доказывается независимо от QR-кривой, затем repeated MANUAL подтверждает монотонность/безопасность всего диапазона |
| `wrist_dropout_grace_ms`, `shoulder_dropout_grace_ms`, пределы временного согласования и экстраполяции Shoulder/Wrist | replay dropout/timestamp сценариев + физические тесты движения |
| `max_mapping_scale`, `human_vector_min_m` | replay/property tests noise amplification + physical mapping MANUAL; scale ceiling не может превышаться даже при малом `human_arm_reach` |
| параметры адаптивного фильтра и допустимая добавленная задержка | воспроизведение отслеживания + физические тесты Quest |
| механические ограничители Base / безопасный кабельный диапазон | измерение на собранной механике |
| фиксация основания / slip относительно `LOCAL_FLOOR` при worst-case квалифицированных траекториях и payload | MANUAL/механический тест фиксации; смещение должно оставаться внутри бюджета RobotLocalization/коллизий, а наблюдаемое/подозреваемое ослабление требует re-localization |
| `power_cut_max_disconnect_ms` | instrumented MANUAL: физический `POWER_CUT` actuation → подтверждённое снятие энергии с приводов |
| `local_stop_response_limit_ms` | hazard/stopping-distance qualification + instrumented healthy/forced `LOCAL_STOP` process tests; software-response измеряется отдельно от physical time-to-rest |
| `power_loss_peak_tcp_speed_limit_mps` | hazard/stopping-distance/containment qualification конкретной mechanical revision + instrumented power-loss MANUAL для EMPTY и каждого разрешённого PayloadProfile; предел фиксируется до физической приёмки и пересматривается при изменении массы/балансировки/передачи/payload envelope |
| `rx_rate_limit_pps`, `rx_burst_packets` | EV3 MANUAL flood sweep valid/invalid traffic при одновременном 50-Hz motor-loop timing; выбирается максимум, сохраняющий parser/network/loop budgets |
| нейтраль Shoulder и максимальное безопасное сгибание | механическая и QR-калибровка |
| разогнутое направление Elbow и максимальное безопасное сгибание | механическая и QR-калибровка |
| пределы `duty`, удержания, выбора люфта и скорости изменения `duty` | нагрузочные тесты осей и реверса |
| `kp_duty_permille_per_rad`, `kd_duty_permille_per_rad_s`, velocity-filter/friction parameters и `FeedForwardMap` torque→duty/battery domain+hash | нагрузочные MANUAL осей в диапазоне поз/скоростей/напряжений; property test запрещает смешение N·m и duty permille |
| production `user_max_vel/user_max_accel` каждой оси (не выше design ceilings [Спецификация EV3 §10](ev3-specification.md#sec-7-10)) | динамические MANUAL tracking/braking/stop tests для EMPTY и применимых PayloadProfile |
| `tracking_error_limit/timeout`, `obstruction_candidate_ms`, `main_joint_stall_ms`, stall speed/duty predicates | controlled obstruction/stall MANUAL по каждой оси с nominal/backlash/noise cases; универсальные hard-coded defaults запрещены |
| Gripper `max_speed_counts_s`, contact predicates (`contact_min_travel_ratio`, duty/speed/error thresholds, `contact_confirm_ms`) и `release_intent_hysteresis` | [Метрики и анализ §4.8.5](metrics-and-logs.md#sec-9-16-6) open/close/contact/jam/release dataset; false contact <=1/100 и opening jam never contact |
| `controller_heartbeat_timeout_ms`, `controller_watchdog_takeover_limit_ms` | instrumented SIGSTOP/deadlock controller MANUAL: heartbeat loss → watchdog expiry → safety takeover zero/brake command; выбираются вместе с 20-Hz heartbeat jitter и stopping-distance evidence |
| пороги `MotorStressScore`, restart floor/cooldown и persistence policy | повторные тесты высокой нагрузки/удержания, reboot при WARN/CRITICAL и подтверждение fail-closed восстановления |
| пороги NORMAL/DERATED/SAFE_HOLD/`FAULT_BATTERY_LOW`, debounce/fault timing по батарее | нагрузочные тесты при пониженном напряжении |
| период опроса питания и допустимый возраст успешного измерения | [Метрики и анализ §4.9](metrics-and-logs.md#sec-9-17): ошибка/зависание sampler и stale snapshot не сохраняют разрешение движения; бюджет проверяется вместе с реальной частотой опроса |
| окно `FlightRecorder` до/после инцидента | MANUAL-тесты восстановления картины инцидента |
| точки крепления противовеса | тесты Shoulder HOLD |

Изменение измеряемой механики требует новой редакции соответствующей конфигурации и повторной приёмки затронутой функции.

Каждый `MEASURED` записывается непосредственно в конфигурацию владельца после измерения.
Единицы и допустимые диапазоны определяются схемой и спецификацией компонента,
процедуры — разделами калибровки и ручных проверок. Требуемое подтверждение результата
хранится в данных калибровки или отчёте, без второй копии значения в отдельном реестре.
Незаполненные safety-critical параметры блокируют допуск движения; сетевой Diagnostic
без actuator authority может проверяться до их измерения.
