# Phantom Project Audit

> **Тип документа:** независимый технический аудит. Ненормативный. Не входит в
> `specification_sha256` и не переопределяет нормативный набор PHANTOM.
> **Дата аудита:** 2026-09-06.
> **Аудируемый срез:** `main` @ `4c842f9a` (clean worktree, 5 коммитов впереди `origin/main`).
> **Метод:** чтение исходников и документации + фактический запуск детерминированных gate-команд.

---

## 1. Executive Summary

### Общее состояние

PHANTOM — необычный проект: **документация значительно опережает реализацию, но не является
«бумажной»**. Нормативный набор (~876 KB, 12 документов) описывает полную телеуправляемую
систему Quest 3 ↔ EV3 с детальной safety-моделью, wire-протоколом, state machine и
qualification gates. Реализация (~13 200 строк исходного кода) намеренно закрывает только
этапы 1–3 (`actuator_scope_mask=0x00`, network-only, без motor authority).

Качество инженерной инфраструктуры **высокое и нетипичное для этой стадии**: schema-first
протокол с cross-language golden vectors, детерминированные build identities, воспроизводимые
generated artifacts, spec-manifest с exact-byte hashes, дисциплина `NOT_RUN` вместо
фальшивых PASS. Все проверенные мной детерминированные gate-команды действительно проходят.

Основная проблема аудита — **не качество кода, а несколько мест, где документация уверенно
описывает механизм, которого в коде нет**, и где статус/тесты создают ложное ощущение
покрытия. Три из них блокируют ближайший физический gate Stage 3.

### Соответствие документации и реализации

| Аспект | Оценка |
|---|---|
| Wire-протокол (schema → constants → golden vectors → codecs) | очень хорошее соответствие |
| Session/handshake/replay/reconnect semantics | хорошее соответствие |
| Stage-3 IPC boundary (layout, credentials, freshness, bounded drain) | соответствует, но не проверен ни одним исполненным тестом |
| Telemetry semantics | **расхождение**: state/fault/status синтезируются network-процессом |
| Configuration (§5.19 Quest, §7.21 EV3) | **существенное расхождение** в обе стороны |
| Logging / FlightRecorder / incident capture | **не реализовано** на стороне controller |
| Credential provisioning (Quest) | **не реализовано** |
| Mapping/IK формулы (§11.1) | IK/FK точно; mapping реализован частично |
| Repository structure (§8.1) | расхождение (пропуски + несуществующий каталог) |

### Здоровье архитектуры

Границы подсистем выбраны правильно и обоснованы: Quest = intent, EV3 = authority,
`phantom-network` = fault-containment фронтенд без motor-write прав, `phantom-safety` =
software supervisor с честно задекларированными ограничениями, `POWER_CUT` = единственный
независимый канал. Разделение DAC-групп, `MotorLease`, boot-id как session epoch,
`commissioning_bundle_hash` как compatibility identity — всё это грамотные решения, которые
**менять не нужно**.

Два архитектурных решения требуют пересмотра:

1. `phantom-network` синтезирует telemetry сам, вместо того чтобы транслировать состояние
   controller (нарушает собственный §7.2.2 и делает liveness-сигнал Quest фиктивным);
2. `phantom-controller` завершается по `LOCAL_STOP`, вместо того чтобы удерживать latched
   `STOPPED` и обслуживать `RESET_STOPPED`.

### Количество findings

| Severity | Кол-во |
|---|---|
| CRITICAL | 2 |
| HIGH | 7 |
| MEDIUM | 17 |
| LOW | 11 |
| INFO | 6 |

### 10 самых важных проблем

1. **C-01** На Quest нет ни одного пути provisioning CONTROL PSK — `Provision()` не вызывается
   нигде. Реальный Quest всегда попадёт в `AuthenticationFailure`. Stage-3 exit criterion №3
   недостижим.
2. **C-02** `LOCAL_STOP` завершает `phantom-controller` с кодом 0; `Restart=on-failure` его не
   поднимает; boot-id файл остаётся; `phantom-network` продолжает отвечать `PONG` и слать
   `TELEMETRY state=CONNECTED_UNREFERENCED`. Документированный latch/`RESET_STOPPED` recovery
   не реализован.
3. **H-01** `TELEMETRY.state/fault_code/status_flags` жёстко зашиты в `phantom_network.py`;
   нормативный обратный `ControllerTelemetrySnapshotV1` (§7.2.2) отсутствует; battery читается
   из sysfs прямо из network-процесса, что §7.2.2 явно запрещает.
4. **H-02** `protocol/protocol.md` упоминается более десятка раз как generated wire mirror и
   входит в CI-gate §11.8 пункт 5 — фактически это 10-строчная рукописная заметка без
   генератора и без проверки.
5. **H-03** §5.19 (Quest config) и §7.21 (EV3 config) описывают структуру, которая заметно
   расходится с `config/schema/*` и `config/source/*` в обе стороны; у одного факта два
   конкурирующих owner.
6. **H-04** Safety/timing параметры (`command_timeout_ms`, `controller_heartbeat_timeout_ms`,
   `loop_fault_ms`, размер FlightRecorder) объявлены в конфигурации, но зашиты в код;
   `loop_safe_hold_ms=60` не реализован вовсе.
7. **H-05** Structured events (§7.20.1) и incident capture FlightRecorder (§7.20.2) на стороне
   `phantom-controller` отсутствуют полностью; ring buffer пишется, но никогда не читается.
8. **H-07** Stage-3 IPC contract имеет три независимые рукописные кодировки (Python struct,
   C++ offsets, C++ тестовый билдер) без общих golden vectors; единственная проверка — ещё не
   запущенный DEVICE AUTO.
9. **M-01** Счётчик `nonzero_motor_writes` структурно всегда равен нулю (нигде не
   инкрементируется), но утверждается 7 раз в тестах и используется как Stage-3 exit gate.
10. **M-02/M-03** `MulticastLock` (§4.6) не реализован; Quest↔EV3 interop проверяется только
    против симулятора, который расходится с реальным `phantom_network.py`.

---

## 2. Audit Scope

### Что реально проверено

- `AGENTS.md`, `ARCHITECTURE.md`, `README.md` — полностью.
- Весь нормативный набор `docs/PHANTOM/` — прочитан целиком либо по релевантным разделам
  (`PROTOCOL_SPECIFICATION`, `SYSTEM_ARCHITECTURE`, `SAFETY`, `SPECIFICATION_GOVERNANCE`,
  `IMPLEMENTATION_STAGES`, `status/CURRENT_STATUS` — целиком; `EV3_SPECIFICATION`,
  `QUEST_SPECIFICATION`, `TEST_PLAN`, `ENGINEERING`, `REFERENCE`, `PRODUCT_REQUIREMENTS`,
  `MECHANICAL_SPECIFICATION` — по заголовкам + все разделы, относящиеся к findings).
- ADR-0001..0004, `risks/EV3_LEGACY_PLATFORM.md`, `CHANGELOG.md`, `exec-plans/`, `spec-set.json`.
- Весь EV3 C++ runtime (`ev3/include`, `ev3/src`, `ev3/safety`, `ev3/tests`, `CMakeLists.txt`) —
  464 строки, прочитан построчно.
- `ev3/network/phantom_network.py`, `phantom_mdns.py`, `test_phantom_network.py` — целиком.
- `protocol/` целиком: `wire_schema.yaml`, `phantom_protocol.py`, `protocol_constants.hpp`,
  `golden_vectors/v1.json`, `protocol.md`, `README.md`.
- Все C# исходники `PhantomQuest/Assets/Phantom/Networking`, `Kinematics`, `Workspace`,
  `Mapping`, `Config`, `Logging`, `UI`, `Tests/Editor`; `PhantomRuntime.cs`.
- Оба Java-плагина (`PhantomNsdBridge.java`, `PhantomCredentialStore.java`) и `AndroidManifest.xml`.
- `deploy/` целиком (systemd units, tmpfiles, `install-release`, `wifi-autoconnect`,
  `device-auto.py`).
- `tools/` целиком: `protocolgen`, `configgen`, `specgen`, `docindex`, `doclint`,
  `artifact_check`, `build_identity`, `security_scan`, `spec_contract_check`.
- `config/` целиком (schema + source + generated + manifest).
- `sim/ev3-simulator/phantom_simulator.py`, `sim/tracking-replay`.
- `scripts/pre-install-auto.ps1`, `quest-device-auto.ps1`, `quest-test.ps1`,
  `ev3-bench-setup-sudo`, `ev3-bench-common`, `.github/workflows/ci.yml`.
- `.agents/skills/*` — все пять.
- `ev3/bench/README.md`, `results/README.md`, `results/ev3/README.md`.

### Что проверить было невозможно

| Область | Причина | Требуемый интеграционный тест |
|---|---|---|
| Реальный Quest 3 | нет устройства | `scripts/quest-device-auto.ps1` + P0 AUTO §9.6 |
| Реальный EV3 brick | нет устройства | `phantom-device-auto` (все Stage-3 строки) |
| Android NSD discovery на устройстве | нет Quest | Stage-3 DoD §10.5 п.2 + §9.8 |
| Android Keystore/AES-GCM credential | нет Quest | §8.11 provisioning + DEVICE AUTO |
| Реальный Quest ↔ реальный EV3 | нет обоих | Stage-3 physical acceptance §10.5 |
| Wi-Fi WNA1100 / ConnMan / Avahi | нет brick | DEVICE AUTO stage-3 network строки |
| Тайминг 50-Hz loop на ARMv5TEJ | нет brick | on-device timing self-test (p99 ≤ 25 ms) |
| systemd 232 unit semantics на brick | нет brick | `systemd-analyze verify` + kill/restart cases |
| Механика, QR-фикстуры, `POWER_CUT` | нет сборки | §9.15, `mechanical/safety-inspection.md` |
| Unity EditMode (26 тестов) | не запускал Unity batch (изменил бы `Library/`) | `scripts/quest-test.ps1` |
| ARMEL cross-build / packaging | требует Docker pull + WSL | `scripts/ev3-armel-docker.ps1` |

### Выполненные команды

Все запущены в read-only режиме относительно tracked-файлов; изменений в проект не вносилось.

```text
git status --porcelain=v1 --branch        → clean, ahead 5
python tools/protocolgen.py --check       → PASS (21 messages, sha256=48d85291…)
python tools/configgen.py --check         → PASS (ready_gate=BLOCKED_UNQUALIFIED_MEASURED_VALUES)
python tools/specgen.py --check           → PASS (c665c4c4…)
python tools/docindex.py --check          → PASS
python tools/doclint.py                   → PASS (12 норм. документов, 302 anchor)
python tools/test_protocol.py             → 5/5 OK
python tools/test_artifact_check.py       → 4/4 OK
python tools/test_build_identity.py       → 2/2 OK
python ev3/network/test_phantom_network.py→ 9/9 OK
python sim/ev3-simulator/test_simulator.py→ 9/9 OK
python sim/tracking-replay/test_tracking_replay.py → 2/2 OK
python tools/quest_validation/test_analyze.py     → 9/9 OK
python tools/ev3_validation/test_analyze.py       → 5/5 OK
tools/quest_validation/compile_and_smoke.ps1      → PASS (core smoke; Stage-3 81 checks; 21/21 golden vectors)
tools/quest_validation/run_udp_integration.ps1    → PASS (9/9 UDP сценариев против симулятора)
```

**Вывод по evidence:** числа в `status/CURRENT_STATUS.md` для детерминированной части
воспроизводятся точно. Дисциплина `NOT_RUN` для hardware соблюдается честно.

---

## 3. System Map

### Подсистемы

```text
Quest 3 (Unity 6000.3.22f1, Android, C#)
└─ Assets/Phantom  (≈2 900 строк C#, asmdef Phantom.Runtime/Editor/Meta/EditorTests)
   ├─ Networking/    Stage3NetworkClient, ProtocolCodec, ServerProtocol, Discovery,
   │                 AndroidNsdDiscoveryBackend, DatagramTransport, ControlCredentials,
   │                 SessionState, GeneratedProtocol.g.cs (generated)
   ├─ Kinematics/    PhantomMath (Vec3/JointAngles/JointLimits), PhantomKinematics (IK/FK)
   ├─ Workspace/     WorkspaceProjector, JointLimitProjector
   ├─ Mapping/       HumanToRobotMapper, GripMapper, PhantomStateMachine, EnableHysteresis
   ├─ Calibration/   ArmReachCalibration, ShoulderSphereFit, UserCalibrationWizard
   ├─ RobotLocalization/, Room/, Meta/, Tracking/, Replay/, Telemetry/, Visualization/, UI/
   ├─ Config/        Stage3RuntimeConfig (используется), PhantomConfig (мёртвый код)
   ├─ Diagnostics/   QuestDeviceAuto, QuestAutoQualification
   ├─ Logging/       QuestJsonlLogger, QuestNetworkEventSink
   ├─ Editor/        PhantomBuild, PhantomMrSceneBuilder
   └─ Tests/Editor/  5 файлов NUnit (26 тестов по статусу)
└─ Assets/Plugins/Android/PhantomScenePermissions.androidlib
   ├─ dev/phantom/nsd/PhantomNsdBridge.java        (NsdManager адаптер)
   └─ dev/phantom/security/PhantomCredentialStore.java (AES-GCM + Android Keystore)

EV3 brick (ev3dev Stretch, Debian 9.12, kernel 4.14, systemd 232, Python 3.5.3, armel)
├─ phantom-controller  (C++14, 464 строки всего core+main+safety+tests)
│    ControllerCore (state machine), Ev3SysfsBackend, MockMotorBackend,
│    HeartbeatChannel, MotorLease, NetworkIpcBoundary, RuntimeProfile, FixedRing<500>
├─ phantom-safety      (C++14, 27 строк main)  — supervisor + LOCAL_STOP + BRAKE takeover
├─ phantom-network     (Python 3.5-совместимый, 512 строк) — UDP/HMAC/session/telemetry
├─ phantom-mdns        (Python + dbus, 95 строк) — Avahi DNS-SD publisher
└─ phantom-wifi-autoconnect (POSIX sh, oneshot) — ConnMan boot recovery

Общие контракты
├─ protocol/wire_schema.yaml   (JSON-синтаксис; 21 message, 12 enum, 4 bitfield)
├─ protocol/generated/         canonical.json, protocol_constants.hpp, schema.sha256
├─ protocol/golden_vectors/    21 cross-language вектора
└─ config/{schema,source,generated}/  6 вариантов конфигурации + measured registry

Инструменты и инфраструктура
├─ tools/       specgen, docindex, doclint, protocolgen, configgen, artifact_check,
│               build_identity, security_scan, spec_contract_check, source_hash,
│               quest_android_nsd_check, quest_provider_compatibility_check,
│               spec_test_duration_check, quest_validation/*, ev3_validation/*
├─ sim/         ev3-simulator (второй сервер протокола), tracking-replay
├─ scripts/     20 скриптов: PowerShell (build/test/package/device) + POSIX sh (bench)
├─ deploy/      5 systemd units + target, tmpfiles, install-release, device-auto
└─ ev3/bench/   ОТДЕЛЬНАЯ подсистема: 1 740 строк C++ характеризационного harness
                + 10 скриптов + tools/ev3_validation/analyze.py (1 268 строк)
```

### Исполняемые компоненты и границы

| Компонент | Идентичность | Транспорт | Authority |
|---|---|---|---|
| Quest app | `dev.phantom.questprototype`, `quest_build_id` | UDP client, NSD browse | intent only |
| `phantom-controller` | `phantom-ctrl:phantom-motor` (+`phantom-ipc`,`phantom-safety-ipc`,`ev3dev`) | AF_UNIX dgram ×2, sysfs | **единственный владелец motor I/O** |
| `phantom-safety` | `root:phantom-safety-ipc` (+`phantom-motor`) | AF_UNIX dgram, sysfs | takeover BRAKE only |
| `phantom-network` | `phantom-net:phantom-net` (+`phantom-ipc`) | UDP :30470, AF_UNIX dgram | нет motor authority; владеет PSK |
| `phantom-mdns` | `phantom-mdns:phantom-mdns` | D-Bus → Avahi | нет |
| `phantom-wifi-autoconnect` | root oneshot | connmanctl | нет |

### Сетевые границы и хранилища состояния

```text
Quest ⇄ EV3 : UDP/IPv4 :30470, HMAC-SHA-256(PSK), ≤1024 B, DNS-SD _phantom-ev3._udp.local.
network ⇄ controller : AF_UNIX SOCK_DGRAM, 120 B request / 64 B reply, SCM_CREDENTIALS
controller ⇄ safety  : AF_UNIX SOCK_DGRAM, 24 B heartbeat, роли 1/2
controller → sysfs   : /sys/class/tacho-motor, /sys/class/lego-sensor, power_supply

Состояние:
  /run/phantom/controller/boot-id      controller epoch (16 B hex, 0644) — НЕ удаляется при выходе
  /run/phantom/motor-control.lock      flock lease (0660 root:phantom-motor)
  /run/phantom/network-status.json     атомарный снапшот счётчиков 1 Hz
  /var/lib/phantom/secrets/control.psk PSK (0640 root:phantom-net)
  /opt/phantom/{current,previous,releases/<id>}  A/B релизы через симлинк
  RAM: FixedRing<500> (controller), BoundedNetworkFlightRecorder(256) (Quest)
```

---

## 4. Documentation Map

### Нормативный набор (входит в `specification_sha256`)

