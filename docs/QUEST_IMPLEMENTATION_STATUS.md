# Quest implementation status

Нормативные требования находятся только в `PHANTOM_SPECIFICATION.md`. Этот файл
фиксирует текущее состояние реализации этапов 1–3 и не заменяет test evidence.

## Реализовано

- network-only Stage-3 runtime без motor authority и без формирования `COMMAND`;
- DNS-SD abstraction с Android NSD backend и deterministic fake backend;
- bounded background UDP transport, CONTROL HELLO/HELLO_ACK session, HMAC,
  PING/PONG/RTT, TELEMETRY freshness и reconnect при loss/endpoint/boot change;
- app-private Android control credential store и ephemeral test store;
- русский network UI, structured events и bounded Quest network FlightRecorder;
- адаптер `LOCAL_FLOOR` и канонической системы координат;
- правый Wrist/grasp, левый Touch Plus и fail-closed state machine;
- MRUK QR adapter для десяти идентификаторов;
- полные position+rotation poses всех QR в snapshot-контракте;
- `RobotBaseFrame`, `q_base_qr`, `ShoulderCenter`, `ElbowCenter` и
  `GripperCenter`; `GRIPPER_*` отделены от движущихся `JAW_*`;
- pure IK/FK, абсолютный mapping, калибровка длины руки и synthetic tests;
- generated HMAC protocol v1, PC EV3 simulator и UDP integration tooling;
- Release/Diagnostic batch build, exact package matrix, embedded build/config
  identity, manifest/hash и Android permission audit;
- Quest-only `scripts/quest-pre-install-auto.ps1` и post-install
  `scripts/quest-device-auto.ps1`: admission только после matching Quest
  PRE-INSTALL PASS, установка с автоматической выдачей permissions, первый
  запуск/force-stop/relaunch, bounded wake/PID/report polling, crash audit и
  обезличенный device report; ни один AUTO не требует надеть шлем, двигать
  рукой/Touch, показать QR, подтвердить haptics или выполнить lifecycle action;
- явная классификация Body provider отделяет `API_ABSENT`, неверную
  конфигурацию, explicit SDK incompatibility, неактивные XR/focus и наличие
  live observation; лежащий HMD без live samples не создаёт software FAIL;
- Diagnostic synthetic Stage-1/2 regressions покрывают Wrist, `Body_RightShoulder`, grasp,
  левый Grip, controller disconnect, stale/fresh, tracking loss/recovery,
  focus/pause/resume, все 10 QR и partial QR rejection, fail-closed state
  machine и отсутствие motor authority;
- Diagnostic автоматически включает physical validation runner, а Release не
  активирует engineering UI; обязательный Space Setup не вызывается для
  выключенного scene-aware UX.

Stage-3 runtime создаёт только discovery/session/telemetry transport и не имеет
публичного actuator command path. Профиль `Diagnostic`,
`qualification_only=true`, `actuator_scope_mask=0x00`,
`required_user_inputs=NONE` не требует tracking/provider/QR и никогда не
переходит в `READY`/`TRACKING`.

Quest-side code и host/simulator automated validation этапа 3 завершены.
Android Diagnostic и Release APK компилируются; Stage-3 operational profile
встроен в Diagnostic artifact. Реальная работоспособность Android NSD,
UDP и lifecycle на Quest 3, а также Quest↔real EV3 остаются `NOT_RUN`.
Stage 3 overall остаётся `NOT COMPLETE` до этих hardware gates.

## Аппаратные gates Quest 3

- `DEVICE AUTO` на реальном Quest 3 запускается с лежащим HMD, устанавливает
  exact APK, подтверждает identity/permissions/config/adapters и перезапуск без
  crash, но software compatibility итог — `FAIL` из-за explicit `OVRBody`
  guard; XR/focus/live observations при этом являются отдельным non-blocking
  environment evidence;
- связанный P0 для exact Horizon/Unity/Meta package matrix — `FAIL`, а не
  `NOT_RUN`: prerequisite Body provider несовместим с требуемым Multimodal;
- bounded (`<=60 s`) live cases одновременной работы Hand Tracking, выбранного
  Body Tracking provider, левого Touch Plus, passthrough и QR Trackables;
- pause/resume, снятие HMD, focus/reference-space lifecycle;
- реальные camera/QR проверки с напечатанными маркерами.

Meta XR Core 205.0.0 содержит существенный blocker: локальная реализация
`OVRBody` отключается при `SimultaneousHandsAndControllersEnabled`; это
подтверждено `OVRBody.OnEnable`, обязательным Meta Project Setup rule и реальным
device report. Source-only проверка ближайшего кандидата Meta XR Core 85
обнаружила тот же guard, поэтому downgrade/build не выполнялся. До выбора и
P0-подтверждения совместимого
provider/version сочетания Quest actuator path остаётся заблокированным.
Прежние экспериментальные device runs и версии APK не являются PASS для
текущего build/spec hash.

Проверенные provider candidates:

| Matrix | Дешёвая source/config проверка | Решение |
|---|---|---|
| Meta XR Core `205.0.0`, `OVRBody`, Multimodal required | pinned package source: explicit disable в `OVRBody.OnEnable` и Required project-setup error | несовместима; device build нужен для доказательства runtime-классификации |
| Meta XR Core `85.0.0`, `OVRBody`, Multimodal required | официальный Unity tarball (`shasum f8b4cfb2789f06cb55ea30b9a379bf52c98d1af3`) содержит тот же guard | отклонена до APK build; не устраняет конфликт |

Источник candidate package — `https://packages.unity.com/com.meta.xr.sdk.core`.

Актуальный Quest-only программный результат создаётся
`scripts/quest-pre-install-auto.ps1` и
привязывается к чистому commit, source/spec/protocol hashes и двум APK. Реальный
статус P0/DEVICE/HIL хранится отдельными отчётами и не подменяется симулятором.
