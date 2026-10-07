# Текущее состояние реализации PHANTOM

## Текущее состояние

**Stage 3 не завершён.** EV3 Diagnostic ARM BUILD и проверка пакета выполнены
для `PHANTOM-BUILD-V4` и обновлённого `HELLO_ACK`; долговечный отчёт ещё не опубликован.
Quest APK BUILD, DEVICE, HIL и ручная приёмка — `NOT_RUN` для текущих артефактов.
Результаты прежних сборок не подтверждают текущие артефакты.

## Незакрытые проверки

| Область | Состояние и следующий шаг |
|---|---|
| Stage 3 | Выполнить Quest Diagnostic BUILD, запуск свежей пары и применимые network/session/reconnect/reboot cases; критерии — [Этапы реализации §5](implementation-stages.md#sec-10-5) |
| DEVICE, HIL, manual acceptance | `NOT_RUN` для новой identity; опубликовать exact reports с URI/SHA-256 |
| Quest credential persistence | `NOT_RUN`: проверить сохранение credential между двумя APK после lifecycle migration |
| Full-arm Body provider | Exact platform matrix не квалифицирована; выполнить [P0](test-plan.md#sec-9-6) для применимого scope. Историческая несовместимость описана в [источниках](references.md#sec-11-5-1) |
| EV3 release inputs | Release PASS не подтверждён: нужны exact brick image/toolchain SHA-256, SBOM и vulnerability review/disposition по [Разработка и развёртывание §5](engineering.md#sec-8-5) |
| Quest APK reproducibility | Повторить проверку exact builds: ранее при одинаковом `build_id` различались Unity GUID metadata (`boot.config`, `globalgamemanagers`, `unity_app_guid`, GUID-именованные entries) |

## Ближайший шаг

Подготовить свежую network-only Diagnostic пару: `actuator_scope_mask=safety_observation_mask=0x00`,
`required_user_inputs=NONE`; физическое движение запрещено, motor A может отсутствовать.
Последняя локальная проверка пары (2026-09-10) дала `LOCAL_PAIR_STATE_ABSENT`;
перед запуском проверить состояние заново и при отсутствии пары выполнить явный
`PROVISION PAIR` с доверенным EV3 fingerprint и CONTROL credential.

Порядок: TEST → BUILD → EV3 TRANSFER/INSTALL и Quest INSTALL → EV3 START → Quest START.
Разобрать timings, readiness, first failure и terminal state; DEVICE и применимые
Stage-3 HIL/manual cases выполнить отдельно. Команды и границы фаз —
[Разработка и развёртывание §5.1](engineering.md#sec-8-5-1).