| Документ | Строк | Роль |
|---|---|---|
| `SPECIFICATION_GOVERNANCE.md` | 115 | правила ownership, уровни, разрешение конфликтов |
| `PRODUCT_REQUIREMENTS.md` | 300 | цель, FR/NFR |
| `SYSTEM_ARCHITECTURE.md` | 395 | границы, system states, startup/motion flows |
| `QUEST_SPECIFICATION.md` | 1 404 | Quest runtime, tracking, IK, QR, UI, Quest config |
| `MECHANICAL_SPECIFICATION.md` | 722 | геометрия, передачи, QR-крепления, LOCAL_STOP |
| `EV3_SPECIFICATION.md` | 1 549 | процессы, IPC, control loop, protection, telemetry, EV3 config |
| `PROTOCOL_SPECIFICATION.md` | 402 | transport/session/transaction semantics, §11.8 ownership |
| `SAFETY.md` | 129 | S1–S57 инварианты, pre-motion checklists |
| `ENGINEERING.md` | 569 | repo structure, CI, build, deploy, PSK, сеть, логи |
| `TEST_PLAN.md` | 1 564 | таксономия PRE-INSTALL/DEVICE/HIL/MANUAL, §9.x cases |
| `IMPLEMENTATION_STAGES.md` | 351 | этапы 1–10 и их gates |
| `REFERENCE.md` | 359 | термины, формулы §11.1, реестр MEASURED |

### Ненормативные

| Документ | Роль |
|---|---|
| `docs/PHANTOM_SPECIFICATION.md` | **generated** манифест path+SHA-256 (не редактировать) |
| `docs/PHANTOM/SECTION_INDEX.md` | **generated** индекс §-якорей |
| `status/CURRENT_STATUS.md` | summary текущего состояния и evidence |
| `decisions/ADR-0001..0004` | rationale (protocol SoT, body provider, EV3 legacy, spec-set) |
| `risks/EV3_LEGACY_PLATFORM.md` | EOL-платформа, disposition |
| `CHANGELOG.md` | provenance ревизий документации |
| `REFERENCES.md` | внешние источники (ненормативно) |
| `exec-plans/README.md`, `TEMPLATE.md` | шаблон task-плана |
| `ARCHITECTURE.md` | короткая карта для людей и агентов (ненормативная) |
| `AGENTS.md` | навигация + постоянные ограничения для AI-агента |
| `README.md` | quick checks |
| `protocol/README.md`, `protocol/protocol.md` | заметки по протоколу |
| `ev3/bench/README.md` | bench harness (вне spec set) |
| `results/README.md`, `results/ev3/README.md` | правила evidence |
| `mechanical/README.md`, `safety-inspection.md` | физическая приёмка |

### Дублирование и потенциальные конфликты

| Где дублируется | Риск |
|---|---|
| `protocol/README.md` ↔ `protocol/protocol.md` | почти идентичный текст, два mutable mirror (L-04) |
| §5.19/§7.21 (config в prose) ↔ `config/schema/*` | **конкурирующие owner одного факта** (H-03) |
| `ARCHITECTURE.md` карта ↔ `docs/PHANTOM/README.md` карта ↔ §8.1 дерево | три частично расходящихся списка (L-01) |
| `AGENTS.md` инварианты ↔ `SAFETY.md` S1–S57 | осознанное повторение, расхождений не найдено ✔ |
| `IMPLEMENTATION_STAGES` §10.5 ↔ `TEST_PLAN` §9.1.3 ↔ `CURRENT_STATUS` | согласованы ✔ |

---

## 5. Documentation Quality

### Что сделано очень хорошо

- **Явная модель ownership.** `SPECIFICATION_GOVERNANCE.md` — один из лучших документов
  проекта: уровни, primary owner, правило уточнения, порядок разрешения конфликтов,
  fail-closed для safety-ambiguity. Это редкость.
- **Machine-checkable identity.** `specification_sha256` над exact Git bytes, запрет hidden
  normalization, транзитивная связь через generated манифест. `doclint.py` дополнительно
  ловит дублирующиеся anchor, неразрешимые `§`, битые ссылки, retired paths и tracked `.pyc`.
- **Разделение жизненных циклов** (spec / stages / plans / status / results / ADR / risks)
  выдержано последовательно.
- **Инварианты S1–S57** сформулированы как проверяемые утверждения, а не пожелания.
- **Честность про ограничения**: §7.2.2 прямо признаёт, что `phantom-network` входит в TCB и
  не изолирован криптографически; §7.2.4 — что `phantom-safety` не независимый канал. Это
  сильно повышает доверие к остальной части.

### Проблемы самой документации

1. **Ссылки на несуществующий generated artifact** — `protocol/protocol.md` (H-02).
2. **Конфликт owner конфигурации** — §5.19/§7.21 vs `config/schema` (H-03).
3. **Несогласованные единицы в prose**: `max_duty_pct` (§4.7.5) при schema `max_duty_permille`;
   `duty_pct` (§7.19.2) при schema `duty_permille`; `calibration_jog_max_duty_pct` (§5.19).
   Расхождение в 10 раз, если разработчик поверит prose (L-02).
4. **Три написания пути схемы** bundle: `/config/schema/commissioning_bundle.schema.json`
   (§7.21) и `/config/commissioning_bundle.schema.json` (§9.1.2) (L-03).
5. **Дерево репозитория §8.1 неполно и содержит несуществующий каталог** (L-01).
6. **`gripper_capabilities`** валидируется как 2-битное поле (`&~3`) в трёх кодеках, но его
   биты не определены ни в `wire_schema.yaml.bitfields`, ни в prose (L-07).
7. **§7.21 смешивает два артефакта** (EV3 runtime config и CommissioningBundle) в один YAML и
   называет схемой bundle-схему, хотя реализация их разделяет.
8. **Достаточность для «другого разработчика»**: для протокола, сессий, state machine и
   safety — да, спецификация самодостаточна. Для конфигурации — нет: разработчик, реализующий
   §7.21 буквально, получит артефакт, несовместимый с `configgen.py`.

### Проверенное отсутствие типичных дефектов

- Логических противоречий между `SAFETY.md`, `SYSTEM_ARCHITECTURE.md` §4.3 и
  `PROTOCOL_SPECIFICATION.md` §4.7 **не найдено** — state machine, latch-семантика,
  release-handshake и recovery описаны согласованно во всех трёх.
- `FAULT` корректно и последовательно описан как «не wire state» во всех документах.
- Enum/константы протокола нигде в нормативной prose не продублированы численно (это
  дополнительно защищено `doclint.py` forbidden-patterns).

---

## 6. Documentation ↔ Implementation Matrix

| Requirement / Contract | Documentation | Implementation | Status | Evidence | Notes |
|---|---|---|---|---|---|
| Wire header 64 B, HMAC-SHA-256, ≤1024 B | §4.7.1–4.7.3, `wire_schema.yaml` | `phantom_protocol.py`, `ProtocolCodec.cs` | MATCH | `protocolgen --check` PASS; 21/21 golden vectors в Python и C# | обе стороны декодируют одни байты |
| 21 message type, exact payload lengths | `wire_schema.yaml` | `protocol_constants.hpp`, `GeneratedProtocol.g.cs` | MATCH | `protocolgen.py:validate()` пересчитывает суммы полей | generated, дрейф блокируется |
| `protocol_schema_hash` = SHA-256 canonical JSON | §11.8 | `protocolgen.py`, `schema.sha256` | PARTIAL | канонизация — `json.dumps(sort_keys)`, не RFC 8785 JCS | M-13 |
| generated `protocol/protocol.md` | §11.8 п.3 и п.5, §4.7.3/4.7.4, README, ARCHITECTURE | нет генератора; файл — заметка на 10 строк | **MISSING_IMPLEMENTATION** | `grep protocol.md tools/` → только строковая проверка в `spec_contract_check.py:61` | H-02 |
| HELLO/HELLO_ACK, server-generated session_id, cached retry | §4.7.3 | `phantom_network.py:305-346`, `Stage3NetworkClient.HandleHelloAck` | MATCH | 9/9 network тестов; UDP сценарии busy/wrong_* | retry-window 2000 ms > 5×250 ms Quest ✔ |
| `capabilities_requested=0` → `ERR_UNSUPPORTED` | §4.7.3 | `phantom_network.py:319-320` | MATCH | `test_authenticated_semantic_hello_rejections_have_zero_session` | |
| Unknown key slot / bad HMAC = silent drop | §4.7.3 | `phantom_network.py:365-376` | MATCH | `test_cheap_parser_identity_and_unknown_key_rejections_are_inert` | |
| Строго возрастающий sequence, wrap запрещён | §4.7.3 | Python `last_rx_sequence`; C# `_txSequence==MaxValue` → invalidate | MATCH | `SessionState.AllocateSequence` бросает | |
| `session_stale_ms` инвалидация | §4.7.3 | `phantom_network.py:478` | MATCH | конфиг 5000 ms vs Quest ping 500 ms ✔ | |
| Нет `SESSION_CLOSE` datagram | §4.7.3 | нет в схеме и в коде | MATCH | | |
| TELEMETRY ≈20 Hz, поля §7.19.1 | §7.19.1, §4.7.8 | `phantom_network.py:409-426`, 50 ms | PARTIAL | layout корректен; **значения синтезированы** | H-01 |
| TELEMETRY отражает controller state/fault | §7.19.1, §10.5 «controller state/fault» | hardcoded `CONNECTED_UNREFERENCED`/`FAULT_NONE`/`STATUS_BUNDLE_VALID` | **MISMATCH** | `phantom_network.py:418-424` | H-01 |
| `ControllerTelemetrySnapshotV1` обратный IPC | §7.2.2 | отсутствует | **MISSING_IMPLEMENTATION** | нет упоминаний в коде | H-01 |
| Battery через controller IPC, не sysfs из network | §7.2.2 | `phantom_network.py:415` читает sysfs напрямую | **MISMATCH** | | H-01 |
| `ControllerRequestV1` 120 B / `ControllerReplyV1` 64 B | §7.2.2 | `network_ipc.cpp`, `IPC_REQUEST/IPC_REPLY` | MATCH (по чтению) | смещения сверены вручную: совпадают | H-07: нет исполненного теста связки |
| IPC: SCM_CREDENTIALS uid check | §7.2.2 | `network_ipc.cpp:46-47` | MATCH | | |
| IPC: ≤16 datagram/тик, freshness ≤500 ms | §7.2.2 | `network_ipc.cpp:43,50` | MATCH | | |
| IPC: canonical zero reserved | §7.2.2 | частично (`[8..11]`, `[53]`, `[55]`, `[62..63]`) | PARTIAL | не проверяются `command_payload=0` для OPEN, `nonce=0` для COMMAND | L-09 |
| IPC session watchdog при потере INVALIDATE | §7.2.2 | `session_active_` не истекает | **MISSING_IMPLEMENTATION** | `network_ipc.hpp:26` | M-10 |
| DNS-SD `_phantom-ev3._udp` / `local.` / IPv4 | §4.6, S46 | `phantom_mdns.py`, `AndroidNsdDiscoveryBackend` | MATCH | `configgen.validate()` + `quest_android_nsd_check.py` | |
| MulticastLock при foreground mDNS | §4.6 | отсутствует (разрешение объявлено) | **MISSING_IMPLEMENTATION** | `PhantomNsdBridge.java` — нет WifiManager | M-02 |
| Discovery по `robot_id`, не по IP | §4.6 | `Stage3NetworkClient.OnDiscoveryChanged:138` | MATCH | | `PhantomConfig.SimulatorHost` — мёртвый контрпример (M-04) |
| Смена endpoint/boot → новая session | §4.6 п.4-5 | `OnDiscoveryChanged:143-146` | MATCH | `EndpointBootAndServiceRecovery` тест | |
| Control PSK provisioning на Quest | §8.11 п.4, §10.5 Security | `Provision()` не вызывается нигде | **MISSING_IMPLEMENTATION** | grep по всем `.cs`/`.ps1`/`.py` | **C-01** |
| Control PSK на EV3 (`/var/lib/phantom/secrets`, 0640 root:phantom-net) | §8.11 | `install-release`, `phantom_network.load_key` | MATCH | `device-auto.py:276-277` проверяет DAC | |
| `LOCAL_STOP` приоритет над сетью (S21) | S21, §7.17, §7.24 | `controller_core.cpp:10` | MATCH (по обнаружению) | | |
| `STOPPED` latch + `RESET_STOPPED` recovery | §4.3, §4.7.5 | контроллер **завершает процесс** | **MISMATCH** | `controller_main.cpp:48` | **C-02** |
| `phantom-safety` loss → STOPPED + FAULT_CONTROLLER_PROCESS | §7.24 | `SAFE_HOLD` + fault; в network-only игнорируется | **MISMATCH** | `controller_core.cpp:11-12` | H-06 |
| Loop overrun → SAFE_HOLD/FAULT_LOOP_OVERRUN | §7.24, `loop_fault_ms=100` | `dt>100000`; в network-only ветка не достигается | PARTIAL | `controller_core.cpp:11,13` | H-06 |
| `loop_safe_hold_ms=60` промежуточный порог | §7.21 runtime_defaults | отсутствует | **MISSING_IMPLEMENTATION** | grep: 0 совпадений в коде | H-04 |
| `command_timeout_ms` из конфигурации | §7.21 network | hardcoded default 120 в структуре | **MISMATCH** | `controller_core.hpp:13`; `RuntimeProfile` не содержит поля | H-04 |
| `controller_heartbeat_timeout_ms` из конфигурации | §7.21 | hardcoded `100000` us ×2 | **MISMATCH** | `controller_main.cpp:47`, `safety/main.cpp:21` | H-04 |
| FlightRecorder 10 s @ 50 Hz | §7.20.2, `logging.*` | `FixedRing<500>` hardcoded, **никогда не читается** | PARTIAL | `controller_core.cpp:16`; `recorder()` без потребителей | H-05 |
| Incident freeze / incident_id / async save | §7.20.2 | отсутствует | **MISSING_IMPLEMENTATION** | | H-05 |
| Structured events controller (§7.20.1 список) | §7.20.1 | только `std::cerr` при startup-ошибках | **MISSING_IMPLEMENTATION** | | H-05 |
| Structured events network (`HELLO_*`, `SESSION_*`, `AUTH_FAILURE`, …) | §7.20.1 | `Stage3Server.event()` | MATCH | `phantom_network.py:244-247` | сетевой список реализован полностью ✔ |
| `WIFI_AVAILABLE/LOST/RECOVERED/RECOVERY_FAILED` | §7.20.1 | `deploy/scripts/wifi-autoconnect` | MATCH | | |
| Emergency log `phantom-safety` | §7.20.3 | `safety/main.cpp:13` | MATCH | | без ротации (M-07) |
| Ротация 7 суток / 250 MB, `UNCLEAN_SHUTDOWN`, `LOG_STORAGE_DEGRADED` | §8.13 | отсутствует полностью | **MISSING_IMPLEMENTATION** | grep: 0 совпадений | M-07 |
| Абсолютное отображение руки §11.1.1 | §11.1.1, FR-MAP-08 | `HumanToRobotMapper:11` | PARTIAL | нет `min(..., human_arm_reach*max_mapping_scale)` | M-05 |
| IK §11.1.2 | §11.1.2 | `PhantomInverseKinematics.Solve` | MATCH | формула совпадает посимвольно | ветвь `_elbowBranch` = `s` ✔ |
| FK §11.1.3 | §11.1.3 | `PhantomForwardKinematics.Solve` | MATCH | | |
| `yaw_singularity_hold_radius_m` из RobotGeometry | §11.1.2, §5.14 | hardcoded `_nearAxis=0.05` | PARTIAL | параметр не встречается в коде | M-05 |
| Left Grip гистерезис 0.45/0.60 | §5.4.2 | `EnableHysteresis(.60,.45)` | MATCH | `EnableUsesNormativeAsymmetricHysteresis` | но `PhantomConfig` 0.75/0.55 (M-04) |
| S9 re-arm по telemetry-confirmed `release_off_sequence` | S9, §5.4.2, §4.7.6 | `PhantomStateMachine` не имеет такого входа | **MISSING_IMPLEMENTATION** | `PhantomStateMachine.Update` | M-15; этап 8+, но тест создаёт ложное впечатление |
| `actuator_scope_mask` hard-inhibit (S44) | S44, §4.7.7 | `Ev3SysfsBackend::set_duty:59` | MATCH | + `MockMotorBackend.nonzero_writes` реальный счётчик | сильное место |
| `brake_all` для всех физически найденных осей | §7.2.4 | `ev3_sysfs_backend.cpp:60` без маски | MATCH | | |
| Quest config §5.19 | §5.19 | `config/schema/quest.schema.json` + `Stage3RuntimeConfig` | **MISMATCH** | `human_mapping`, фильтры, QR-пороги отсутствуют; `hello_retry_ms` и др. отсутствуют в §5.19 | H-03 |
| EV3 config §7.21 | §7.21 | `config/schema/ev3.schema.json` | **MISMATCH** | `drive_calibration`, per-axis gains, `runtime_defaults` отсутствуют; `hello_retry_window_ms`/`session_stale_ms` отсутствуют в `ev3.json` | H-03 |
| Config schema отклоняет duplicate keys / unknown fields | §7.21, §9.1.2 | `json.loads` (last-wins), `additionalProperties:true` | **MISMATCH** | `configgen.py:90`, `ev3.schema.json` | M-06 |
| MEASURED `required_before` enforcement | §7.21, §9.1.2 | `configgen` требует `value is None` | PARTIAL/инверсия | `configgen.py:113` | M-06 |
| PRE-INSTALL обязательный набор §9.1.2 | §9.1.2 | `pre-install-auto.ps1` (20 checks) | PARTIAL | нет `specgen/docindex/doclint` | M-08 |
| CI = PRE-INSTALL подмножество | §8.5 | `.github/workflows/ci.yml` | PARTIAL | нет network/security, artifact-gate | M-09 |
| Release provisioning audit (нет секретов в APK/manifest/логах) | §9.24.4, TEST_PLAN:1157 | `security_scan.py` — 2 regex по репо | PARTIAL | `artifact_check.verify_quest_embedded_identity` покрывает APK частично | M-11 |
| `phantom.target` требует safety, wants остальные | §7.2 | `deploy/systemd/phantom.target` | MATCH | | |
| Restart controller обнаруживается network/mDNS | §7.2 | boot-id polling 0.25 s | MATCH | `test_controller_restart_invalidates_session` | но смерть без рестарта — нет (C-02) |
| Python на brick не новее 3.5 | §7.1 | проверено: нет f-strings/typing/walrus | MATCH | grep по 4 on-brick скриптам | ✔ |
| systemd директивы ≤232 | §7.1 | units не используют `StateDirectory`/`LogsDirectory` | MATCH | | требует `systemd-analyze verify` на brick |
| Bench harness `ev3/bench` | — | 1 740 строк C++ + 10 скриптов | **UNDOCUMENTED_IMPLEMENTATION** | нет в §8.1, ARCHITECTURE, spec set | M-12 |
| `tools/ev3_validation/analyze.py` (1 268 строк) | — | анализ bench-логов | **UNDOCUMENTED_IMPLEMENTATION** | | M-12 |
| `PhantomConfig.cs` | — | мёртвый код с hardcoded IP и MEASURED-значениями | **UNDOCUMENTED_IMPLEMENTATION** | | M-04 |
| `nonzero_motor_writes` counter | §10.5 п.10 (как критерий) | никогда не инкрементируется | **UNCLEAR/фиктивный** | `phantom_network.py:231` — единственное вхождение | M-01 |

