# Quest implementation status

Нормативные требования находятся только в `PHANTOM_SPECIFICATION.md`. Этот файл
фиксирует текущее состояние реализации этапов 1–2 и не заменяет test evidence.

## Реализовано

- Unity/OpenXR observation-only runtime без motor authority;
- адаптер `LOCAL_FLOOR` и канонической системы координат;
- правый Wrist/grasp, левый Touch Plus и fail-closed state machine;
- MRUK QR adapter для десяти идентификаторов;
- полные position+rotation poses всех QR в snapshot-контракте;
- `RobotBaseFrame`, `q_base_qr`, `ShoulderCenter`, `ElbowCenter` и
  `GripperCenter`; `GRIPPER_*` отделены от движущихся `JAW_*`;
- pure IK/FK, абсолютный mapping, калибровка длины руки и synthetic tests;
- generated HMAC protocol v1, PC EV3 simulator и UDP integration tooling;
- Release/Diagnostic batch build, manifest/hash и Android permission audit.

Runtime этапа 2 намеренно не создаёт `RobotTransport` и не посылает команды
движения. Любая неготовность tracking/provider/QR оставляет систему вне READY.

## Непройденные аппаратные gates

- P0 на реальном Quest 3 для exact Horizon/Unity/Meta package matrix;
- одновременная работа Hand Tracking, выбранного Body Tracking provider,
  левого Touch Plus, passthrough и QR Trackables в течение 30 минут;
- pause/resume, снятие HMD, focus/reference-space lifecycle;
- установленный APK `DEVICE AUTO` и реальные camera/QR проверки.

Meta XR Core 205.0.0 содержит существенный blocker: локальная реализация
`OVRBody` отключается при `SimultaneousHandsAndControllersEnabled`. До выбора и
P0-подтверждения совместимого provider/version сочетания Quest actuator path
остаётся заблокированным. Прежние экспериментальные device runs и версии APK
не являются PASS для текущего build/spec hash.

Актуальный программный результат создаётся `scripts/pre-install-auto.ps1` и
привязывается к чистому commit, source/spec/protocol hashes и двум APK. Реальный
статус P0/DEVICE/HIL хранится отдельными отчётами и не подменяется симулятором.
