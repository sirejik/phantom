# PHANTOM — инварианты безопасности

Нормативные сквозные инварианты безопасности и быстрые gates перед движением. Детальные component safety rules остаются в соответствующих component specs.

<!-- BEGIN GENERATED TOC -->
<details>
<summary>Оглавление</summary>

- [1. Инварианты безопасности и управления](#sec-11-3)
- [2. Быстрая проверка перед движением](#sec-11-4)
  - [2.1. Полный `READY/TRACKING`](#sec-11-4-1)
  - [2.2. Gripper-only `COMMISSIONING/ACTUATOR_QUALIFICATION`](#sec-11-4-2)

</details>
<!-- END GENERATED TOC -->

<a id="sec-11-3"></a>
## 1. Инварианты безопасности и управления

```text
S1  Нет валидного Left Grip/разрешения → нет нового движения.
S2  Один и тот же shoulder→Wrist vector → одна и та же математическая TCP target.
S3  Физическая поза робота при включении движения не становится coordinate origin.
S4  Старый/replayed packet → нет изменения цели.
S5  Неверный HMAC/session/boot id → нет actuator change.
S6  Нет JointReference → A/B/C не двигаются автоматически.
S7  Нет GripperReference → D не двигается автоматически.
S8  HOLD/SAFE_HOLD отменяют старую движущуюся цель.
S9  После SAFE_HOLD/arm-invalidating event движение не возобновляется автоматически: причина должна быть устранена, Quest должен увидеть Grip released, передать OFF/HOLD и получить свежую telemetry текущей session с `last_accepted_command_sequence >= release_off_sequence`; только затем `armed=true` и новый rising edge. Потерянный OFF/HOLD/stale telemetry/reconnect не считаются re-arm. Latched fault condition дополнительно держит `state=STOPPED` и требует предусмотренный ACK/maintenance.
S10 Main-joint stall никогда не считается gripper contact.
S11 QR не является 50-Hz servo feedback.
S12 После механического вмешательства или подозрения на пропуск передачи движение запрещено до новой QR-привязки.
S13 `Release`/`Diagnostic` используют один product control/state/safety core и не могут различаться safety predicates или actuator result для одинакового product-mode input; `Diagnostic` дополнительно может экспонировать qualification-only engineering surfaces и richer diagnostics, но только с отдельной локальной авторизацией и без доступности этих surfaces в `Release`.
S14 Ошибка логирования не блокирует цикл управления моторами.
S15 RobotGeometry/DriveCalibration не меняются автоматически во время обычного движения.
S16 Кабель Base защищён физическими механическими ограничителями независимо от программного обеспечения.
S17 Программные границы Shoulder/Elbow не допускают сгибание более 90°.
S18 Безопасность при crash/power loss не зависит от активного `HOLD`; учитываются пассивная механика/`BRAKE` и независимый `POWER_CUT`.
S19 Только `phantom-controller` штатно записывает команды моторам; `phantom-safety` делает это только при аварийном перехвате.
S20 Потеря phantom-safety запрещает движение, но сам phantom-safety не считается независимым аппаратным safety channel.
S21 LOCAL_STOP имеет приоритет над сетью.
S22 `q_actual` вычисляется только из абсолютного отсчёта энкодера, `DriveCalibration` и текущей привязки; скорость мотора не интегрируется в положение.
S23 Калибровочное QR-измерение принимается только после полной остановки оси и устойчивого многомаркерного расчёта.
S24 Признак препятствия запрещает дальнейшее наращивание усилия; подтверждённое заклинивание прекращает движение без автоматического повторного продавливания.
S25 Критический инцидент сначала обрабатывается контуром управления и безопасности и только затем записывается на диск.
S26 OpenXR `LOCAL_FLOOR` трактуется как Y-up; внутренняя Z-up кинематика получает данные только через явный coordinate adapter.
S27 Одинаковый валидный input не может получать разный q_target из-за предыдущего Base yaw в singularity.
S28 Actuator input разрешён только при совпадении runtime/SDK/feature flags с квалифицированным `TrackingQualificationProfile`; приложение не выдумывает per-sample provenance, отсутствующий в API.
S29 HMAC не считается механизмом confidentiality; v1 требует доверенную/изолированную LAN.
S30 Неизвестный safety-critical `MEASURED` запрещает READY.
S31 Превышение квалифицированного payload/swept-volume envelope запрещено.
S32 Каждый исполняемый A/B/C `q_target` и каждый промежуточный `q_ref` принадлежит локальному EV3 `JointSafeSet`; D-only scope не использует joint-space `q_ref`.
S33 `GRIPPER_HOME`, а не stall, является closed reference Gripper; stall до home = fault.
S34 Session id генерируется только EV3 после authenticated HELLO; client nonce retry идемпотентен лишь в bounded retry-window, а новая session никогда не наследует старые sequence/targets/armed/release state. Recovery-only CONTROL session в STOPPED не имеет actuator authority до очистки blocking latches и deliberate re-arm.
S35 Войти в `COMMISSIONING` одной UDP-командой невозможно: `LOCAL_COMMISSION_ARM` создаётся только локальным ENTER+UP. Нормальный вход выполняется в `DISCOVERY`; если после добровольно оставленной CONTROL session EV3 локально остаётся в `HOLD`, fresh CONTROL owner должен уже отсутствовать, а тот же физический gesture сначала локально переводит `HOLD→DISCOVERY`, затем открывает bounded arm-window. `HELLO role=COMMISSIONING` обязан consume это окно; перейти в `ACTUATOR_QUALIFICATION` также нельзя без отдельного локального ENTER confirmation.
S36 Любой reference-space change/resume снимает motion permission и требует deliberate re-arm; в полном A/B/C path старая `RobotLocalization` инвалидируется и используется `SAFE_HOLD/HOLD`, а D-only qualification не требует `RobotLocalization`, но остаётся dearmed до повторной проверки применимых inputs.
S36a Физическое перемещение/поворот/ослабление основания после `RobotLocalization` инвалидирует её; motor encoder continuity не делает старую localization валидной. A/B/C motion запрещён до повторной фиксации и новой QR localization.
S37 Room mesh/Scene floor anchor не является обязательным условием core actuator path.
S38 `P_requested_B` является pure function aligned Shoulder/Wrist + static mapping config; tracking filter state не меняет эту математическую цель.
S39 В full-arm path during Shoulder/Wrist dropout grace stale joint никогда не комбинируется со fresh second joint; замораживается последняя aligned actuator target. Это не применяется к D-only scope, где actuator input — grasp.
S40 В эксплуатации PayloadProfile/PayloadState меняются только в `READY/HOLD` при stationary motors; startup-исключение в `ROBOT_CALIBRATION` разрешает последовательные `SET_PAYLOAD_PROFILE` → `SET_PAYLOAD_STATE=EMPTY|LOADED` после full reference/localization и до `READY`. Engineering-исключение существует только в `COMMISSIONING/ACTUATOR_QUALIFICATION`: narrow A/B/C — строго EMPTY/EMPTY, full 0x0F — квалифицируемые EMPTY/LOADED transitions при полной reference, stationary motors, local authority и снятом motion-arm; wire state остаётся COMMISSIONING. Любой profile/state transition снимает armed-latch. Release payload сначала замораживает A/B/C и открывает только D; после снятия контакта остаётся UNKNOWN до явного EMPTY.
S41 State-changing transactions строго one-in-flight и возрастают без дырок. Любой operation-level ACK для нового id (успех или детерминированная semantic error) завершает/consume-ит transaction и кэширует id/hash/ACK payload; pre-transaction bad HMAC/session/sequence/exact-length drop id не consume-ит. Retry completed id не повторяет side effect; corrected payload после error использует следующий id.
S42 `JointSafeSet` runtime format v1 — GRID3D_V1 для активного PayloadProfile; q_ref path не перескакивает unsafe cells.
S43 Reboot не обнуляет накопленную motor-stress protection: warning/critical checkpoint восстанавливается fail-closed по restart floor/cooldown policy.
S44 Ось вне actuator_scope_mask никогда не получает nonzero motor write; motor authority задаётся только versioned bundle/config и не расширяется сетью. safety_observation_mask может требовать чтение реального q disabled оси для coupled-safety, но никогда не даёт ей motor write.
S45 D-only qualification может двигать Gripper при JointReference A/B/C invalid, но только при валидных DriveCalibration[D]+GripperReference и commissioning qualification gates; READY при этом запрещён.
S46 DNS-SD v1 использует service type `_phantom-ev3._udp` и domain `local.` отдельно; control transport v1 — IPv4-only до отдельной qualification.
S47 `phantom-network` не имеет motor-write authority; controller повторно валидирует bounded IPC/session/sequence/age/scope/re-arm перед принятием target, а IPC failure fail-safe эквивалентен отсутствию свежей команды.
S48 `quest_build_id` и `ev3_build_id` являются разными component/profile identities; release evidence связывает их общими protocol/config identities и exact artifact hashes, а не равенством IDs или обязательным общим Git commit.
S49 Нельзя удерживать неоткалиброванную нагрузочную ось q-based controller-ом как prerequisite к калибровке другой оси; до собственной calibration/reference она механически фиксируется/поддерживается.
S50 Derived content hash никогда не входит в bytes собственного semantic payload; CommissioningBundle/component identity не может быть рекурсивным self-hash.
S51 После boot/controller continuity loss active payload profile становится UNSELECTED, active safe-set hash=0, PayloadState=UNKNOWN; READY запрещён до нового startup profile selection **и** явного startup EMPTY/LOADED confirmation. После READY runtime-события могут снова установить UNKNOWN; A/B/C TRACKING остаётся запрещён до следующего явного confirmation. Смена profile или object/early contact также устанавливает UNKNOWN.
S52 После controller_boot_id change старые CONTROL/COMMISSIONING sessions, JointReference и GripperReference недействительны независимо от сохранности motor encoder counts.
S53 Всегда actuator_scope_mask ⊆ safety_observation_mask. При partial A/B/C ACTUATOR_QUALIFICATION safety_observation_mask включает 0x07|actuator_scope_mask; q disabled A/B/C берётся из локальной reference/encoder модели и входит в JointSafeSet, а нагрузочная disabled ось fixture/support-ится. Wire zero не может заменить физический fixed joint state.
S54 Retry state transaction сохраняет semantic ACK payload/result, но никогда не replay-ит старую wire datagram: каждый EV3→Quest ответ имеет новый sequence/timestamp/HMAC.
S55 Idempotency state-changing transaction ограничена текущей session. После session loss операция с физическим side effect и неизвестным исходом, особенно CALIBRATION_JOG, не может автоматически повторяться; сначала восстанавливается наблюдаемое физическое состояние.
S56 `phantom-network` не может единолично создать CONTROL/COMMISSIONING actuator authority: session становится authoritative только после controller-side SESSION_OPEN_ACCEPT, а commissioning требует consume свежего физического LOCAL_COMMISSION_ARM controller-ом.
S57 Incremental partial A/B/C ACTUATOR_QUALIFICATION является EMPTY-only: narrow motor authority требует явных engineering EMPTY profile+state gates и не разрешает LOADED/non-EMPTY payload, pickup/release или расширение safety envelope. Payload MANUAL допускается только в full 0x0F/0x0F qualification bundle с отдельными commissioning payload transactions.
```

<a id="sec-11-4"></a>
## 2. Быстрая проверка перед движением

Проверка зависит от режима; нельзя применять production checklist к раннему стенду и затем обходить пункты вручную.

<a id="sec-11-4-1"></a>
### 2.1. Полный `READY/TRACKING`

```text
[ ] Quest spatial permission granted
[ ] LOCAL_FLOOR valid; QR capability доступна для требуемой привязки, после принятой привязки QR Tracking отключён
[ ] expected robot_id discovered; authenticated CONTROL session valid
[ ] qualification_only=false; actuator_scope_mask=0x0F; safety_observation_mask=0x0F; qualification_evidence_manifest_hash valid/nonzero и относится к текущему semantic component set
[ ] P0CompatibilityScope=FULL_ARM_USER PASS для exact installed platform matrix
[ ] complete CommissioningBundle/RobotGeometry/DriveCalibration hashes compatible
[ ] RobotLocalization valid
[ ] JointReference A/B/C valid
[ ] GripperReference valid
[ ] Body_RightShoulder + Wrist current/valid; temporal alignment valid
[ ] пользователь присутствует; presence/lifecycle состояние достоверно для пользовательского движения
[ ] human_arm_reach valid
[ ] IGripSignalProvider ready; optional GripRemapProfile valid/compatible or disabled
[ ] startup не использовал optimistic EMPTY: после boot profile был UNSELECTED; затем active PayloadProfile/JointSafeSet/CollisionModel явно выбран/валиден; до входа в `READY` PayloadState explicitly confirmed `EMPTY` or `LOADED` (not `UNKNOWN`); no payload transition/release interlock pending
[ ] MotorStressScore of every axis/battery/loop health permit motion
[ ] Base cable service loop free
[ ] workspace free of people/unexpected obstacles; operator outside swept/pinch zones
[ ] LOCAL_STOP released; GRIPPER_HOME healthy; POWER_CUT checked
[ ] no latched fault
[ ] после последнего arm-invalidating event Left Grip фактически отпущен; свежая TELEMETRY текущего boot/session подтверждает принятие OFF/HOLD по last_accepted_command_sequence >= release_off_sequence; движение требует следующего нового нажатия
```

<a id="sec-11-4-2"></a>
### 2.2. Gripper-only `COMMISSIONING/ACTUATOR_QUALIFICATION`

```text
[ ] build_profile=Diagnostic
[ ] qualification_only=true; actuator_scope_mask=0x08; safety_observation_mask=0x08
[ ] P0CompatibilityScope=D_ONLY_USER PASS; для новой QR-driven commissioning calibration также актуален COMMISSIONING_QR PASS
[ ] OpenXR session/focus valid; Hand/grasp + left Touch Plus + Multimodal scope prerequisites valid
[ ] QR Trackable capability valid until current-run GripperReference is accepted
[ ] expected robot_id discovered; authenticated COMMISSIONING session valid
[ ] current bundle hash matches on Quest/EV3
[ ] Motor D present/type/count_per_rot valid
[ ] DriveCalibration[D] compatible and validated
[ ] GripperReference current-run valid
[ ] GRIPPER_HOME healthy
[ ] grasp provider ready; GRASP_VALID current
[ ] left Touch Plus present
[ ] пользователь присутствует; presence/lifecycle состояние достоверно для пользовательского движения
[ ] commissioning session создана из локального ENTER+UP arm-window; session-local authority current
[ ] пользователь выполнил local ENTER qualification confirmation; fresh TELEMETRY bit9 подтверждает authoritative ACTUATOR_QUALIFICATION phase; qualification_armed=false
[ ] после local ENTER при фактически отпущенном Left Grip Quest получил fresh TELEMETRY текущей session с last_accepted_command_sequence >= release_off_sequence для своего OFF/HOLD COMMAND; только после этого armed=true, и лишь следующий rising edge может разрешить motion
[ ] LOCAL_STOP released; POWER_CUT checked; pinch zone clear
[ ] safety supervisor/watchdog/battery/loop health permit motion
[ ] no latched fault
[ ] A/B/C are out of scope and hard-inhibited; nonzero writes = 0
```

Для этого checklist **не требуются** `RobotLocalization`, `JointReference A/B/C`, Body Shoulder/Wrist, `human_arm_reach`, PayloadProfile или `JointSafeSet`, потому что ни один из них не участвует в D-only actuator path.