---

## 7. Architecture Review

### Что сделано хорошо — сохранить без изменений

1. **Разделение authority.** Quest шлёт intent, EV3 решает. Это не декларация: `set_duty`
   маскируется `actuator_scope_mask` на уровне backend, `phantom-net` не входит в
   `phantom-motor`, `MotorLease` через `flock` предотвращает split-brain. Решение правильное,
   реализовано последовательно.

2. **Schema-first протокол с hand-written кодеками.** Компромисс выбран верно: генерация
   constants/size maps + общие golden vectors даёт кросс-языковую гарантию без генератора
   кодеков для трёх языков на legacy-тулчейне. `spec_contract_check.py` дополнительно
   запрещает появление конкурирующих таблиц в prose. Не менять.

3. **`controller_boot_id` как session epoch.** Один 16-байтовый CSPRNG идентификатор
   одновременно решает: инвалидацию сессий при рестарте, привязку HELLO к текущему процессу,
   перепубликацию DNS-SD TXT, и обнаружение рестарта network-процессом. Элегантно и дёшево.

4. **Fail-closed по умолчанию везде.** `IoSnapshot.local_stop_pressed=true` по умолчанию;
   `ControllerCore::initialize` уходит в `SAFE_HOLD/Config` при незакоммиссионированном
   профиле; `load_runtime_profile` требует полного совпадения обоих артефактов; отсутствие
   battery telemetry — ошибка инициализации.

5. **Build identity (`PHANTOM-BUILD-V1`).** `build_id` = SHA-256 канонического объекта из
   commit + source_tree_hash + spec + protocol + config + toolchain lock. `install-release`
   отказывается ставить артефакт, чей `build_id`/SHA-256 отсутствует в PRE-INSTALL отчёте.
   Это существенно сильнее типовой практики.

6. **Дисциплина evidence.** Разделение PASS/FAIL/NOT_RUN/N_A, запрет промоушена симулятора в
   hardware PASS, `install_authorized=false` при dirty worktree — реально соблюдается в коде
   (`pre-install-auto.ps1`, `install-release`, `device-auto.py`).

### Что вызывает проблемы

#### A. `phantom-network` как источник telemetry вместо транслятора

1. **Что сейчас:** `phantom_network.py:409-426` собирает `TELEMETRY` из собственных
   локальных переменных и константы `CONNECTED_UNREFERENCED`, читает battery из sysfs сам.
   Обратного IPC от controller нет.
2. **Почему это проблема:** нарушает §7.2.2, инвариант «EV3 authoritative for state» и делает
   единственный liveness-сигнал Quest независимым от реального состояния authority. Смерть
   controller становится ненаблюдаемой (см. C-02).
3. **Реально ли это для PHANTOM:** да. Stage-3 DoD §10.5 прямо требует показывать
   «controller state/fault». На этапе 4+ это становится safety-critical: HUD оператора будет
   показывать состояние, не связанное с приводами.
4. **Как лучше:** реализовать `ControllerTelemetrySnapshotV1` как описано в §7.2.2 —
   controller push’ит bounded snapshot в тот же AF_UNIX канал раз в 50 ms; network только
   сериализует. При отсутствии свежего snapshot — не слать telemetry (Quest перейдёт в
   `TelemetryStale` по существующему таймеру 100 ms).
5. **Менять ли сейчас:** да, до Stage 4. Это малое изменение (структура уже спроектирована в
   спецификации) с большой отдачей, и оно закрывает C-02 и H-01 одновременно.

#### B. `phantom-controller` завершается по `LOCAL_STOP`

1. **Что сейчас:** `controller_main.cpp:48` — при `state()==Stopped` цикл останавливается,
   `main` возвращает 0. `Restart=on-failure` не поднимает процесс после кода 0.
2. **Почему проблема:** документированный `STOPPED` — это latched **состояние живого
   процесса**, из которого выходят через `RESET_STOPPED` + re-arm (§4.7.5, §4.3). Завершение
   процесса делает весь recovery-путь нереализуемым и оставляет `/run/phantom/controller/boot-id`
   с прежним значением, из-за чего network-плоскость не видит инцидента.
3. **Реально ли:** да. Физическая безопасность при этом сохраняется (`ExecStopPost` тормозит,
   supervisor тормозит), но продуктовый сценарий «нажал стоп → отпустил → сбросил → продолжил»
   невозможен.
4. **Как лучше:** оставаться в `STOPPED` внутри процесса, удерживать latch, обслуживать
   `RESET_STOPPED`; при завершении — удалять boot-id файл и/или использовать `BindsTo=` для
   network/mDNS.
5. **Менять ли сейчас:** да. Изменение локальное (условие выхода + удаление boot-id), но
   полный `RESET_STOPPED` можно отложить до этапа 4 — на Stage 3 достаточно не завершаться
   молча и делать факт наблюдаемым.

#### C. Конфигурация: два owner и невостребованные параметры

1. **Что сейчас:** §5.19/§7.21 описывают богатую структуру; `config/schema` описывает
   существенно меньшую; часть параметров из `config/source` не читается кодом вовсе.
2. **Почему проблема:** governance §4.5 прямо называет такую ситуацию неразрешённой
   неоднозначностью. Практически: параметр можно «настроить», и ничего не изменится
   (`command_timeout_ms`, `loop_fault_ms`, `flight_recorder_*`), а `loop_safe_hold_ms`
   вообще не имеет реализации.
3. **Реально ли:** да, и это классический источник инцидентов: оператор меняет
   `controller_heartbeat_timeout_ms` перед HIL, а поведение не меняется.
4. **Как лучше:** расширить `RuntimeProfile` до полного набора safety/timing параметров,
   загружать их из `config.generated.json` с валидацией диапазонов, и привести §7.21/§5.19 к
   фактической схеме (или наоборот — но один раз и явно).
5. **Менять ли сейчас:** привести документацию к схеме — да, сейчас (дёшево). Загрузку
   параметров — перед этапом 4, когда они начнут влиять на приводы.

#### D. Тестовая архитектура: симулятор как второй сервер

1. **Что сейчас:** Quest-клиент проверяется против `sim/ev3-simulator/phantom_simulator.py`;
   `phantom_network.py` проверяется изолированно с `LocalControllerAuthority`; C++ IPC —
   собственным тестом с третьей реализацией кодирования.
2. **Почему проблема:** ни одна пара «реальная реализация ↔ реальная реализация» не
   проверяется off-hardware. Симулятор объективно расходится с рабочим сервером (нет
   rate-limit, нет pre-HMAC key-slot drop, `session_stale=2 s` вместо 5 s, нет
   role/minor/capabilities rejection).
3. **Реально ли:** да, но частично компенсируется golden vectors (байтовый уровень) и
   DEVICE AUTO (на устройстве). Опасен именно IPC-слой: у него нет golden vectors.
4. **Как лучше:** (а) добавить golden vectors для `ControllerRequestV1`/`ControllerReplyV1` и
   прогонять их обеими реализациями; (б) добавить loopback-тест
   `phantom_network.py` ↔ `Stage3NetworkClient` (host-only, оба реальных).
5. **Менять ли сейчас:** да, (а) — небольшая работа с высокой отдачей.

#### E. Что НЕ является проблемой (проверено, менять не требуется)

- **Отсутствие C++ кодека протокола на EV3.** Wire-протокол обрабатывается в Python вне
  50-Hz цикла — это ровно то, что требует §7.2. Правильно.
- **Хранение схемы как JSON в файле `.yaml`.** Осознанное решение ради generation без
  зависимостей на legacy-образе; описано в `protocol/README.md`. Только имя вводит в
  заблуждение (L-04), но менять формат не нужно.
- **`phantom-safety` без независимого аппаратного канала.** Ограничение честно
  задокументировано и компенсируется `POWER_CUT`. Не переусложнять.
- **Синхронный `_exchange` с таймаутом 250 ms в network-worker.** При потере controller
  сессия закрывается после одного stall; остальное отсекается token bucket. Для Stage-3
  нагрузок (2 pps ping) допустимо.
- **Хранение всей матрицы Unity-пакетов в lock-файле и проверка версий в `artifact_check`.**
  Это выглядит избыточным, но именно оно ловит будущий multimodal-блокер, зафиксированный в
  ADR-0002. Оправдано.

---

## 8. Protocol & Integration Review

### Quest ⇄ EV3 (UDP/HMAC, protocol v1)

| Аспект | Состояние |
|---|---|
| Инициатор | Quest (после NSD resolve) ✔ соответствует §4.6 |
| Authority | EV3 создаёт `session_id` ✔ (S34) |
| Transport | UDP/IPv4 :30470, ≤1024 B ✔ |
| Addressing/Discovery | DNS-SD `_phantom-ev3._udp.local.`, выбор по `robot_id` ✔ |
| Handshake | HELLO(nonce) → HELLO_ACK(result, session) ✔; отказ = `session_id=0` ✔ |
| Версия | `protocol_major` в TXT + `protocol_minor` + `protocol_schema_hash` в ACK ✔ |
| Аутентификация | HMAC-SHA-256, constant-time (`compare_digest` / `FixedEquals`) ✔ |
| Framing/serialization | fixed-length, exact-length check до HMAC ✔ |
| Ordering | строго возрастающий `sequence` по направлению ✔ |
| Delivery | best-effort, «последняя цель заменяет старую» ✔ |
| Timeout | telemetry 100 ms, ping 750 ms ×3, session_stale 5 s ✔ согласованы |
| Retry | HELLO ×5 @250 ms внутри окна 2000 ms → cached ACK ✔ |
| Duplicate | `sequence <= last` → `replay_reject` на обеих сторонах ✔ |
| Stale | `end_session("timeout")`; Quest — `Reconnecting` ✔ |
| Reconnect | новый HELLO, новый session, sequence сбрасывается ✔ |
| Crash/restart | boot-id меняется → сессия инвалидируется ✔ |
| Несовместимый peer | `ERR_UNSUPPORTED`/`ProtocolMismatch`/`ConfigurationMismatch` ✔ |
| Shutdown | нет `SESSION_CLOSE`; bounded OFF/HOLD + затухание ✔ по §4.7.3 |

**Единственный дефект контракта на этом уровне** — семантика `TELEMETRY.state`: обе стороны
одинаково парсят поле, но передаваемое значение не является состоянием authority (H-01).
Quest даже усиливает иллюзию: `HandleTelemetry` отвергает `Ready/Hold/Tracking/...`, то есть
корректно ожидает network-only домен, но принимает `CONNECTED_UNREFERENCED` как доказательство
живости controller, которым оно не является.

**Асимметрия COMMAND.** EV3 полностью реализует приём `COMMAND` при scope `0x00` (учёт как
protocol evidence, `command_scope_zero`, IPC до controller), и DEVICE AUTO §9.1.3 это требует.
Quest Stage-3 клиент `COMMAND` не отправляет никогда. Это согласовано (проверку выполняет
локальный клиент `device-auto.py`), но нигде не зафиксировано явно — стоит отметить в статусе.

### `phantom-network` ⇄ `phantom-controller` (AF_UNIX)

| Аспект | Состояние |
|---|---|
| Инициатор | network (клиент), controller (сервер) ✔ |
| Authority | controller ✔ (S56) |
| Addressing | `/run/phantom/controller/network.sock`, `/run/phantom/network/controller.sock` ✔ |
| Auth | `SO_PASSCRED` + сравнение uid с `phantom-net` ✔; socket `0660 :phantom-ipc` ✔ |
| Framing | фиксированные 120/64 B ✔ |
| Freshness | `rx_us` ≤ 500 ms ✔ |
| Bounded drain | ≤16 за тик ✔ |
| Ordering | `wire_sequence > last` ✔ |
| Retry | **нет**: потеря одной датаграммы → `ERR_SESSION` → `end_session` |
| Session liveness | **нет таймаута** на стороне controller (M-10) |
| Takeover | иной PID с тем же uid **молча перехватывает** сессию (M-14) |
| Reverse telemetry | **не реализовано** (H-01) |
| Cross-impl test | **отсутствует** (H-07) |

Смещения полей Python-структуры и C++-разбора я сверил вручную поле за полем — **они
совпадают**. Дефекта нет; есть отсутствие защиты от будущего дрейфа.

### `phantom-controller` ⇄ `phantom-safety` (heartbeat)

Роли 1/2, magic `PHNT`, version 1, отклонение собственной роли и ненулевого `reserved` — всё
корректно. Два замечания: `drain()` — неограниченный цикл (в отличие от network IPC), а
`chmod 0660` выполняется без `chown` в группу `phantom-safety-ipc`, требуемую §7.2.4
(фактически работает, потому что peer — root). Оба вынесены в M-14.

### Quest ⇄ Android NSD (JNI)

Очередь resolve сериализована корректно (`resolving` флаг), `enqueueResolve` ограничен 64,
C#-сторона ограничивает глубину callback 128 и дренаж 64/кадр. Два риска, проверяемых только
на устройстве: отсутствующий `MulticastLock` и `normalize()`, снимающий только завершающую
точку (M-02).

---

## 9. State Machine Review

### System states (§4.3) vs `ControllerCore`

`ControllerCore` реализует подмножество, соответствующее этапам 1–3:

```text
Boot → (initialize)
  ├─ network-only  → Discovery ⇄ ConnectedUnreferenced   (по network_session_active)
  ├─ commissioned  → ConnectedUnreferenced
  └─ иначе         → SafeHold(Config)

tick():
  local_stop            → Stopped        → процесс завершается (C-02)
  network-only          → Discovery/ConnectedUnreferenced, fault принудительно None
  !safety_alive         → SafeHold(ControllerProcess)   [спец. требует Stopped — H-06]
  dt>100 ms             → SafeHold(LoopOverrun)
  !ready_predicates     → ConnectedUnreferenced | SafeHold
  !fresh                → SafeHold(Timeout)
  !enabled              → Hold
  else                  → Tracking, motion_allowed=true, затем brake_all()
```

**Замечания:**

- `Ready`, `RobotCalibration`, `Commissioning` **никогда не достигаются**: `ready_predicates()`
  требует `commissioning_valid && measured_limits_complete && external_power_cut_tested`, а
  `controller_main.cpp:20` жёстко задаёт им `false` и никогда не загружает из профиля. Это
  корректный fail-closed для этапов 1–3, но факт нигде не задокументирован — читатель
  `EV3_SPECIFICATION` вправе ожидать, что переходы работают.
- Ветка network-only стоит **перед** проверками safety heartbeat и loop overrun и
  безусловно сбрасывает `fault_=None` каждый тик. Для scope `0x00` это безопасно (нет
  authority), но означает, что supervisor-liveness и loop-health на Stage 3 не наблюдаются
  вовсе — при том, что §10.2 требует их «на каждом применимом этапе» (H-06).
- Комментарий `/* Stage 2 deliberately has no network-to-motor actuator law. */` находится в
  ветке, которая устанавливает `state_=Tracking` и `motion_allowed_=true` — то есть состояние
  `Tracking` достижимо без какого-либо движения. Для этапа 3 недостижимо (см. выше), но при
  включении commissioning это станет ловушкой.

### `PhantomStateMachine` (Quest) vs §4.3

- Вводит `Fault=100` — состояние, которого нет ни в `wire_schema.yaml`, ни в §4.3
  («`FAULT` не является отдельным wire state»). Как локальное продуктовое состояние это
  допустимо, но расходится с документированной моделью и не описано нигде.
- Численные значения `Boot=0 … Commissioning=10` продублированы вручную; тест
  `StateCodesMatchWireContract` сверяет только 3 из 11 значений и тоже с литералами, а не с
  `WireV1.State`. Изменение схемы не будет поймано (M-15).
- Отсутствует вход «telemetry-confirmed `release_seen`», обязательный по S9/§5.4.2. Тест
  `StateMachine_RequiresReleaseAndNewRisingEdge` проверяет только локальный rising edge, но
  назван так, будто покрывает весь контракт re-arm (M-15).
- `OnReferenceSpaceChange()` реализует S36 корректно ✔.

### `NetworkState` (Quest клиент)

11 состояний, переходы полны и покрыты 81 проверкой в `Stage3CoreTests`. Проверены: потеря
сервиса, смена endpoint, смена boot id, remove/re-add, pause/resume, HELLO retry с тем же
nonce, отказ по BUSY/AUTH, timeout ping, exhaustion sequence. **Это лучшая по покрытию
state machine в проекте.** Замечаний нет.

### Gripper FSM, JointSafeSet, payload FSM

Подробно специфицированы (§7.15, §7.16, §4.7.5, S40/S51/S57), **не реализованы** — это
соответствует этапам 4–9 и не является дефектом.

---

## 10. Error Handling & Recovery Review

