# Stage 3 network-only: свежий hardware-run после lifecycle migration

> **Тип:** execution plan; ненормативный
> **Область:** Stage 3, Quest 3, EV3, PROVISION/TRANSFER/INSTALL/START
> **Начало:** 2026-09-10, source baseline `ce00d9f4e9452bc440d644f2b803db4f6c6279f0`
> **Status:** ACTIVE
> **Supersedes:** `STAGE3_HARDWARE_ACCEPTANCE.md`
> **Superseded by:** N_A
> **Normative owners:** `IMPLEMENTATION_STAGES.md` §10.5, `ENGINEERING.md` §8.5/§8.7/§8.8, `TEST_PLAN.md` §9.1
> **Hardware/evidence state:** все hardware-фазы нового candidate `NOT_RUN`

## Цель

Установить и запустить один свежий exact Stage-3 Diagnostic candidate на назначенной паре
Quest 3 + EV3, остановиться после bounded `START` и разобрать phase timings, readiness,
первый непосредственный отказ и terminal state до отдельного запуска DEVICE INTEGRATION TEST.

## Границы

- Только network-only профиль: `qualification_only=true`, `actuator_scope_mask=0x00`,
  `safety_observation_mask=0x00`, `required_user_inputs=NONE`.
- CONTROL credential создаётся только явной фазой `PROVISION PAIR`; commissioning credential
  Stage 3 не требуется и не создаётся.
- Текущая локальная проверка дала `LOCAL_PAIR_STATE_ABSENT`, поэтому новый hardware-run
  начинается с явного `PROVISION` и не принимает legacy credentials как доказательство пары.
- В подготовительной сессии запрещены ADB discovery/install/shell, SSH/SCP, device discovery,
  `PROVISION`, `TRANSFER`, `INSTALL`, `START`, DEVICE, HIL и RECOVERY.
- После Quest/EV3 `START` дальнейшие автоматические фазы не запускаются: сначала анализируются
  сохранённые lifecycle reports.

## Этапы работы

- [ ] M1 — выполнить явный fixed-pair `PROVISION` с доверенным EV3 fingerprint и проверить complete local record.
- [ ] M2 — выполнить EV3 `TRANSFER`, EV3 `INSTALL` и Quest `INSTALL` exact Diagnostic artifacts.
- [ ] M3 — выполнить EV3 `START`, затем Quest `START`; сохранить timings/readiness/first failure/terminal state.
- [ ] M4 — после отдельного решения запустить DEVICE INTEGRATION TEST exact installed builds.
- [ ] M5 — выполнить оставшиеся Stage-3 HIL/manual cases и опубликовать immutable evidence.

## Журнал прогресса

- Source baseline и lifecycle/provisioning refactor подтверждены на clean HEAD `ce00d9f4...`.
- `scripts\\phantom.cmd TEST EV3 -Profile Diagnostic` — PASS, 4/4 CTest.
- `scripts\\phantom.cmd TEST QUEST` — PASS, 32/32 Unity EditMode.
- Generated config/protocol/spec, doc index/lint, spec contract, implementation map и security
  checks — PASS; hardware evidence из этих проверок не выводится.
- Read-only local fixed-pair validation: `LOCAL_PAIR_STATE_ABSENT`; state не создавался и не ремонтировался.

## Решения

- Свежие EV3 и Quest artifacts строятся по одному разу из clean tracked source после фиксации
  этого плана; повторная reproducibility build в этой задаче не выполняется.
- Exact build IDs, artifact paths и SHA-256 берутся из штатных BUILD results и передаются
  hardware-командам явно; старый `PRE-INSTALL AUTO` не используется.

## Проверка

- Off-hardware проверки перечислены в журнале и относятся только к source candidate.
- `PROVISION`, `TRANSFER`, `INSTALL`, `START`, DEVICE INTEGRATION TEST, HIL и MANUAL
  ACCEPTANCE: `NOT_RUN` до подключения устройств.

## Оставшаяся работа / blockers

- Подключить назначенные Quest 3 и EV3 и выполнить M1–M3 точными командами для свежих artifacts.
- После M3 остановиться; DEVICE INTEGRATION TEST является отдельным следующим решением.
