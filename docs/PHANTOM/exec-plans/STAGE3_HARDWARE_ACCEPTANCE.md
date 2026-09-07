# Stage 3 network-only: физическая приёмка Quest 3 и EV3

> **Тип:** execution plan; ненормативный
> **Область:** Stage 3, Quest 3, EV3, DEVICE/HIL/integration, `actuator_scope_mask=0x00`
> **Начало:** 2026-09-06, source candidate `4c842f9a4916389fd5b2898320f840a30763b7ec`

## Цель

Получить воспроизводимый machine-readable результат физической приёмки Stage 3 для одного
точно идентифицированного clean candidate, не создавая motor authority и сохраняя нулевое
наблюдаемое motor state во всех выполненных сценариях.

## Границы

- Только network-only профиль: `qualification_only=true`, `actuator_scope_mask=0x00`,
  `safety_observation_mask=0x00`, `required_user_inputs=NONE`.
- Simulator/build evidence не заменяет physical DEVICE/HIL evidence.
- Guardian/LOCAL_STOP/POWER_CUT не обходятся ради получения PASS.
- Пароли, private keys, IP-адреса и serial устройств не входят в versioned evidence.

## Этапы работы

- [x] M1 — проверить нормативный scope, software/build gates и обнаружить оба физических устройства.
- [x] M2 — установить exact Quest APK и попытаться установить exact EV3 package с безопасным rollback.
- [x] M3 — локализовать обнаруженный EV3 runner defect, добавить regression и host clock correlation.
- [ ] M4 — собрать clean candidate с исправлением, повторить EV3 DEVICE AUTO и restart/reboot сценарии.
- [ ] M5 — получить Quest DEVICE AUTO при валидном Horizon tracking environment и выполнить real integration.
- [ ] M6 — выпустить итоговый Stage-3 verdict и связать его с exact artifact identities/evidence.

## Журнал прогресса

- PRE-INSTALL для исходного candidate прошёл, а установленные Quest APK bytes подтверждены обратным pull/hash.
- EV3 installer дошёл до on-device runner; runner упал на отсутствующем `built_at` в deterministic manifest,
  после чего installer выполнил rollback. Наблюдаемые duty/speed всех обнаруженных motor nodes оставались нулевыми.
- Причина — рассинхронизация runner с manifest schema: embedded manifest нормативно не содержит wall-clock build time.
- Регрессия устранена без добавления timestamp в build identity; несинхронизированный NTP теперь требует
  отдельной host timestamp correlation. Такая корреляция выполнена с bounded round-trip и дала PASS.
- Clean Windows worktree выявил отсутствие LF checkout policy для POSIX EV3 scripts; добавлены узкие
  `.gitattributes` правила, чтобы ARMEL/deploy runners не получали CRLF.
- Первый exact-candidate retest прошёл manifest load, но выявил неперехваченный bounded timeout
  `timedatectl status` на systemd 232. NTP query теперь остаётся evidence, а его timeout явно требует
  уже предусмотренную host correlation и не скрывает проверку plausibility календаря.
- Следующий retest выявил CRLF shebang у Python systemd entrypoints из `ev3/network` (exit 127).
  LF checkout policy расширена на Python-файлы; downstream service/IPC/network FAIL не считаются
  самостоятельным результатом до повторного startup без этой причины.
- Quest cold start был прерван системным Guardian из-за `TRACKING_LOST` до запуска scene runner;
  обход Guardian не выполнялся.

- Повторный DEVICE AUTO candidate `0d4e3aa6...` дошёл до реальных systemd services. Первый
  отказ — `phantom-controller` exit 3: `ProtectSystem=strict` не разрешал открыть
  `/run/phantom/motor-control.lock`, потому что lock отсутствовал в `ReadWritePaths` controller unit.
  `phantom-network` timeout и `phantom-mdns` dependency failure были каскадом этого отказа.
- Rollback вернул `/opt/phantom/current` на release `70c5f541...`, но оставил candidate units и
  tmpfiles в `/etc`; текущая установка поэтому смешанная и оставлена с остановленными PHANTOM
  services до следующей контролируемой установки.
- На Stage 3 обнаруженные `outB/outC/outD` являются `OUT_OF_SCOPE`; отсутствие `outA` нормативно
  допустимо при `actuator_scope_mask=0x00` и не связано со startup failure.
- Off-hardware remediation добавляет controller lock в systemd sandbox, transactional restoration
  units/tmpfiles при rollback, отдельную проверку каждого обязательного service и dependency-aware
  `NOT_RUN` в DEVICE AUTO. Пустой `network-status.json` больше не разрушает report identity.
- Quest-конфигурация содержала canonical `commissioning_key_id:null`, который Unity
  `JsonUtility` материализует как пустую строку. Runtime теперь принимает null/empty только как
  отсутствие commissioning slot и продолжает отклонять любое непустое значение.

## Решения

- Wall-clock не возвращается в deterministic EV3 manifest. DEVICE AUTO фиксирует календарь, NTP и
  `chronology_trust`; при отсутствии NTP хронологическую пригодность даёт отдельный host-correlation report.
- Для повторяемой автоматизации используется отдельный локальный root deployment SSH key. Пароль пользователя
  `robot` остаётся установленным; unrestricted passwordless sudo удалён.

## Проверка

- `python tools/test_ev3_device_auto.py` — `PASS`, 16/16: sandbox path, per-service admission,
  rollback metadata/ownership contract, dependency-aware `NOT_RUN`, boot-id validation и
  empty/malformed status handling.
- `powershell -File scripts/quest-test.ps1` — `PASS`, Unity EditMode 32/32, включая реальную
  `JsonUtility`-десериализацию `commissioning_key_id:null` в пустую строку.
- `tools/quest_validation/compile_and_smoke.ps1` — `PASS`: pure core 81 checks и 21/21 golden
  decode/round-trip vectors.
- EV3 host Release/Diagnostic — `PASS`, по 4/4 CTest; shell/Python syntax checks — `PASS`.
- `python tools/security_scan.py` — `PASS`; старый failed DEVICE AUTO сохраняется без ручного
  редактирования и распознаётся только как legacy public-hash evidence.
- `powershell -File scripts/ev3-clock-correlation.ps1` — `PASS` на физическом EV3.
- EV3 exact-candidate DEVICE AUTO после исправления — `NOT_RUN` до clean build/installation.
- Quest DEVICE AUTO — `NOT_RUN`: app report не создан из-за системного `TRACKING_LOST`/Guardian preemption.
- Quest↔EV3 integration, restart/reboot/IP-change — `NOT_RUN` до прохождения prerequisite DEVICE gates.

## Оставшаяся работа / blockers

- Выполнить clean build/PRE-INSTALL/install нового exact candidate и полный EV3 DEVICE AUTO.
- Обеспечить Quest устойчивой визуальной tracking-сценой/валидной Guardian boundary без обхода safety UI,
  затем повторить нулевзаимодействующий DEVICE AUTO.
- После двух DEVICE PASS выполнить только network/session/reconnect/reboot tests и проверить, что
  наблюдаемое motor state остаётся нулевым, а `phantom-net` не имеет motor-write authority.