| Сценарий | Поведение | Оценка |
|---|---|---|
| Недоступен EV3 | Quest: `Discovering`, повторный browse | ✔ |
| Недоступен Quest | EV3: `session_stale_ms` → `end_session("timeout")` | ✔ |
| Потеря Wi-Fi | ConnMan + bounded helper; Quest реконнект | ✔ (но M-16) |
| Смена IP | `endpoint_changed` → инвалидация → новый HELLO | ✔ |
| Malformed packet | `cheap_header` до HMAC, silent drop, счётчик | ✔ |
| Unexpected packet type в сессии | `parser_reject`, drop | ✔ |
| Duplicate/replay | отвергается на обеих сторонах | ✔ |
| Пакет в неверном состоянии | HELLO в активной сессии → `ERR_CONTROL_SESSION_BUSY` | ✔ |
| Bad HMAC | silent drop + `AUTH_FAILURE` event | ✔ |
| Crash `phantom-network` | новый PID → takeover IPC-сессии; systemd рестарт | ✔ |
| Crash `phantom-controller` (SIGKILL) | supervisor BRAKE + emergency log; systemd рестарт; новый boot-id → сессия инвалидируется | ✔ (покрыто DEVICE AUTO) |
| **Чистый выход `phantom-controller` (LOCAL_STOP)** | **не перезапускается; boot-id остаётся; network рапортует здоровье** | **C-02** |
| Зависание `phantom-controller` | heartbeat stale 100 ms → inhibit → lease/100 ms → BRAKE | ✔ |
| Потеря `phantom-safety` | `SAFE_HOLD` вместо `STOPPED` (§7.24); в network-only игнорируется | H-06 |
| Loop overrun | `SAFE_HOLD/FAULT_LOOP_OVERRUN`; порог 60 ms не реализован | H-04 |
| Потеря IPC datagram | сессия закрывается (fail-closed), retry нет | приемлемо, задокументировать |
| Потеря `SESSION_INVALIDATE` | controller навсегда считает сессию активной | M-10 |
| Отсутствует boot-id при старте network | бесконечный цикл ожидания без `READY=1` | зависит от `TimeoutStartSec=90` — приемлемо, но недокументировано |
| Заполнен диск (Quest) | `IOException` из `Log()` пробрасывается в `Update()` | M-07 |
| Некорректный config/bundle | `CONFIG_MISMATCH`/`BUNDLE_MISMATCH` + отказ старта | ✔ |
| Несовместимый `protocol_schema_hash` | отказ старта worker; на Quest — `ProtocolMismatch` | ✔ |
| Rollback установки | `install-release` откатывает симлинк и удаляет release | ✔ |

**Может ли система застрять в невосстановимом состоянии:** да, ровно один случай —
C-02. Все остальные пути либо восстанавливаются автоматически, либо честно останавливаются.

---

## 11. Security Review

Модель угроз (§3.2.6, §8.12): доверенная изолированная LAN, HMAC без конфиденциальности
(S29), компрометация хоста EV3 вне модели.

### Проверено и хорошо

- **Секретов в репозитории нет.** `git ls-files` не содержит ни `.secrets/`, ни `.ev3-ssh/`,
  ни keystore/PSK. `.gitignore` покрывает их корректно, включая
  `DevAgentSettings.asset` (может содержать токен Meta).
- **DAC-разделение реализовано и проверяется**: `phantom-ctrl` не читает PSK, `phantom-net`
  не пишет motor lease, `phantom-mdns` не читает PSK — три `runuser`-проверки в DEVICE AUTO.
- **HMAC сравнивается constant-time** в обеих реализациях.
- **Pre-HMAC поверхность минимальна**: длина, magic, версия, тип, `header_length`, `flags`,
  и один байт `key_slot` как селектор. Никакого oracle: неизвестный слот и плохой HMAC —
  тихий drop.
- **Session id — CSPRNG (`os.urandom(16)`), boot id — `/dev/urandom`**, оба ненулевые.
- **Rate limiting** — общий token bucket процесса, не per-endpoint (правильно против spoofing).
- **Credential на Quest** — AES-GCM с ключом в Android Keystore, AAD = keyId,
  fail-closed при ошибке. Реализация корректна (единственная проблема — её никто не вызывает).
- **`install-release`** проверяет пути в архиве на `../`, валидирует SHA256SUMS, сверяет
  PRE-INSTALL evidence, ставит `sudoers`-независимо.
- **`artifact_check`** проверяет, что путь к локальному keystore и пароль подписи не попали
  в APK — нетривиальная и полезная проверка.
- **Логи не содержат секретов**: `SESSION_CREATED` пишет `session="redacted"`;
  `wifi-autoconnect` явно никогда не читает `Passphrase`.

### Находки

1. **M-11 — `security_scan.py` создаёт ложное ощущение покрытия.** Два regex (PEM-ключ и
   `control_psk=<64hex>`) по файлам репозитория, с исключением **любого пути, содержащего
   `/test`**. Не детектирует: бинарный 32-байтовый PSK-файл, Wi-Fi passphrase, base64-секрет,
   пароль keystore. `TEST_PLAN:1157` описывает куда более широкий release provisioning audit,
   которого в автоматике нет.

2. **M-12 — bench-harness выдаёт `robot` NOPASSWD-root.** `scripts/ev3-bench-setup-sudo`
   устанавливает `robot ALL=(root) NOPASSWD: /home/robot/phantom-bench/bin/ev3-bench`.
   Путь **писуем пользователем `robot`**, поэтому правило эквивалентно неограниченному root
   для этого пользователя. `install-release` этот фрагмент не удаляет и не проверяет. На
   brick, где сначала гоняли bench, а затем поставили production, всё DAC-разделение
   `phantom-ctrl`/`phantom-net` обходится тривиально. Ни один нормативный документ этого не
   упоминает.

3. **M-12 (продолжение)** — незашифрованный SSH-ключ в `.ev3-ssh/id_ed25519` (gitignored, но
   присутствует в рабочей копии). Владение рабочей копией = root на brick. Для лабораторного
   стенда допустимо, но должно быть явно записано в модель угроз.

4. **M-14 — молчаливый takeover IPC-сессии.** `SESSION_OPEN` от другого PID с тем же uid
   всегда перехватывает сессию; `ERR_CONTROL_SESSION_BUSY` возвращается только тому же PID.
   Для одного systemd-сервиса это правильное поведение при рестарте, но контракт
   «одна CONTROL-сессия» на IPC-уровне обеспечивается только тем, что процесс один.

5. **L-09 — canonical-zero reserved полей IPC** проверяются частично (см. матрицу). Это
   defence-in-depth, а не эксплуатируемый дефект.

6. **`--psk-hex` у симулятора** имеет тестовый default с явным комментарием
   «production secrets are never CLI defaults» — корректно.

### Явно НЕ проблемы

- Отсутствие TLS/шифрования — осознанное решение, S29 и §3.2.6 его фиксируют.
- `bind 0.0.0.0` в Stage-3 — §8.12 требует привязки к интерфейсу только в Release;
  для Diagnostic на изолированной сети допустимо. Требование зафиксировано и не потеряно.
- Отсутствие аутентификации на heartbeat-сокете — сокет `0660` в
  root-owned каталоге `0770`; эскалация требует уже полученного доступа к группе.

---

## 12. Performance & Resource Review

### Проверено, проблем нет

- **Ограниченные очереди везде:** Quest transport 64 send / 64 receive с подсчётом дропов;
  NSD callbacks 128 глубина / 64 за кадр; `BoundedNetworkFlightRecorder(256)`;
  `FixedRing<500>`; IPC drain ≤16; UDP drain ≤32; `SO_RCVBUF 16384`.
- **Нет утечек задач/сокетов:** `TransportRestartConcurrencyIsBounded` явно проверяет, что
  100 рестартов транспорта не создают более одного worker и не оставляют висящих. Тест
  реально выполнен мной — PASS.
- **ASan/UBSan** прогоняются в CI и в PRE-INSTALL для C++ ядра.
- **50-Hz цикл не содержит сетевого/файлового I/O**: сокеты неблокирующие, логирования нет,
  sysfs-чтения — через предоткрытые fd с `lseek(0)+read` (без переоткрытия). Правильно.
- **Self-test контроллера** измеряет p99/max на 250 итерациях и падает при p99>25 ms.

### Замечания

1. **Постоянное пробуждение network-worker 100 раз/с** (`select` timeout 10 ms) на 300-МГц
   ARMv5. Значение зафиксировано в §7.21 как часть baseline. Это не дефект, но бюджет
   должен быть подтверждён на устройстве вместе с 50-Hz циклом и `phantom-safety` (тоже 50 Hz).
   Проверить статически невозможно.
2. **`HeartbeatChannel::drain` — неограниченный цикл.** При флуде по heartbeat-сокету тик
   растянется; результат fail-safe (`FAULT_LOOP_OVERRUN`), но асимметрия с bounded network
   drain выглядит непреднамеренной (M-14).
3. **`Ev3SysfsBackend::set_duty` пишет `command=run-direct` при каждом вызове** (50 раз/с на
   ось). На этапе 3 не используется; при включении приводов стоит писать `run-direct` один
   раз при входе в режим. INFO-уровень, отметить для этапа 4.
4. **`duty/10` в `set_duty`** отбрасывает дробную часть процента: разрешение команды
   фактически 1 % вместо 0.1 % (`duty_permille`). Для протокола, оперирующего permille, это
   потеря разрешения. Отметить перед этапом 4.
5. **Неограниченный рост логов** — единственная реальная ресурсная проблема (M-07).
6. **`build/` содержит 24 накопленных пакета** и несколько audit-снапшотов; политика очистки
   не описана (L-10). Каталог gitignored, влияния на артефакты нет.

---

## 13. Configuration & Dependencies Review

### Зависимости

| Компонент | Зависимости | Пиннинг |
|---|---|---|
| EV3 build | `ev3dev/debian-stretch-cross@sha256:819ea744…76a29f` | ✔ digest, проверяется `artifact_check` |
| EV3 runtime | stdlib C++14 + POSIX; Python 3.5 stdlib + `dbus` | ✔ без сторонних библиотек |
| Quest | Unity 6000.3.22f1, Meta XR Core, MRUK, XR Hands, OpenXR | ✔ `packages-lock.json` + сверка версий в `artifact_check` |
| Host tooling | Python 3.8 stdlib | ✔ без зависимостей (`configgen` содержит свой мини-валидатор JSON-Schema — осознанно) |

Устаревших/дублирующихся библиотек не обнаружено. `risks/EV3_LEGACY_PLATFORM.md` корректно
фиксирует EOL-статус ev3dev Stretch и блокирует Release до SBOM/vuln-review.

### Конфигурация

| Проблема | Детали |
|---|---|
| Два owner структуры | §5.19/§7.21 vs `config/schema/*` (H-03) |
| Параметры в конфиге, не читаемые кодом | `command_timeout_ms`, `controller_heartbeat_rate_hz`, `controller_heartbeat_timeout_ms`, `loop_safe_hold_ms`, `loop_fault_ms`, `motor_output_default`, `flight_recorder_seconds`, `flight_recorder_rate_hz`, `release_retention_days`, `release_max_mb`, `max_concurrent_control_sessions` (H-04) |
| Параметры в §7.21, отсутствующие в `ev3.json` (Release) | `hello_retry_window_ms`, `session_stale_ms` — есть только в network-only варианте; схема этого не ловит |
| Параметры в §5.19, отсутствующие в конфиге и коде | весь блок `human_mapping`, фильтры tracking, QR-пороги, `optional_remap_enabled` |
| Параметры в конфиге, отсутствующие в §5.19 | `hello_retry_ms`, `hello_max_attempts`, `ping_interval_ms`, `ping_timeout_ms`, `max_missed_pongs`, `reconnect_delay_ms` — реально влияют на поведение |
| Слабая схема | корень `ev3.schema.json` и `network` имеют `additionalProperties:true`; `safety`/`logging`/`axes` описаны как `{"type":"object"}` без свойств |
| Duplicate keys | `json.loads` — last-wins, вопреки §7.21/§9.1.2 (M-06) |
| MEASURED registry | 30 параметров, все `null`; `configgen` **запрещает** непустое значение (M-06) |
| Hardcoded адреса/значения | `PhantomConfig.SimulatorHost="192.168.0.112"`, `SimulatorPort=31337`, `L1/L2=0.215`, `OuterReach=0.43`, `FallbackJointLimits` — мёртвый код, но в runtime-сборке (M-04) |
| Hardcoded пути инструментов | `C:\Program Files\Unity\Hub\Editor\6000.3.22f1\…` в трёх скриптах; `wsl.exe -d Ubuntu` в PRE-INSTALL (L-05) |

**Согласованность масок** проверяется хорошо: `configgen.validate()` требует
`actuator_scope_mask & ~safety_observation_mask == 0`, сверяет тройку
bundle/ev3/quest и связывает `expected_hash` Quest с реальным хэшем bundle. Это сильное место.

---

## 14. Tests & Verification Review

### Уровни

| Уровень | Есть | Объём |
|---|---|---|
| Unit/property (Quest pure) | ✔ | `CoreSmoke` + 26 Unity EditMode |
| Unit (EV3 C++) | ✔ | `core_tests` + `network_ipc_tests` |
| Golden/cross-codec (wire) | ✔ | 21 вектор × Python + C# |
| Negative/fuzz-подобные | ✔ | malformed, NaN/Inf, reserved, length, replay, wrong key |
| Protocol server (EV3) | ✔ | 9 тестов `test_phantom_network.py` |
| Client state machine | ✔ | 81 проверка `Stage3CoreTests` |
| Integration (loopback UDP) | ✔ | 9 сценариев **против симулятора** |
| Simulator/replay | ✔ | 9 + 2 |
| Tooling self-tests | ✔ | artifact_check, build_identity, analyze ×2 |
| Sanitizers | ✔ | ASan/UBSan в CI и PRE-INSTALL |
| **Cross-implementation IPC** | ✘ | H-07 |
| **Реальный клиент ↔ реальный сервер** | ✘ | M-03 |
| DEVICE/HIL/manual | `NOT_RUN` | честно зафиксировано |

### Покрытые критические сценарии

Handshake, retry-идемпотентность, отказы HELLO по всем 4 кодам, replay, дубликаты,
устаревшая сессия, смена boot id, смена endpoint, remove/re-add сервиса, pause/resume
Android lifecycle, timeout ping, исчерпание sequence, token-bucket flood, NaN/Inf в telemetry,
битый HMAC, чужой endpoint, backend failure, split-brain lease, LOCAL_STOP latch (в ядре),
scope-zero inhibit.

### Непокрытые критические сценарии

1. **Python `ControllerIpcAuthority` ↔ C++ `NetworkIpcBoundary`** — ни одного исполненного
   теста (H-07).
2. **Реальный `phantom_network.py` ↔ реальный `Stage3NetworkClient`** — только через
   симулятор (M-03).
3. **Смерть controller без рестарта** — не покрыто ни одним тестом (C-02).
4. **Потеря `phantom-safety` heartbeat в network-only** — ветка кода недостижима, тест
   отсутствует.
5. **Переполнение/ошибка записи логов** — не покрыто.
6. **`ready_predicates()`==true** — ни один тест не достигает `READY`.

### Ложное ощущение покрытия

| Симптом | Реальность |
|---|---|
| `nonzero_motor_writes == 0` — 7 утверждений в Python-тестах + Stage-3 exit gate | счётчик нигде не инкрементируется; утверждение тавтологично (M-01) |
| `StateMachine_RequiresReleaseAndNewRisingEdge` | проверяет только локальный rising edge; S9 (telemetry-confirmed) не реализован (M-15) |
| `StateCodesMatchWireContract` | сверяет 3 из 11 значений и с литералами, не с `WireV1.State` (M-15) |
| «Stage 3 protocol interoperability PASS» | получено против симулятора, а не против рабочего сервера (M-03) |
| `spec_contract_check` «проверяет ownership» | для `protocol/protocol.md` — только наличие подстроки в prose (H-02) |
| «secret scan PASS» | 2 regex, исключая любой путь с `/test` (M-11) |

Реальная защита от нулевого выхода моторов обеспечивается двумя **настоящими** механизмами:
`MockMotorBackend::nonzero_writes_` (инкрементируется в `set_duty`) и `zero_state()` в
DEVICE AUTO (читает sysfs). Их достаточно — проблема именно в третьем, фиктивном счётчике.

### Соответствие тестов текущей спецификации

Тесты соответствуют реализованному срезу. Расхождения тестов и **спецификации** там, где
спецификация описывает нереализованное (S9, §7.24 STOPPED, config), перечислены выше.

---

## 15. Build / Deployment / Developer Experience Review

### Может ли новый разработчик…

| Задача | Возможно? | Комментарий |
|---|---|---|
| Понять архитектуру | **да** | `ARCHITECTURE.md` + `docs/PHANTOM/README.md` — образцовая навигация |
| Собрать EV3 (host) | да | `scripts/ev3-host-build.ps1` |
| Собрать EV3 (armel) | да | `scripts/ev3-armel-docker.ps1`, образ запиннен по digest |
| Собрать Quest APK | да, но | требует Unity 6000.3.22f1 по **точному пути** + локальный keystore; §8.8 описывает, но путь не параметризован |
| Запустить проверки | да | `README.md` содержит рабочий список; я выполнил его почти целиком |
| Запустить PRE-INSTALL | частично | требует Unity + Docker + **WSL Ubuntu** (`wsl.exe -d Ubuntu`); последнее нигде не заявлено как prerequisite |
| Понять порядок запуска на EV3 | да | systemd-граф явный, `install-release` линеен и читаем |
| Соединить компоненты | **нет** | нет процедуры provisioning PSK на Quest (C-01) |
| Диагностировать проблему | да | structured JSON events, `network-status.json`, HUD с hashes/RTT/счётчиками |
| Понять hardware prerequisites | да | §7.1 fingerprint, §8.6/§8.7, `mechanical/` |

### Замечания

- **`README.md` корректен**: перечисленные команды существуют и работают. Приятное
  исключение из типичной практики.
- **`install-release` — сильная сторона**: атомарный симлинк, откат, self-test бинарей,
  `compileall`, создание пользователей/групп, `systemd-tmpfiles`, проверка активности,
  запуск DEVICE AUTO как финального шага.
- **Отсутствует документация prerequisites хоста разработчика** (Unity path, WSL distro,
  Docker, Git Bash для bench-скриптов) — L-05.
