# Разделение сборки, установки, запуска и device qualification

> **Тип:** execution plan; ненормативный
> **Область:** PC/CI, Quest 3, EV3, build/deploy/start/test tooling; §8.5–§8.8, §9.1
> **Начало:** 2026-09-07

## Цель

Сделать жизненный цикл артефакта явным и наблюдаемым: подключение устройств не должно
запускать сборку или длительные host-тесты, установка не должна запускать DEVICE AUTO, а
ошибка запуска не должна теряться за каскадом зависимостей либо скрытым rollback.

## Границы

- Нормативные владельцы процесса — `ENGINEERING.md` и `TEST_PLAN.md`.
- Эта задача сначала меняет документацию. Реализация scripts/systemd и повторная установка
  выполняются только после отдельного одобрения пользователя.
- Реальные DEVICE/HIL результаты не выводятся из review исходников; до следующего запуска на
  устройствах они остаются `NOT_RUN`.
- Safety authority, scope masks, `LOCAL_STOP` и zero-output требования не ослабляются.

## Этапы работы

- [x] M1 — проаудировать существующие build/install/start/device-auto scripts и локализовать
  причины длительного общего deploy-пути.
- [x] M2 — нормативно разделить `BUILD`, `PRE-INSTALL AUTO`, `TRANSFER`, `INSTALL`, `START`,
  `DEVICE AUTO`, `HIL AUTO` и recovery/rollback.
- [x] M3 — после одобрения документации разделить Quest и EV3 runners согласно новому контракту.
- [x] M4 — добавить machine-readable phase reports, deadlines, first-failure capture и tests
  границ ответственности.
- [ ] M5 — собрать новый exact candidate и выполнить отдельные INSTALL/START/DEVICE gates на
  подключённых устройствах.

## Журнал прогресса

- Unity используется только на PC для сборки Quest APK и Unity tests. EV3 package не содержит
  Unity и EV3 deployment не должен запускать Unity.
- EV3 использует системный Python runtime для shipped `phantom-network`, `phantom-mdns` и
  `phantom-device-auto`; installer не должен устанавливать/обновлять Python либо выполнять
  полный `compileall`.
- До M3 `pre-install-auto.ps1` повторно вызывал ARMEL build и EV3 packaging, хотя gate
  должен проверять заранее созданные immutable artifacts. Теперь он только проверяет уже
  существующие candidate artifacts и включает hashes deployment tools в admission report.
- До M3 EV3 installer не пересобирал артефакты, но последовательно выполнял admission,
  controller/safety self-tests, `compileall`, systemd activation, health checks и полный
  DEVICE AUTO. DEVICE AUTO повторяет часть self-tests и содержит restart/fault-injection cases.
- Startup может ждать readiness нескольких services, а rollback повторно запускает предыдущий
  target. Поэтому один вызов deploy выглядит как долгая установка и затрудняет выделение
  первого отказа.
- До M3 Quest DEVICE runner также объединял `adb install`, запуск и проверки приложения.
- Реализация разделена на `ev3-transfer/install/start/device-auto/recover` и
  `quest-install/start/device-auto`; отсутствующий prerequisite больше не запускает скрытую
  предыдущую фазу.
- Дублирующий `quest-pre-install-auto.ps1` удалён: Quest INSTALL и DEVICE используют единый
  authoritative `results/pre-install/report.json` полного post-build gate.
- В failed EV3 startup статический review дополнительно выявил попытку создать
  `/run/phantom/network-status.tmp` вне разрешённого service writable directory; исправление
  переносит atomic status file в `/run/phantom/network/status.json`. Это отдельный
  implementation defect будущего M3/M4, а не основание менять сохранённый hardware evidence
  вручную.

## Решения

- Финальные artifact bytes создаёт только `BUILD`; `PRE-INSTALL AUTO` их проверяет, но не
  пересобирает, не переподписывает и не переупаковывает.
- `TRANSFER` только копирует и сверяет bytes. `INSTALL` только валидирует и атомарно размещает
  артефакт при остановленном runtime. `START` отдельно активирует services/app и фиксирует
  первый отказ. `DEVICE AUTO` запускается отдельной явной командой над уже установленным build.
- Каждая фаза имеет собственный deadline, progress и machine-readable result. Отсутствующий
  prerequisite даёт быстрый FAIL, а не неявный запуск предыдущей фазы.
- После startup failure сначала сохраняются status/journal/terminal safe state и failed release;
  recovery/rollback является отдельной видимой фазой и не запускает DEVICE AUTO.

## Проверка

- `python tools/specgen.py --check` — `PASS`.
- `python tools/docindex.py --check` — `PASS`.
- `python tools/doclint.py` — `PASS`.
- `python tools/implementation_map_check.py` — `PASS`.
- `python tools/spec_contract_check.py` — `PASS`.
- `git diff --check` — `PASS`.
- `python tools/test_ev3_device_auto.py` — `PASS`, 25/25.
- `python ev3/network/test_phantom_network.py` — `PASS`, 13/13.
- PowerShell parser для изменённых/new runners — `PASS`.
- POSIX `sh -n` для EV3 deploy scripts — `PASS`.
- `python tools/security_scan.py` — `PASS`.
- Artifact build и physical transfer/install/start/device operations — `NOT_RUN`: устройства
  отключены; software changes проверены только off-hardware.

## Оставшаяся работа / blockers

- Собрать из clean commit новые artifacts заранее и получить PRE-INSTALL PASS; текущие старые
  artifacts несовместимы с изменившимися source/specification hashes.
- После подключения устройств выполнить по отдельности
  transfer, install, start и DEVICE AUTO.