- **`.gitignore` игнорирует `*.csproj`/`*.slnx`**, но `PhantomQuest/*.csproj` присутствуют в
  рабочей копии как untracked — нормально для Unity.
- **`build/phantom-automation-sudoers-setup.sh`** присутствует локально (untracked) —
  вне области аудита содержимого репозитория, но указывает, что существует ещё один путь
  провижининга привилегий, не отражённый в `deploy/`.

---

## 16. AGENTS.md Review

### Соответствие текущей архитектуре

Содержательно `AGENTS.md` **точен**. Проверено построчно:

- Список неизменяемых инвариантов полностью согласуется с `SAFETY.md` (S19, S21, S44, S13,
  S11) и с фактическим кодом (`set_duty` маска, `MotorLease`, `brake_all` вне маски).
- Раздел «Источники истины» согласуется с `SPECIFICATION_GOVERNANCE.md`.
- Список generator-команд соответствует реальным инструментам и все они работают.
- Разделы «Дисциплина проверки» и «Завершение задачи» точны и полезны; правило про
  `PASS` и изменение `specification_sha256` соответствует поведению `artifact_check`/
  `install-release`.
- Правило про commit («execution plan, который агент создал сам, не даёт разрешения») —
  хорошая, редко встречающаяся предосторожность.

### Найденные проблемы

1. **M-17 (MEDIUM) — платформенные допущения о конкретном агенте.**
   - «Codex получает этот файл через механизм проектных инструкций. Не трать отдельный вызов
     инструмента на повторное чтение `AGENTS.md`». В репозитории **нет `CLAUDE.md`**, поэтому
     для Claude Code файл не подставляется автоматически и утверждение ложно — агент, который
     ему поверит, будет работать без ключевых ограничений проекта.
   - «Используй репозиторный Skill из `.agents/skills/`». Claude Code обнаруживает skills в
     `.claude/skills/`; пять качественных `phantom-*` skills фактически недоступны.
   - `exec-plans/README.md` также написан в терминах «длинных Codex-задач».
   - **Исправление:** добавить `CLAUDE.md` со ссылкой `@AGENTS.md` (или симлинк/копию) и
     продублировать/симлинкнуть skills в `.claude/skills/`; сформулировать инструкцию как
     «если этот файл не был подставлен автоматически — прочитай его один раз».

2. **L-11 (LOW) — не описаны области, реально существующие в репозитории.**
   `AGENTS.md` не упоминает `ev3/bench/`, `results/**` schema, `mechanical/`, и не даёт
   правила «что делать с bench-кодом». Учитывая, что bench — крупнейшая по объёму часть
   кодовой базы, агент может изменить его, не понимая, что это не production-путь.

3. **L-12 (LOW) — неоднозначность при конфликте prose-конфигурации и schema.**
   AGENTS.md говорит «объявленные репозиторием config schema/generator sources владеют
   машинно-читаемой структурой конфигурации», но §5.19/§7.21 тоже нормативны и содержат поля,
   которых в схеме нет. Правило не покрывает случай «поле есть в prose, но отсутствует в
   схеме» (H-03). Стоит добавить явное разрешение.

### Опасных или двусмысленных указаний не найдено

Никаких инструкций, которые могли бы привести к небезопасным действиям, обходу safety-gates
или скрытому commit, в `AGENTS.md` нет. Правило fail-closed при конфликте сформулировано
корректно.

### Достаточность для AI-агента

Достаточна и хорошо сбалансирована по объёму (progressive disclosure, запрет читать всё
подряд, детерминированный `docindex --locate`). После исправления M-17 — очень хороший
документ.

---

## 17. Missing Documentation

Реализовано, но не описано в нормативном наборе:

1. **`ev3/bench/` + `scripts/ev3-bench-*` + `tools/ev3_validation/`** — ~2 700 строк,
   собственный toolchain-файл, SSH-автоматизация, провижининг sudo, «намеренно опасный»
   сценарий E9. Отсутствует в §8.1, в `ARCHITECTURE.md` и в spec set. Нужен как минимум
   раздел «инженерная оснастка вне production» с явным заявлением, что она не является частью
   safety-периметра, и требованием удалять sudoers-фрагмент перед production-установкой.
2. **`results/**` структура и schema** — упоминается в governance, но её формат
   (`pre_install_report.schema.json`, `device-auto.json`, `quest-p0-report.json`) не описан в
   `ENGINEERING.md`; `ENGINEERING.md` не содержит ни одной ссылки на `results/`.
3. **Stage-3 асимметрия COMMAND**: EV3 принимает и учитывает `COMMAND` при scope `0x00`,
   Quest его не шлёт; проверка выполняется локальным клиентом DEVICE AUTO. Не зафиксировано.
4. **Хардкод `commissioning_valid/measured_limits_complete/external_power_cut_tested=false`**
   в `controller_main.cpp` — фактически делает `READY` недостижимым на этапах 1–3. Это
   правильное поведение, но оно нигде не записано как реализованное ограничение.
5. **Ветка network-only в `ControllerCore::tick`**, обходящая safety-heartbeat и loop-overrun
   предикаты, и принудительно сбрасывающая `fault_`.
6. **Поведение `phantom-network` при отсутствующем boot-id** (бесконечное ожидание до
   systemd `TimeoutStartSec`).
7. **Семантика IPC session takeover** (другой PID перехватывает; тот же PID получает BUSY).
8. **Отсутствие retry на IPC** и следствие «одна потерянная датаграмма = закрытие сессии».
9. **Требования к хосту разработчика**: точный путь Unity, WSL distro, Docker, Git Bash.
10. **`PhantomConfig.cs`** — если это осознанно сохранённый черновик, это должно быть
    отмечено; если нет — удалить.
11. **Unity template/sample assets** (`VRTemplateAssets`, XR Interaction Toolkit samples,
    Oculus samples) в трекинге — не упомянуты в §8.1; влияние на APK не оценено.

---

## 18. Missing Implementation

Заявлено документацией, отсутствует или реализовано неполно (упорядочено по важности для
ближайшего этапа):

| Требование | Owner | Состояние |
|---|---|---|
| Provisioning CONTROL PSK на Quest | §8.11 п.4, §10.5 Security | **отсутствует** (C-01) |
| Latched `STOPPED` + `RESET_STOPPED` recovery | §4.3, §4.7.5 | **отсутствует**, процесс завершается (C-02) |
| `ControllerTelemetrySnapshotV1` (обратный IPC) | §7.2.2 | **отсутствует** (H-01) |
| generated `protocol/protocol.md` + его CI-проверка | §11.8 п.3, п.5 | **отсутствует** (H-02) |
| `loop_safe_hold_ms` (60 ms) промежуточный порог | §7.21 | **отсутствует** (H-04) |
| Загрузка safety/timing параметров из конфигурации | §7.21 | **отсутствует** (H-04) |
| Structured events `phantom-controller` (§7.20.1) | §7.20.1 | **отсутствует** (H-05) |
| FlightRecorder incident freeze/save/`incident_id` | §7.20.2 | **отсутствует** (H-05) |
| `phantom-safety` loss → `STOPPED` | §7.24 | реализовано как `SAFE_HOLD` (H-06) |
| Ротация логов 7 сут / 250 MB | §8.13.1 | **отсутствует** (M-07) |
| `runtime-active` маркер + `UNCLEAN_SHUTDOWN` | §8.13.3 | **отсутствует** (M-07) |
| `LOG_STORAGE_DEGRADED` event | §8.13.3 | **отсутствует** (M-07) |
| `MulticastLock` для foreground mDNS | §4.6 | **отсутствует** (M-02) |
| IPC session watchdog | §7.2.2 | **отсутствует** (M-10) |
| Отклонение duplicate keys / unknown fields в конфиге | §7.21, §9.1.2 | **отсутствует** (M-06) |
| `MEASURED.required_before` enforcement | §7.21, §9.1.2 | инвертировано (M-06) |
| `mapping_reach_m = min(robot_nominal_reach, human_arm_reach*max_mapping_scale)` | §11.1.1, FR-MAP-08 | **частично** (M-05) |
| `yaw_singularity_hold_radius_m`/`human_vector_min_m` из RobotGeometry | §11.1.2, §5.14 | hardcoded (M-05) |
| S9 telemetry-confirmed re-arm на Quest | S9, §5.4.2 | **отсутствует** (M-15) |
| `protocol/fuzz_corpus/` | §8.1 | **отсутствует** (L-01) |
| Release provisioning audit (APK/manifest/логи) | §9.24.4 | частично (M-11) |
| RFC 8785 JCS канонизация | §11.8, §7.21 | не-JCS эквивалент (M-13) |

**Не считается пропуском** (этапы 4–10, корректно вне scope): gripper FSM, JointSafeSet,
DriveCalibration, QR RobotLocalization, IK preview/collision, payload profiles, transaction
layer (`FAULT_ACK`/`RESET_STOPPED`/`SET_*`), commissioning role/PSK, `DIAGNOSTIC_TELEMETRY`,
MotorStressScore, gravity feed-forward, controllers.

---

## 19. Findings

### CRITICAL

---

#### C-01 — На Quest нет реализованного пути provisioning CONTROL PSK

- **Severity:** CRITICAL
- **Тип:** missing implementation / blocked key scenario
- **Где:** Quest credential слой
- **Файлы:**
  - `PhantomQuest/Assets/Phantom/Networking/ControlCredentials.cs:61` (`Provision`)
  - `PhantomQuest/Assets/Plugins/Android/PhantomScenePermissions.androidlib/src/main/java/dev/phantom/security/PhantomCredentialStore.java:27` (`provision`)
  - `PhantomQuest/Assets/Phantom/PhantomRuntime.cs:25` (создаёт store, но только читает)
  - `scripts/quest-device-auto.ps1` (устанавливает APK, credential не передаёт)
- **Что говорит документация:** `ENGINEERING.md` §8.11 п.4: «control PSK передаётся на Quest
  вне исполнительного UDP-протокола и хранится через app-private credential service».
  `IMPLEMENTATION_STAGES.md` §10.5, строка Security: «provision независимый `control`
  PSK/key_id по §8.11 и проверить CONTROL-authenticated network-only session». Stage-3 exit
  criterion №3 требует аутентифицированной CONTROL-сессии с реальным Quest.
- **Что делает код:** `AndroidPrivateControlCredentialStore.Provision(...)` и
  `PhantomCredentialStore.provision(...)` реализованы корректно (AES-GCM + Keystore), но
  **не вызываются ни из одного места**: grep по всем `.cs`, `.ps1`, `.py`, `.java` в
  репозитории даёт только определения. Единственный не-Android путь —
  `#else`-ветка, читающая plaintext `<persistentDataPath>/phantom-secrets/<keyId>.psk`,
  которая на Android не компилируется (`UNITY_ANDROID && !UNITY_EDITOR`).
- **Почему проблема:** на реальном устройстве `_credentials.TryLoad` вернёт `false`,
  `Stage3NetworkClient.Start()` (`Stage3NetworkClient.cs:84`) установит
  `NetworkState.AuthenticationFailure` и `HELLO` не будет отправлен никогда.
- **Реальный сценарий:** установка Diagnostic APK на Quest 3 → приложение показывает
  «ОШИБКА АУТЕНТИФИКАЦИИ» → шаги 4–7 «Следующего физического gate Stage 3» из
  `status/CURRENT_STATUS.md` невыполнимы.
- **Рекомендация:** реализовать явный инженерный путь provisioning: (а) Diagnostic-only
  экран/действие, вызывающее `Provision` с ключом, переданным вне протокола, либо
  (б) host-скрипт, который через `adb` запускает одноразовую provisioning-активность.
  Ключ не должен появляться в Resources/StreamingAssets/build manifest. Добавить в
  DEVICE AUTO строку `quest-control-credential-present`.
- **Confidence:** HIGH

---

#### C-02 — `LOCAL_STOP` завершает `phantom-controller`; система не восстанавливается и продолжает рапортовать исправность

- **Severity:** CRITICAL
- **Тип:** state-machine flaw / unrecoverable state / misleading safety indication
- **Где:** EV3 runtime + systemd + network telemetry
- **Файлы/символы:**
  - `ev3/src/controller_core.cpp:10` — `if(io.local_stop_pressed){safe(State::Stopped);}`
  - `ev3/src/controller_main.cpp:48` — `if(core.state()==phantom::State::Stopped){lease.release();running=0;}` → `return 0`
  - `deploy/systemd/phantom-controller.service` — `Restart=on-failure`
  - `deploy/systemd/phantom-network.service` — `Requires=phantom-controller.service` (не `BindsTo=`)
  - `ev3/src/runtime_profile.cpp:23` — `publish_controller_boot_id` пишет файл; **удаления нет нигде**
  - `ev3/network/phantom_network.py:249-256` — `read_boot_id` реагирует только на **изменение** значения
- **Что говорит документация:** §4.3 — `STOPPED` латчится и снимается `RESET_STOPPED` после
  физического release; §4.7.5 — `RESET_STOPPED` принимается «только когда физический
  `LOCAL_STOP` уже released, все моторы stationary…»; §7.24 — `LOCAL_STOP` → `STOPPED` + `BRAKE`;
  §7.2 — «Restart controller обязан быть обнаружен network/mDNS plane».
- **Что делает код:** контроллер выходит из главного цикла и возвращает `0`. `Restart=on-failure`
  не перезапускает процесс при коде 0. `ExecStopPost` тормозит моторы, `phantom-safety`
  дополнительно тормозит по потере heartbeat — **физическая безопасность сохраняется**. Но:
  файл `/run/phantom/controller/boot-id` остаётся с прежним значением, `phantom-network`
  видит то же значение и **не** завершает сессию; `TELEMETRY` продолжает уходить со
  `state=CONNECTED_UNREFERENCED`, `fault_code=NONE`, `status_flags=COMMISSIONING_BUNDLE_VALID`;
  `PING` продолжает получать `PONG`. Quest видит `TelemetryFresh`.
- **Почему проблема:** (1) документированный путь восстановления (`RESET_STOPPED` → `HOLD`)
  невозможен в принципе; (2) оператор в HMD видит исправную связь с роботом, у которого нет
  authority-процесса; (3) обнаружение возможно только по внешнему признаку (systemd), которого
  ни один компонент не проверяет; (4) `phantom-safety` при удерживаемом `LOCAL_STOP` уходит в
  бесконечный цикл torможения с логированием одного события — приемлемо, но система остаётся
  мёртвой до ручного вмешательства.
- **Реальный сценарий:** Stage-3 стенд с датчиком на `in4` (или любой стенд этапа 4+, где
  `local_stop.required=true`): оператор нажимает `LOCAL_STOP` → controller выходит →
  ни systemd, ни network, ни Quest этого не замечают → после отпускания кнопки система не
  возвращается, но UI показывает «СОЕДИНЕНО / ТЕЛЕМЕТРИЯ АКТУАЛЬНА».
- **Рекомендация:**
  1. не завершать процесс по `Stopped` — удерживать latch внутри `ControllerCore`
     (`stop_latched_`), продолжать тик, тормозить, ждать release + `RESET_STOPPED`;
  2. до реализации `RESET_STOPPED` (этап 4) как минимум: удалять
     `/run/phantom/controller/boot-id` при любом завершении, использовать `BindsTo=` в
     `phantom-network.service`/`phantom-mdns.service` и `Restart=always` для controller;
  3. добавить в DEVICE AUTO кейс «controller завершился штатно → network перестаёт отвечать».
- **Confidence:** HIGH на факты кода и на отсутствие удаления boot-id;
  MEDIUM-HIGH на точную семантику systemd `Requires=` при чистом самозавершении (проверяемо
  только на brick; `BindsTo=` — документированный способ добиться распространения).

---

### HIGH

---

#### H-01 — `TELEMETRY` синтезируется network-процессом; нормативный обратный IPC не реализован

- **Severity:** HIGH
- **Тип:** spec/implementation mismatch, ownership violation
- **Файлы:** `ev3/network/phantom_network.py:409-426` (`telemetry`), `:415` (чтение
  `/sys/class/power_supply/lego-ev3-battery/voltage_now`), `:418`, `:421`
- **Документация:** §7.2.2 — «Обратный `ControllerTelemetrySnapshotV1` передаёт network worker
  только bounded snapshot состояния controller/battery/reference/gripper/incident»;
  «`CALIBRATION_QUERY`/atomic encoder snapshot и иные read operations, состояние которых
  принадлежит controller, также проходят этот IPC, **а не читают motor sysfs из network
  process**». §10.5 (Stage-3 DoD, строка UI/telemetry) требует «battery, **controller
  state/fault**».
- **Код:** значения `state=CONNECTED_UNREFERENCED`, `fault=FAULT_NONE`,
  `status=STATUS_BUNDLE_VALID` — константы; `battery_mv` читается из sysfs напрямую;
  структуры `ControllerTelemetrySnapshotV1` в репозитории нет.
- **Почему проблема:** нарушен инвариант «EV3 authoritative for state» на наблюдаемом уровне;
  Quest-watchdog валидируется против сигнала, не связанного с authority; `local_stop_active` и
  `safety_supervisor_alive` никогда не выставляются, хотя Quest их допускает.
- **Сценарий:** любой отказ или переход состояния `phantom-controller` невидим для Quest
  (см. C-02). На этапе 4 это станет прямой safety-проблемой.
- **Рекомендация:** реализовать push-снапшот controller→network в существующем сокете
  (структура уже специфицирована), сериализовать telemetry только из свежего снапшота, при
  отсутствии свежего — не отправлять. Battery перенести в снапшот.
- **Confidence:** HIGH

---

#### H-02 — `protocol/protocol.md` объявлен generated wire mirror и частью CI-gate, но не генерируется

- **Severity:** HIGH
- **Тип:** documentation/implementation mismatch, unenforced normative gate
- **Файлы:** `protocol/protocol.md` (10 строк, рукописная заметка);
  `tools/protocolgen.py:101-107` (5 выходов, `protocol.md` среди них нет);
  `tools/spec_contract_check.py:61` (проверяет лишь наличие подстроки `"protocol/protocol.md"` в prose)
- **Документация:** §11.8 — «Authoritative byte-level sources: … 3. `protocol/protocol.md` —
  generated human-readable wire mirror»; §11.8 gate п.5 — «проверить machine-readable
  extractor-ом, что generated `protocol/protocol.md`, constants/size maps и golden vectors
  соответствуют текущему `wire_schema.yaml`». Плюс §4.7.3, §4.7.4, §4.7.6, §4.7.8, ADR-0001,
  `docs/PHANTOM/README.md`, `ARCHITECTURE.md:54` — более десятка отсылок.
- **Код:** генератора нет; файл содержит общее описание, а не layout; ни один gate не
  проверяет его актуальность.
- **Почему проблема:** разработчик, следующий документации за «точным message_type / bit
  positions / payload lengths», приходит к файлу, где их нет. Нормативный CI-пункт объявлен
  выполняемым и не выполняется. Также нарушено правило «не создавать mutable mirrors»:
  `protocol/README.md` и `protocol/protocol.md` дублируют друг друга.
- **Рекомендация:** добавить рендер Markdown-таблиц в `tools/protocolgen.py` (все данные уже
  есть в схеме) и включить `protocol.md` в `--check`; слить `protocol/README.md` в него или
  оставить README как краткий указатель. Альтернатива — убрать `protocol.md` из §11.8 и всех
  ссылок и объявить `wire_schema.canonical.json` единственным mirror.
- **Confidence:** HIGH

---

#### H-03 — Нормативные спецификации конфигурации (§5.19, §7.21) расходятся с фактической схемой в обе стороны

- **Severity:** HIGH
- **Тип:** competing same-layer owners, incomplete specification
- **Файлы:** `docs/PHANTOM/QUEST_SPECIFICATION.md:1300-1404`,
  `docs/PHANTOM/EV3_SPECIFICATION.md:1190-1450`, `config/schema/quest.schema.json`,
  `config/schema/ev3.schema.json`, `config/source/*.json`
- **Документация:** §5.19/§7.21 нормативны (governance таблица: QUEST/EV3 spec владеют «Quest
  config»/«EV3 config»); одновременно governance объявляет «объявленные репозиторием config
  schema/generator sources» владельцами машинно-читаемой структуры. Governance §4.5 требует
  явно разрешать такую двойственность.
- **Код:** конкретные расхождения:
  - §5.19 содержит блок `human_mapping` (`arm_reach_min/max_technical_m`, `max_mapping_scale`),
    `body_tracking.{shoulder_dropout_grace_ms, max_tracking_alignment_ms,
    max_tracking_extrapolation_ms, control_vector_filter, filter_params, human_vector_min_m}`,
    восемь QR-порогов, `grasp.{optional_remap_enabled, remap_min_usable_span}`,
    `commissioning_bundle.path` — **ничего из этого нет** в схеме/источнике/коде;
  - `config/source/quest*.json` содержит `network.{hello_retry_ms, hello_max_attempts,
    ping_interval_ms, ping_timeout_ms, max_missed_pongs, reconnect_delay_ms}`, реально
    управляющие поведением `Stage3NetworkClient`, — **их нет в §5.19**;
  - §7.21 объявляет нормативной схемой `/config/schema/commissioning_bundle.schema.json` для
    блока, который смешивает EV3 runtime config и CommissioningBundle; реализация разделяет их
    на `ev3.schema.json` и `commissioning_bundle.schema.json`;
  - §7.21 `network` содержит `hello_retry_window_ms` и `session_stale_ms`, которых нет в
    `config/source/ev3.json` (Release), — их отсутствие схема не ловит;
  - §7.21 размещает `controller_heartbeat_*`, `loop_safe_hold_ms`, `loop_fault_ms` в
    `runtime_defaults`; `ev3.json` — в `safety`; блока `runtime_defaults` нет вовсе.
- **Почему проблема:** разработчик не может определить, какая структура нормативна; попытка
  реализовать §7.21 буквально даст артефакт, отвергаемый `configgen.py`. `MEASURED` реестр
  строится только по `config/source/*.json`, поэтому объявленные в prose `MEASURED` (например
  `max_mapping_scale`) не попадают в реестр и не блокируют `READY`, вопреки S30.
- **Рекомендация:** привести §5.19/§7.21 к фактической разбивке артефактов, явно указав
  правильные пути схем и отметив, какие поля появятся на будущих этапах; либо расширить схемы.
  Добавить в `configgen.py` проверку «каждое поле, объявленное `MEASURED` в prose, существует в
  `config/source` и зарегистрировано» — иначе S30 не обеспечен.
- **Confidence:** HIGH

---

#### H-04 — Safety/timing параметры объявлены конфигурацией, но зашиты в код; `loop_safe_hold_ms` не реализован

- **Severity:** HIGH
- **Тип:** configuration not honoured / missing implementation
- **Файлы:** `ev3/include/phantom/runtime_profile.hpp:6-11` (профиль содержит только 4 поля),
  `ev3/src/controller_main.cpp:33` (загружает только `qualification_only` и
  `actuator_scope_mask`), `:20` (жёстко `false` для трёх commissioning-флагов),
  `:47` (`100000` us heartbeat), `ev3/safety/main.cpp:21` (`100000` us),
  `ev3/include/phantom/controller_core.hpp:13` (`command_timeout_ms=120` как default структуры),
  `:15` (`FixedRing<500>`), `ev3/src/controller_core.cpp:13` (`dt>100000`)
- **Документация:** §7.21 объявляет `command_timeout_ms`, `controller_heartbeat_rate_hz`,
  `controller_heartbeat_timeout_ms`, `loop_safe_hold_ms: 60`, `loop_fault_ms: 100`,
  `motor_output_default`, `flight_recorder_seconds/rate_hz`, `release_retention_days/max_mb`,
  `max_concurrent_control_sessions`. Все они присутствуют в `config/source/ev3*.json`.
- **Код:** `grep` по всем `.cpp/.hpp/.py/.cs` показывает, что ни один из этих ключей не читается
  из конфигурации. Значения совпадают с документированными **случайно** (120/100/500/100), а
  `loop_safe_hold_ms=60` не имеет реализации: промежуточного порога между нормой и
  `FAULT_LOOP_OVERRUN` нет.
- **Почему проблема:** изменение конфигурации не изменит поведение — классический источник
  инцидентов при HIL-настройке. Отсутствие 60-мс порога означает, что джиттер 60–100 мс не
  вызывает ни `SAFE_HOLD`, ни флага `loop_health_flags`.
- **Рекомендация:** расширить `RuntimeProfile` до полного набора, валидировать диапазоны при
  загрузке (fail-closed), реализовать двухуровневый порог. Сделать до этапа 4.
- **Confidence:** HIGH

---

#### H-05 — Structured events и incident-capture FlightRecorder на стороне controller отсутствуют

- **Severity:** HIGH
- **Тип:** missing implementation
- **Файлы:** `ev3/src/controller_core.cpp:16` (запись в ring buffer),
  `ev3/include/phantom/controller_core.hpp:23` (`recorder()` — потребителей нет),
  `ev3/src/controller_main.cpp` (только `std::cerr` при startup-ошибках)
- **Документация:** §7.20.1 перечисляет 17 обязательных классов событий с фиксированной
  структурой из 16 полей, включая «все state transitions», «`STOPPED`, `SAFE_HOLD` с причиной»,
  «controller/safety process loss», «превышение периода цикла». §7.20.2 требует incident-путь:
  freeze ring, `incident_id`, post-fault tail, асинхронное сохранение. §10.5 DoD п.8 требует
  structured events и работающий FlightRecorder.
- **Код:** `phantom-controller` не эмитит **ни одного** structured event. Ring buffer
  заполняется, но не читается, не замораживается и не сохраняется; `incident_id` в telemetry
  всегда нулевой. Сетевые события (§7.20.1, сетевая часть списка) реализованы полностью и
  корректно — пробел именно в controller.
- **Почему проблема:** после инцидента на brick не останется ничего, кроме одной строки
  `SAFETY_TAKEOVER` от supervisor. Диагностируемость (§3.2.4) и §9.24.1 (тесты инцидентов
  FlightRecorder) не обеспечены.
- **Рекомендация:** добавить неблокирующий JSON-эмиттер (stdout → journald, как в
  `phantom-network`) для переходов состояний и fault; incident-сохранение — вместе с этапом 4.
- **Confidence:** HIGH

---

#### H-06 — Расхождение с §7.24: потеря `phantom-safety` даёт `SAFE_HOLD`, а в network-only предикаты безопасности обходятся

- **Severity:** HIGH
- **Тип:** state-machine mismatch / bypassed safety predicate
- **Файлы:** `ev3/src/controller_core.cpp:11` (ветка network-only **перед** проверками),
  `:12` (`safe(State::SafeHold,Fault::ControllerProcess)`), `:13` (loop overrun)
- **Документация:** §7.24, строка таблицы: «`phantom-safety` завис | controller health |
  `BRAKE` + **`STOPPED`** + legacy `FAULT_CONTROLLER_PROCESS`; structured subsystem=SAFETY».
  §10.2, строка «Безопасность и восстановление»: watchdog/`phantom-safety` должны работать «на
  каждом применимом этапе». S20: «Потеря phantom-safety запрещает движение».
- **Код:** при `!safety_alive_` устанавливается `SAFE_HOLD`, а не `STOPPED`; structured event
  не пишется (см. H-05). В профиле network-only ветка `qualification_only && scope==0`
  выполняется **раньше** и безусловно задаёт `fault_=Fault::None`, `state_=Discovery|
  ConnectedUnreferenced`, поэтому потеря supervisor-heartbeat и превышение периода цикла на
  этапе 3 не наблюдаются вообще.
- **Почему проблема:** на этапе 3 нет motor authority, поэтому прямой опасности нет, но
  (а) требование §10.2 не выполняется, (б) Stage-3 стенд не может продемонстрировать
  supervisor-liveness через собственный контроллер, (в) при переходе к scope≠0 разница
  `SAFE_HOLD` vs `STOPPED` меняет требуемую процедуру восстановления.
- **Рекомендация:** вынести проверки `safety_alive_` и `dt` **до** ветки network-only и
  сохранять их результат в наблюдаемом состоянии/флагах даже при нулевом scope; согласовать
  `SAFE_HOLD` vs `STOPPED` с §7.24 (или исправить §7.24, если `SAFE_HOLD` — намеренное
  решение; тогда обновить owner и объяснить, почему latch не нужен).
- **Confidence:** HIGH

---

#### H-07 — Stage-3 IPC contract не покрыт ни одним исполненным cross-implementation тестом

- **Severity:** HIGH
- **Тип:** verification gap
- **Файлы:** `ev3/network/phantom_network.py:34-35` (`IPC_REQUEST`/`IPC_REPLY` struct),
  `ev3/src/network_ipc.cpp:44-66` (разбор по смещениям),
  `ev3/tests/network_ipc_tests.cpp:19-23` (третья, тестовая кодировка),
  `ev3/network/test_phantom_network.py:87-104` (использует `LocalControllerAuthority`, не
  `ControllerIpcAuthority`)
- **Документация:** §7.2.2 задаёт exact 120/64-байтовый контракт как нормативный;
  §11.8 требует cross-codec golden vectors для wire-протокола (сделано), но для IPC
  аналогичного требования нет — при этом §7.2.2 объявляет IPC отдельным safety boundary.
- **Код:** три независимые рукописные кодировки одного layout. Я сверил смещения вручную —
  **сейчас они совпадают**. Однако ни один исполняемый тест не связывает Python-кодировщик с
  C++-разборщиком; единственная такая проверка — `device-auto.py:ev3-udp-session-stage3`, то
  есть DEVICE AUTO, который имеет статус `NOT_RUN`.
- **Почему проблема:** ошибка в одном байте смещения пройдёт все 45 исполняемых тестов и все
  gate’ы PRE-INSTALL, проявившись только на устройстве — то есть ровно там, где отладка
  дороже всего. `CURRENT_STATUS` перечисляет свойства IPC как «зафиксированные implementation
  facts», не отмечая, что они не проверены исполненным тестом.
- **Рекомендация:** сгенерировать golden vectors для `ControllerRequestV1`/`ControllerReplyV1`
  (по образцу `protocol/golden_vectors/v1.json`) и проверять их обеими реализациями; либо
  добавить host-тест, где Python `ControllerIpcAuthority` общается с реальным
  `NetworkIpcBoundary` через временный сокет.
- **Confidence:** HIGH

---

### MEDIUM

---

#### M-01 — Счётчик `nonzero_motor_writes` тавтологичен, но используется как Stage-3 exit gate

- **Файлы:** `ev3/network/phantom_network.py:231` (единственное вхождение — инициализация);
  `ev3/network/test_phantom_network.py:104,117,149,172,186,198,208` (7 утверждений);
  `deploy/scripts/device-auto.py:322-324` (gate `ev3-stage3-zero-output-audit`)
- **Документация:** §10.5 DoD п.10 — «за весь gate зарегистрировано ноль motor writes с
  nonzero duty».
- **Проблема:** счётчик нигде не инкрементируется и не может быть ненулевым (network-процесс
  не имеет motor-пути по построению). Семь тестовых утверждений и один gate проверяют
  константу. Реальное доказательство даёт `zero_state()` (чтение sysfs) и
  `MockMotorBackend::nonzero_writes_` — их достаточно.
- **Рекомендация:** удалить счётчик либо переименовать в
  `motor_write_attempts_rejected` и инкрементировать при попытке `COMMAND` с ненулевым
  `MOTION_ENABLE` вне scope; иначе он даёт ложную уверенность.
- **Confidence:** HIGH

#### M-02 — Android NSD: отсутствует `MulticastLock`; нормализация service type может отбрасывать сервисы

- **Файлы:** `PhantomQuest/Assets/Plugins/.../nsd/PhantomNsdBridge.java:31-47,83-85`;
  `AndroidManifest.xml:8` (объявлен `CHANGE_WIFI_MULTICAST_STATE`, не используется)
- **Документация:** §4.6 — «на старых Android/SDK-extension комбинациях, где foreground mDNS
  требует ручного `WifiManager.MulticastLock`, lock удерживается только bounded временем
  discovery и гарантированно освобождается».
- **Проблема:** (а) разрешение объявлено, кода нет — требование не реализовано; (б)
  `normalize()` снимает только завершающую точку, поэтому если платформа сообщает
  `_phantom-ev3._udp.local.`, `sameType()` вернёт false и сервис будет молча отброшен —
  известная разница поведения между версиями Android/NsdManager. `ACCESS_WIFI_STATE`,
  необходимый для `WifiManager`, тоже не объявлен.
- **Сценарий:** discovery на реальном Quest 3 не находит робота, при том что все host-тесты
  проходят (они используют `FakeDiscoveryBackend`).
- **Рекомендация:** реализовать bounded `MulticastLock`; в `sameType`/`normalize` сравнивать
  по нормализованному «`_service._proto`» с отбрасыванием доменного суффикса. Обязательный
  device-кейс Stage-3 DoD §10.5 п.2.
- **Confidence:** MEDIUM (требует подтверждения на устройстве; отсутствие MulticastLock —
  HIGH-уверенный факт кода)

#### M-03 — Interop проверяется только против симулятора, который расходится с рабочим сервером

- **Файлы:** `tools/quest_validation/run_udp_integration.ps1` (запускает
  `sim/ev3-simulator/phantom_simulator.py`), `sim/ev3-simulator/phantom_simulator.py:16`
  (`session_stale=2.`), `:41-69` (`process`)
- **Расхождения с `ev3/network/phantom_network.py`:** нет token bucket; нет pre-HMAC
  key_slot drop; `session_stale` 2 s вместо конфигурационных 5 s; нет проверок
  `role/key_slot/minor/capabilities` (ERR_AUTH/ERR_UNSUPPORTED формируются только через
  сценарные флаги); нет `end_session` при отказе controller; нет ограничения 32 датаграмм.
- **Проблема:** строка «Stage 3 protocol interoperability PASS» в `CURRENT_STATUS`
  подтверждена против второй реализации, а не против той, что поедет на устройство.
- **Рекомендация:** добавить host-сценарий, где `Stage3NetworkClient` работает против
  реального `phantom_network.py` (с `LocalControllerAuthority`), и зафиксировать в статусе,
  какие сценарии проверены против симулятора, а какие — против рабочего сервера.
- **Confidence:** HIGH

#### M-04 — `PhantomConfig.cs` — мёртвый код с hardcoded IP, MEASURED-значениями и противоречащими порогами

- **Файлы:** `PhantomQuest/Assets/Phantom/Config/PhantomConfig.cs:11-19`
- **Содержимое:** `SimulatorHost="192.168.0.112"`, `SimulatorPort=31337`,
  `L1Meters=L2Meters=0.215`, `MappingRadiusMeters=0.32`, `GripEngageThreshold=0.75f`,
  `GripReleaseThreshold=0.55f`, `Workspace=WorkspaceConfig.Default` (`OuterReach=0.43`),
  `FallbackJointLimits=(-2.8,-1.2,0.0)..(2.8,1.4,2.8)`
- **Проблема:** класс не используется нигде (единственное вхождение — его объявление), но
  компилируется в `Phantom.Runtime`. При этом: `l1_m`/`l2_m` и `axes.*.limits` числятся в
  реестре `MEASURED_REQUIRED` со значением `null`; пороги 0.75/0.55 прямо противоречат
  §5.4.2 (0.45/0.60), реализованному в `EnableHysteresis`; жёстко зашит адрес локальной сети,
  что противоречит §4.6 («выбирать сервис по `robot_id`, а не по IP»); `configgen`
  сканирует MEASURED только по `config/source/*.json` и такой обход реестра не заметит.
- **Рекомендация:** удалить файл или пометить его как `#if UNITY_EDITOR` инструмент с
  значениями, взятыми из конфигурации.
- **Confidence:** HIGH

#### M-05 — Формула отображения §11.1.1 реализована частично; параметры геометрии зашиты

- **Файлы:** `PhantomQuest/Assets/Phantom/Mapping/HumanToRobotMapper.cs:11`;
  `PhantomQuest/Assets/Phantom/Kinematics/PhantomKinematics.cs:29` (`nearAxis=0.05`)
- **Документация:** §11.1.1 / `FR-MAP-08`:
  `mapping_reach_m = min(RobotGeometry.robot_nominal_reach_m, human_arm_reach*max_mapping_scale)`;
  §11.1.2: `require r >= RobotGeometry.yaw_singularity_hold_radius_m`.
- **Код:** `requested = dir * (_robotReach * ratio)` — ограничение
  `human_arm_reach * max_mapping_scale` отсутствует. Идентификаторы `max_mapping_scale`,
  `robot_nominal_reach_m`, `yaw_singularity_hold_radius_m`, `human_vector_min_m` не встречаются
  ни в одном исходном файле; их роль исполняют конструкторные аргументы/константы
  (`_robotReach`, `_nearAxis=0.05`, `_humanVectorMin=0.05`).
- **Почему проблема:** нарушается именно тот предохранитель, ради которого введён
  `max_mapping_scale` — усиление tracking-шума при малом `human_arm_reach`. Реализация
  относится к этапу 8, но класс существует, протестирован и создаёт впечатление готовности.
- **Рекомендация:** дополнить формулу и брать параметры из `CommissioningBundle`/Quest config;
  зарегистрировать `max_mapping_scale` в `measured_parameters.json`.
- **Confidence:** HIGH

#### M-06 — Валидация конфигурации слабее, чем требует спецификация; enforcement MEASURED инвертирован

- **Файлы:** `tools/configgen.py:7` (`json.loads`), `:90`, `:110-113`;
  `config/schema/ev3.schema.json` (корень и `network` — `additionalProperties:true`;
  `safety`/`logging`/`axes.*` без описания свойств)
- **Документация:** §7.21 — «parser/build gate обязан отклонять duplicate mapping keys,
  unknown fields, неверные units/types и незаполненные `MEASURED`, достигшие своего
  `required_before`. Last-key-wins/first-key-wins поведение YAML parser как способ разрешить
  дубликат запрещено». §9.1.2 повторяет то же требование.
- **Код:** `json.loads` молча применяет last-wins к дубликатам ключей; unknown fields
  проходят из-за `additionalProperties:true`; `required_before` нигде не сопоставляется со
  стадией; более того, `configgen` **требует** `value is None` и `evidence is None`, то есть
  первое реальное измерение сломает gate.
- **Рекомендация:** использовать `json.load(..., object_pairs_hook=)` с проверкой дубликатов;
  ужесточить схемы (`additionalProperties:false` + описание свойств `safety`/`logging`/`axes`);
  заменить проверку «всё должно быть null» на «`MEASURED` без значения запрещает stage ≥
  `required_before`», сохранив текущее поведение как частный случай.
- **Confidence:** HIGH

#### M-07 — Логи не ротируются; отсутствуют `runtime-active`/`UNCLEAN_SHUTDOWN`/`LOG_STORAGE_DEGRADED`; логгер Quest может бросить исключение в кадр

- **Файлы:** `PhantomQuest/Assets/Phantom/Logging/QuestJsonlLogger.cs:20-27`;
  `PhantomQuest/Assets/Phantom/Logging/QuestNetworkEventSink.cs:10-14`;
  `ev3/safety/main.cpp:13`
- **Документация:** §8.13.1 (7 суток / 250 MB), §8.13.3 (ротация, atomic rename,
  `runtime-active` маркер, `UNCLEAN_SHUTDOWN`, «ошибка записи не влияет на цикл управления»,
  `LOG_STORAGE_DEGRADED`). Конфигурация содержит `release_retention_days: 7`,
  `release_max_mb: 250`.
- **Код:** grep по всей кодовой базе даёт **ноль** совпадений для `runtime-active`,
  `UNCLEAN_SHUTDOWN`, `LOG_STORAGE_DEGRADED`, ротации и retention. Quest создаёт новый
  `<runId>.jsonl` на каждый запуск и никогда не удаляет старые; `_writer.WriteLine` не
  обёрнут в try/catch, а `Record` вызывается из `Stage3NetworkClient.Emit` внутри `Tick()`,
  который вызывается из `PhantomRuntime.Update()`.
- **Сценарий:** заполнение app-private хранилища после многих запусков → `IOException` из
  `Update()` каждый кадр → сетевой клиент перестаёт обслуживаться.
- **Рекомендация:** ограничить каталог по числу/объёму файлов при старте, обернуть запись в
  try/catch с одноразовым `LOG_STORAGE_DEGRADED`; на EV3 добавить ротацию
  `safety-emergency.log` и `runtime-active` маркер.
- **Confidence:** HIGH

#### M-08 — `PRE-INSTALL AUTO` не проверяет актуальность specification manifest и section index

- **Файлы:** `scripts/pre-install-auto.ps1` (список `Run-Check` не содержит `specgen`,
  `docindex`, `doclint`); `.github/workflows/ci.yml:7` (содержит их)
- **Документация:** §9.1.2 — «Итоговый `PASS` … обязан содержать `git_commit`,
  `source_tree_hash`, `specification_sha256`, `protocol_schema_hash`…»; `AGENTS.md` и
  `README.md` требуют этих генераторов после изменения нормативной документации.
- **Проблема:** отчёт записывает `specification_sha256` как хэш **файла**
  `docs/PHANTOM_SPECIFICATION.md`, не проверяя, что этот файл соответствует текущим
  нормативным документам. При изменении нормативного документа без запуска `specgen.py`
  манифест остаётся прежним, `configgen --check` проходит (он тоже хэширует только манифест),
  и PRE-INSTALL выдаёт `PASS` с идентичностью, которая фактически не покрывает спецификацию.
  CI это ловит, но именно PRE-INSTALL авторизует установку (`install_authorized`).
- **Рекомендация:** добавить три проверки в `pre-install-auto.ps1`.
- **Confidence:** HIGH

#### M-09 — CI покрывает лишь часть обязательного набора PRE-INSTALL

- **Файлы:** `.github/workflows/ci.yml`
- **Отсутствуют:** `ev3/network/test_phantom_network.py` (9 тестов Stage-3 network/security),
  `tools/test_artifact_check.py`, `tools/quest_validation/test_analyze.py`,
  `tools/ev3_validation/test_analyze.py`.
- **Проблема:** регрессия в основном сетевом воркере EV3 не будет поймана в PR — только
  локальным запуском PRE-INSTALL на Windows.
- **Рекомендация:** добавить эти четыре команды в существующий Linux-job (все они
  чистый Python, зависимостей нет).
- **Confidence:** HIGH

#### M-10 — Нет таймаута жизни IPC-сессии на стороне controller

- **Файлы:** `ev3/include/phantom/network_ipc.hpp:26`; `ev3/src/network_ipc.cpp:61-63`
- **Документация:** §7.2.2 — «Даже если invalidate IPC потерян, controller
  command-freshness/**session watchdog** обязан прекратить motion».
- **Проблема:** `session_active_` сбрасывается только явным `SESSION_INVALIDATE` или
  перезаписывается новым `SESSION_OPEN`. Freshness (500 ms) применяется к отдельному
  сообщению, но не к сессии. Потеря invalidate → controller навсегда считает сессию активной
  и рапортует `network_session_active()==true`.
- **Влияние сейчас:** ограничено (используется только для выбора
  `Discovery`/`ConnectedUnreferenced`). На этапе 4+ — существенно.
- **Рекомендация:** хранить `last_ipc_us` и сбрасывать сессию при превышении порога.
- **Confidence:** HIGH

#### M-11 — `security_scan.py` намного уже, чем декларируемый provisioning audit

- **Файлы:** `tools/security_scan.py`
- **Документация:** `TEST_PLAN.md:1157` — «release provisioning audit подтверждает отсутствие
  Wi-Fi credential/control PSK/commissioning PSK в Git, APK/resources, build manifest,
  `CommissioningBundle`, DNS-SD TXT, telemetry и обычных логах».
- **Код:** два regex (PEM private key; `control|commissioning_psk = <64hex>`), с пропуском
  `.secrets/`, `protocol/golden_vectors/` и **любого пути, содержащего `/test`** (что включает
  `tools/test_*.py`, `PhantomQuest/.../Tests/`, `ev3/tests/`). Не покрывает: бинарный PSK,
  Wi-Fi passphrase, base64, пароль keystore, содержимое APK/manifest/логов.
- **Смягчение:** `artifact_check.verify_quest_embedded_identity` действительно проверяет APK
  на путь keystore и пароль подписи — это лучшая часть покрытия.
- **Рекомендация:** расширить сканер (энтропийная эвристика для 32-байтовых файлов, поиск в
  build manifest/generated config), убрать исключение `/test` или сузить его до
  `golden_vectors`.
- **Confidence:** HIGH

#### M-12 — Bench-подсистема не документирована и провижинит `robot` NOPASSWD-root, не снимаемый при установке production

- **Файлы:** `ev3/bench/**` (1 740 строк), `scripts/ev3-bench-*` (10 скриптов),
  `tools/ev3_validation/analyze.py` (1 268 строк), `scripts/ev3-bench-setup-sudo`,
  `scripts/ev3-bench-common:6-14`, `ev3/bench/README.md`
- **Документация:** отсутствует в `ENGINEERING.md` §8.1, в `ARCHITECTURE.md`, в spec set.
  Единственные упоминания — косвенные (`EV3_SPECIFICATION.md:1185` про каталог результатов).
- **Проблемы:**
  1. Крупнейший по объёму компонент репозитория (~22 % кода) вне карты документации;
  2. `ev3-bench-setup-sudo` устанавливает
     `robot ALL=(root) NOPASSWD: /home/robot/phantom-bench/bin/ev3-bench` — путь писуем
     пользователем `robot`, поэтому правило эквивалентно неограниченному root для него;
  3. `install-release` не проверяет и не удаляет `/etc/sudoers.d/phantom-ev3-bench`;
  4. `.ev3-ssh/id_ed25519` — незашифрованный ключ в рабочей копии;
  5. `ev3/bench/README.md` внутренне противоречив в port mapping (Large=`outB`/Medium=`outA`
     против «documented Large=`outA`, Medium=`outD`»), и это не production-маппинг из
     `config/source/ev3.json`.
- **Почему проблема:** brick, на котором гоняли bench, а затем поставили production, имеет
  тривиальный обход всего DAC-разделения `phantom-ctrl`/`phantom-net`, на котором построена
  часть safety-аргументации §7.2.2.
- **Рекомендация:** описать bench в `ENGINEERING.md` как явно непроизводственную оснастку;
  добавить в `install-release` проверку/удаление bench-sudoers; или перенести бинарь в
  root-owned каталог.
- **Confidence:** HIGH

#### M-13 — Канонизация не является RFC 8785 JCS, хотя объявлена таковой

- **Файлы:** `tools/protocolgen.py:9-10`, `tools/configgen.py:6`,
  `ev3/network/phantom_network.py:139-140`, `tools/build_identity.py:12-13`
- **Документация:** §11.8 gate п.1 — «RFC 8785 JCS `wire_schema.canonical.json`»;
  §7.21 — «Compatibility `content_hash`/`commissioning_bundle_hash` считается по RFC 8785 JCS
  UTF-8 bytes»; §4.7.5 — «canonicalize по JCS»; `ENGINEERING.md:436` — «Quest и EV3 независимо
  вычисляют hash candidate bundle из одних canonical components».
- **Код:** `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",",":"))`.
  Отличия от JCS: сортировка по code point вместо UTF-16 code units и, главное, **сериализация
  чисел по правилам Python, а не ECMAScript**: `1.0` → `"1.0"` в Python и `"1"` по JCS.
- **Сейчас:** расхождений нет — схема и bundle содержат только целые и `null`, все хэши
  считаются одной реализацией.
- **Риск:** как только `MEASURED` значения (`l1_m`, `payload_mass_max_kg`,
  `swept_volume_margin_m`, …) будут заполнены и Quest начнёт независимо считать
  `commissioning_bundle_hash` на C# (что прямо требуется §4.7.5), любое значение вида `1.0`
  даст расхождение хэшей → `ERR_HASH_MISMATCH` → блокировка движения без очевидной причины.
- **Рекомендация:** реализовать настоящую JCS-сериализацию чисел (или запретить схемой
  числа с плавающей точкой в hashed-компонентах, потребовав фиксированную строковую запись).
  Решить до этапа 7.
- **Confidence:** HIGH на технический факт; MEDIUM на вероятность реализации

#### M-14 — Мелкие расхождения контрактов IPC/heartbeat

- **Файлы:** `ev3/src/runtime_guard.cpp:14` (`chmod 0660` без `chown` в
  `phantom-safety-ipc`), `:17` (`drain()` — неограниченный цикл),
  `ev3/src/network_ipc.cpp:55-57` (takeover сессии другим PID)
- **Документация:** §7.2.4 — «Heartbeat socket endpoints после `bind` обязаны иметь mode
  `0660` и dedicated group `phantom-safety-ipc`»; §7.2.2 — bounded drain как принцип.
- **Проблемы:** (а) сокет контроллера получает группу `phantom-motor` (egid процесса), а не
  `phantom-safety-ipc`; практически работает, так как peer — root, но буква требования не
  выполнена и группа шире необходимого; (б) `HeartbeatChannel::drain` не ограничен, в отличие
  от network IPC (деградация fail-safe через `FAULT_LOOP_OVERRUN`, но асимметрия выглядит
  случайной); (в) `SESSION_OPEN` от другого PID молча перехватывает сессию, тогда как
  `ERR_CONTROL_SESSION_BUSY` возвращается только тому же PID — контракт «одна сессия»
  держится лишь на том, что процесс один, и это не задокументировано.
- **Рекомендация:** `chown` сокета в `phantom-safety-ipc`; ограничить heartbeat drain
  (например 16); задокументировать семантику takeover.
- **Confidence:** HIGH

#### M-15 — `PhantomStateMachine`: недокументированное состояние, ручной дубликат wire-enum, отсутствие S9

- **Файлы:** `PhantomQuest/Assets/Phantom/Mapping/PhantomStateMachine.cs:3,15-31`;
  `PhantomQuest/Assets/Phantom/Tests/Editor/ProtocolAndStateTests.cs` (тесты
  `StateMachine_RequiresReleaseAndNewRisingEdge`, `StateCodesMatchWireContract`)
- **Документация:** §4.3 — «`FAULT` не является отдельным wire state protocol v1»;
  S9 и §5.4.2 — `armed=true` только после свежей telemetry с
  `last_accepted_command_sequence >= release_off_sequence`; `AGENTS.md` — «не дублируй
  packet offsets/sizes как competing source».
- **Проблемы:** (а) `Fault=100` — состояние, отсутствующее в документированной модели;
  (б) значения `Boot=0 … Commissioning=10` записаны литералами, а не через `WireV1.State`
  (в отличие от корректного `RobotRuntimeState`); тест сверяет 3 из 11 значений и тоже с
  литералами; (в) `Update()` не имеет входа от telemetry, поэтому S9 не реализуется, при том
  что имя теста утверждает обратное.
- **Рекомендация:** вывести `PhantomState` из `WireV1.State` (плюс отдельный локальный флаг
  fault), добавить вход `releaseConfirmed` перед этапом 8, переименовать тест.
- **Confidence:** HIGH

#### M-16 — Бюджет повторов `wifi-autoconnect` превышает `TimeoutStartSec` его unit

- **Файлы:** `deploy/scripts/wifi-autoconnect:22-40`;
  `deploy/systemd/phantom-wifi-autoconnect.service` (`TimeoutStartSec=120`)
- **Проблема:** цикл выполняет до 12 попыток; каждая содержит `connmanctl scan` (без
  таймаута), `timeout 25 connmanctl connect` на профиль и `sleep 5`. Реальный бюджет одной
  попытки ≈ 30–40 с, поэтому попытки 4–12 недостижимы: systemd убьёт unit на ~120 с.
  `install-release` затем проверяет `systemctl is-active … phantom-wifi-autoconnect.service`
  и при отказе выполняет **rollback всей установки**.
- **Рекомендация:** привести число попыток и таймауты в соответствие с `TimeoutStartSec` (или
  наоборот), обернуть `connmanctl scan` в `timeout`.
- **Confidence:** HIGH

#### M-17 — `AGENTS.md` предполагает конкретного агента; правила навигации и Skills не действуют вне Codex

- **Файлы:** `AGENTS.md` (разделы «Назначение», «Навигация по контексту» п.6),
  `.agents/skills/*`, `docs/PHANTOM/exec-plans/README.md`
- **Проблема:** отсутствует `CLAUDE.md`, поэтому утверждение «Codex получает этот файл через
  механизм проектных инструкций… не трать вызов на повторное чтение» неверно для Claude Code —
  агент, доверившийся ему, будет работать без инвариантов проекта. Аналогично `.agents/skills/`
  не обнаруживается Claude Code (ожидается `.claude/skills/`), и пять качественных
  `phantom-*` skills недоступны.
- **Рекомендация:** добавить `CLAUDE.md`, ссылающийся на `AGENTS.md`; продублировать skills в
  `.claude/skills/`; переформулировать инструкцию как условную.
- **Confidence:** HIGH

---

### LOW

- **L-01 — §8.1 дерево репозитория неполно и содержит несуществующий каталог.**
  Отсутствуют `SPECIFICATION_GOVERNANCE.md` и `IMPLEMENTATION_STAGES.md` (оба — нормативные
  члены `spec-set.json`), `mechanical/`, `results/`, `ev3/bench/`. Присутствует
  `protocol/fuzz_corpus/`, которого нет и который больше нигде не упоминается.
  Файл: `docs/PHANTOM/ENGINEERING.md:15-66`. Confidence: HIGH.

- **L-02 — Несогласованные единицы в prose.** §4.7.5 перечисляет `max_duty_pct`, схема —
  `max_duty_permille`; §7.19.2 — `duty_pct`, схема — `duty_permille`; §5.19 —
  `calibration_jog_max_duty_pct`. Разница в 10 раз при буквальной реализации. Confidence: HIGH.

- **L-03 — Три написания пути схемы bundle:** `/config/schema/commissioning_bundle.schema.json`
  (§7.21) и `/config/commissioning_bundle.schema.json` (§9.1.2). Confidence: HIGH.

- **L-04 — `protocol/wire_schema.yaml` содержит JSON;** `protocol/README.md` и
  `protocol/protocol.md` — почти дублирующие тексты (два mutable mirror при явном запрете
  таких дубликатов в `AGENTS.md`). Confidence: HIGH.

- **L-05 — Требования к среде разработчика не задокументированы.**
  `C:\Program Files\Unity\Hub\Editor\6000.3.22f1\...` жёстко зашит в
  `quest-test.ps1`, `quest-device-auto.ps1`, `compile_and_smoke.ps1`,
  `run_udp_integration.ps1`; `pre-install-auto.ps1` требует `wsl.exe -d Ubuntu`;
  bench-скрипты требуют Git Bash. Ни одно из этих требований не заявлено в §8.5/§8.8.
  Confidence: HIGH.

- **L-06 — Ручные маски вместо generated констант в Quest-клиенте.**
  `Stage3NetworkClient.cs:204` — `(telemetry.StatusFlags & 0x383u)` и
  `telemetry.PayloadState != 2` вместо `WireV1.TelemetryStatusFlags*` /
  `WireV1.PayloadState.Unknown`. Противоречит правилу `AGENTS.md` о недублировании
  generated protocol constants. Confidence: HIGH.

- **L-07 — `gripper_capabilities` без определения.** Поле валидируется как 2-битное
  (`&~3`) в `phantom_protocol.py:66`, `ServerProtocol.cs` и в Quest-клиенте, но его биты не
  определены ни в `wire_schema.yaml.bitfields`, ни в prose. Confidence: HIGH.

- **L-08 — Диагностический HUD смешивает языки.** `Stage3NetworkUi.cs:20` выводит
  `value.RemoteState` (имя C#-enum, латиница) и числовой `value.Fault` в русскоязычном
  интерфейсе; §3.1.9/FR-UI требуют русских понятных сообщений. Confidence: HIGH.

- **L-09 — Canonical-zero требования IPC не проверяются полностью.** §7.2.2 требует
  `command_payload=0` для `SESSION_OPEN`, `client_nonce=0` для `COMMAND_SNAPSHOT`,
  нулей для `SESSION_INVALIDATE`, `remote_family=4` для всех типов;
  `ev3/src/network_ipc.cpp:48-52` проверяет только часть. Defence-in-depth, не эксплуатируемо.
  Confidence: HIGH.

- **L-10 — Нет политики очистки `build/`.** 24 накопленных пакета, включая
  `phantom-audit-snapshot-*`, три `stage3-network-only-dev*.tar.gz` и диффы. Каталог
  gitignored; на артефакты не влияет, но `artifact_check` перечисляет их в PRE-INSTALL
  отчёте по маске. Confidence: HIGH.

- **L-11 — `AGENTS.md` не упоминает существующие области репозитория** (`ev3/bench/`,
  `results/**`, `mechanical/`) и не даёт правил обращения с ними. Confidence: HIGH.

- **L-12 — `AGENTS.md`/governance не разрешают случай «поле есть в нормативной prose,
  но отсутствует в схеме»** — именно этот случай реализован (H-03). Confidence: HIGH.

---

### INFO

- **I-01 — Дисциплина evidence образцовая.** Разделение PASS/FAIL/NOT_RUN/N_A,
  `install_authorized=false` при dirty worktree, запрет наследования PASS при смене
  `specification_sha256`/`protocol_schema_hash` — всё это реализовано в коде, а не только
  описано. Сохранить.

- **I-02 — Отсутствие TODO/FIXME/HACK во всей кодовой базе.** Ноль совпадений по
  `.cs/.py/.cpp/.hpp/.ps1`. Редкая и полезная дисциплина.

- **I-03 — `set_duty` пишет `command=run-direct` при каждом вызове** и теряет разрешение
  `duty_permille` из-за целочисленного `duty/10`. На этапе 3 не используется; учесть перед
  первым движением (`ev3/src/ev3_sysfs_backend.cpp:59`).

- **I-04 — Unity template/sample ассеты в трекинге** (`VRTemplateAssets`, XR Interaction
  Toolkit samples, Oculus samples, TextMesh Pro) — сотни файлов, не относящихся к PHANTOM и
  не упомянутых в §8.1. Влияние на APK не оценивалось; стоит проверить при оптимизации сборки.

- **I-05 — `results/quest/environment.md` и summaries** в трекинге дают хороший
  человекочитаемый след, но `ENGINEERING.md` не содержит ни одной ссылки на `results/`.

- **I-06 — Рассмотрите фиксацию «что намеренно не реализовано».** Значительная часть
  findings этого отчёта — не дефекты, а разрыв между полной спецификацией и реализованным
  срезом. Небольшой машиночитаемый файл «требование → этап реализации» снял бы неоднозначность
  и позволил бы автоматически отличать «не сделано по плану» от «забыто».

---

## 20. Prioritized Remediation Plan

### P0 — исправить немедленно (до попытки Stage-3 physical acceptance)

| # | Что | Почему | Компоненты | Сложность | Зависимости |
|---|---|---|---|---|---|
| 1 | **C-01** Реализовать provisioning CONTROL PSK на Quest | без этого шаги 4–7 физического gate невыполнимы | Quest C#/Java, host-скрипт, DEVICE AUTO | MEDIUM | — |
| 2 | **C-02** Не завершать controller по `LOCAL_STOP`; удалять boot-id при выходе; `BindsTo=` для network/mDNS | невосстановимое состояние + ложная индикация исправности | `controller_main.cpp`, `controller_core.cpp`, systemd units | SMALL (минимальный вариант) / MEDIUM (полный latch) | — |
| 3 | **H-01** Реализовать `ControllerTelemetrySnapshotV1` и убрать синтез telemetry | Stage-3 DoD требует controller state/fault; закрывает часть C-02 | `network_ipc.*`, `controller_core.*`, `phantom_network.py` | MEDIUM | №2 желательно раньше |
| 4 | **M-02** MulticastLock + нормализация service type | discovery на реальном Quest может не работать | Java bridge, AndroidManifest | SMALL | — |
| 5 | **M-01** Убрать/переопределить `nonzero_motor_writes` | тавтологичный gate в Stage-3 exit criteria | `phantom_network.py`, тесты, `device-auto.py` | SMALL | — |
| 6 | **H-07** Golden vectors для IPC либо host-тест реальной связки | единственный непроверенный safety boundary | `tools/`, `ev3/tests`, Python тест | SMALL | — |

### P1 — до следующего крупного этапа (перед этапом 4, первое движение)

| # | Что | Почему | Компоненты | Сложность | Зависимости |
|---|---|---|---|---|---|
| 7 | **H-04** Загружать safety/timing параметры из конфигурации; реализовать `loop_safe_hold_ms` | конфигурация не влияет на поведение приводов | `runtime_profile.*`, `controller_core.*` | MEDIUM | H-03 (согласовать имена) |
| 8 | **H-06** Вынести safety-heartbeat и loop-overrun до ветки network-only; согласовать `SAFE_HOLD`/`STOPPED` с §7.24 | обход safety-предикатов | `controller_core.cpp`, §7.24 | SMALL | — |
| 9 | **H-05** Structured events controller (минимум: state transitions, fault, LOCAL_STOP, overrun) | без них инцидент не диагностируется | `controller_core/main` | MEDIUM | — |
| 10 | **M-10** Watchdog жизни IPC-сессии | требование §7.2.2 | `network_ipc.*` | SMALL | №6 |
| 11 | **M-07** Ротация логов + `runtime-active`/`UNCLEAN_SHUTDOWN` + try/catch в Quest-логгере | ресурсная и надёжностная проблема | Quest logger, EV3 | MEDIUM | — |
| 12 | **M-06** Duplicate keys, unknown fields, корректный `required_before` | первое реальное измерение сломает gate | `configgen.py`, схемы | MEDIUM | H-03 |
| 13 | **M-03** Host-тест реальный клиент ↔ реальный сервер | текущий interop PASS получен против симулятора | `tools/quest_validation`, `sim` | MEDIUM | — |
| 14 | **M-08 / M-09** Дополнить PRE-INSTALL (spec/index/doclint) и CI (network/artifact тесты) | gate авторизует установку с непроверенной spec identity | скрипты, CI | SMALL | — |
| 15 | **M-12** Документировать bench; удалять bench-sudoers при установке production | обход DAC-разделения на production brick | `ENGINEERING.md`, `install-release` | SMALL | — |
| 16 | **M-16** Согласовать бюджет `wifi-autoconnect` с `TimeoutStartSec` | rollback установки при задержке Wi-Fi | скрипт/unit | SMALL | — |

### P2 — желательно исправить

| # | Что | Компоненты | Сложность |
|---|---|---|---|
| 17 | **H-02** Генерировать `protocol/protocol.md` и включить в `--check` (или убрать из §11.8 и всех ссылок) | `protocolgen.py`, docs | SMALL |
| 18 | **H-03** Привести §5.19/§7.21 к фактической разбивке артефактов и путям схем | docs | MEDIUM |
| 19 | **M-13** Настоящая JCS-сериализация чисел (или запрет float в hashed-компонентах) | `configgen`, `protocolgen`, будущий C# | MEDIUM |
| 20 | **M-05** Дополнить формулу отображения `max_mapping_scale`; брать геометрию из bundle | Quest mapping/IK, config | MEDIUM |
| 21 | **M-11** Расширить `security_scan.py`; убрать исключение `/test` | tools | SMALL |
| 22 | **M-15** Вывести `PhantomState` из `WireV1.State`; добавить вход S9; переименовать тест | Quest | SMALL |
| 23 | **M-14** `chown` heartbeat-сокета; ограничить heartbeat drain; задокументировать takeover | EV3 | SMALL |
| 24 | **M-17** `CLAUDE.md` + skills в `.claude/skills/` | корень репозитория | SMALL |
| 25 | **M-04** Удалить или изолировать `PhantomConfig.cs` | Quest | SMALL |

### P3 — cleanup / документация

| # | Что | Сложность |
|---|---|---|
| 26 | **L-01** Актуализировать дерево §8.1 (добавить пропущенное, убрать `fuzz_corpus/` или создать его) | SMALL |
| 27 | **L-02/L-03** Исправить единицы (`_pct` → `_permille`) и пути схем | SMALL |
| 28 | **L-04** Объединить `protocol/README.md` и `protocol/protocol.md` | SMALL |
| 29 | **L-05** Задокументировать среду разработчика; параметризовать пути Unity/adb | SMALL |
| 30 | **L-06** Заменить `0x383u`/`!=2` на generated константы | SMALL |
| 31 | **L-07** Определить биты `gripper_capabilities` в схеме | SMALL |
| 32 | **L-08** Русские подписи состояний/ошибок в HUD | SMALL |
| 33 | **L-09** Дополнить canonical-zero проверки IPC | SMALL |
| 34 | **L-10** Политика очистки `build/` | SMALL |
| 35 | **L-11/L-12** Дополнить `AGENTS.md` областями репозитория и правилом prose-vs-schema | SMALL |
| 36 | **I-06** Машиночитаемая карта «требование → этап реализации» | MEDIUM |

**Критический путь:** №1 и №2 независимы и могут выполняться параллельно; №3 логично делать
сразу после №2 (общий IPC-канал); №4 и №5 независимы. Без №1 физический gate Stage 3 не
стартует вовсе, поэтому он приоритетнее остальных.

---

## 21. Questions / Unresolved Decisions

Вопросы, которые невозможно разрешить по содержимому репозитория:

1. **Является ли `PhantomConfig.cs` намеренно сохранённым черновиком?** Если да — почему он
   содержит числовые значения параметров, объявленных `MEASURED_REQUIRED`, и адрес локальной
   сети? Если нет — можно удалять (M-04).

2. **`SAFE_HOLD` или `STOPPED` при потере `phantom-safety`?** Код и §7.24 расходятся.
   Какой вариант является намеренным решением, и какая процедура восстановления
   предполагается? (H-06)

3. **Как физически предполагается доставлять control PSK на Quest?** Инженерный экран в
   Diagnostic-сборке, отдельная provisioning-активность через `adb`, QR-код, что-то ещё?
   §8.11 говорит «вне исполнительного UDP-протокола», но не задаёт механизм (C-01).

4. **Планируется ли `protocol/fuzz_corpus/`?** Каталог заявлен в §8.1, но нигде больше не
   упоминается; TEST_PLAN требует fuzz-кейсов, но не привязывает их к корпусу (L-01).

5. **Должен ли Quest Stage-3 клиент отправлять `COMMAND` при scope `0x00`?** EV3 и DEVICE AUTO
   это поддерживают/требуют, Quest-клиент — нет. Это осознанное решение или пропуск?

6. **Кто будет вычислять `commissioning_bundle_hash` на стороне Quest** (C#), и какая
   каноникализация будет использована? От этого зависит серьёзность M-13.

7. **Является ли `ev3/bench` частью поставляемого продукта или чисто локальной оснасткой?**
   От ответа зависит, нужно ли включать его в spec set, SBOM и security-периметр (M-12).

8. **Какова целевая среда исполнения `pre-install-auto.ps1`** — только рабочая станция
   разработчика с Unity+WSL+Docker, или предполагается CI-хост? CI сейчас покрывает лишь
   часть, и неясно, намеренно ли (M-09).

9. **Планируется ли `CLAUDE.md` / поддержка нескольких агентов**, или проект осознанно
   привязан к Codex? (M-17)

---

## 22. Final Assessment

| Направление | Оценка | Обоснование |
|---|---|---|
| **Architecture** | **8/10** | Границы подсистем, модель authority, fault-containment, boot-id как session epoch, DAC-разделение и schema-first протокол — всё выбрано правильно и реализовано последовательно. Честное признание ограничений (`phantom-safety` не независим, `phantom-network` в TCB) заметно повышает доверие. Снимаю два балла за два конкретных решения, требующих пересмотра: синтез telemetry в network-процессе и завершение controller по `LOCAL_STOP`. |
| **Documentation correctness** | **7/10** | Внутренне спецификация на редкость непротиворечива: state machine, latch-семантика, release-handshake и safety-инварианты согласованы между четырьмя документами. Ошибок в формулах нет (IK/FK сверены посимвольно). Снижение — за уверенные ссылки на несуществующий generated artifact, расхождение §5.19/§7.21 с фактической схемой, единицы `_pct` vs `_permille` и неполное дерево §8.1. |
| **Documentation completeness** | **8/10** | Для протокола, сессий, состояний, safety и этапов спецификация самодостаточна: сторонний разработчик может реализовать систему, не угадывая поведение. Пробелы: конфигурация (нельзя реализовать по §7.21 и попасть в схему), полностью недокументированная bench-подсистема (22 % кода), отсутствие описания `results/**` и требований к среде разработчика. |
| **Implementation/spec consistency** | **6/10** | Там, где реализация существует, она обычно очень точна — особенно wire-протокол, session lifecycle, scope-инварианты и bounded-ресурсы. Балл снижен за концентрированные расхождения в наблюдаемости: telemetry, structured events, FlightRecorder, конфигурация, `STOPPED`-recovery, provisioning. Это не мелкие неточности, а места, где документация описывает механизм, которого нет. |
| **Reliability / fault tolerance** | **6/10** | Обработка сетевых отказов сделана образцово: 20+ сценариев покрыты и проверены. Локальные отказы слабее: один невосстановимый путь (C-02), отсутствие session watchdog IPC, отсутствие retry IPC, обход safety-предикатов в network-only, отсутствие ротации логов. Физическая безопасность при этом всюду сохраняется — система деградирует в сторону тормоза, а не движения. |
| **Test coverage quality** | **7/10** | 45 исполняемых тестов + 81 проверка клиента + 21 golden vector — я запустил их и подтвердил. Негативные кейсы, sanitizers, property-подобные проверки, честный `NOT_RUN`. Снижение за три вещи: тавтологичный `nonzero_motor_writes`, interop только против симулятора и полное отсутствие проверки IPC-связки. Тесты качественные, но в трёх местах измеряют не то, что декларируют. |
| **Maintainability** | **7/10** | Сильные стороны: generated artifacts с `--check`, build identity, doclint, отсутствие TODO, ADR для ключевых решений, продуманные Skills. Слабые: экстремально плотный стиль (несколько операторов и целые функции в одной строке) существенно затрудняет review и точную локализацию дефектов; мёртвый код; ручные дубликаты enum и масок; недокументированная bench-подсистема. |
| **Overall readiness** | **6/10** | Для заявленного среза (этапы 1–3, software/build) проект действительно готов: все детерминированные gate’ы проходят, идентичности зафиксированы, hardware честно помечен `NOT_RUN`. Но **ближайший физический gate Stage 3 в текущем состоянии не пройдёт**: нет provisioning PSK (C-01), telemetry не отражает controller (H-01, требуется DoD §10.5), и `LOCAL_STOP` ведёт в невосстановимое состояние (C-02). После P0-исправлений оценка обоснованно поднимется до 8. |

### Итоговое суждение

Это зрелый, дисциплинированный проект с необычно сильной инженерной инфраструктурой и
качественной спецификацией. Он **не страдает** типичными болезнями подобных проектов:
здесь нет фальшивых PASS, нет молчаливого дрейфа generated-артефактов, нет секретов в
репозитории, нет размытых границ ответственности.

Его характерный риск иной: **спецификация настолько подробна, что легко принять описанный
механизм за существующий**. Именно в этом сосредоточены все CRITICAL и HIGH findings —
не в качестве написанного кода, а в разрыве между уверенной документацией и реализованным
срезом, который в трёх местах не отмечен как нереализованный и в трёх местах закрыт тестами,
измеряющими не то, что заявлено.

Шесть P0-исправлений (одно MEDIUM, пять SMALL) закрывают этот разрыв для Stage 3.
