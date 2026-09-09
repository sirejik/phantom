# Локальное evidence и независимая идентичность сборки

> **Status:** SUPERSEDED
> **Superseded by:** `LIFECYCLE_RESTRUCTURE.md`
> **Normative owners:** `ENGINEERING.md`, `TEST_PLAN.md`
> **Hardware/evidence state:** только исторические отчёты; не переносить PASS на текущий candidate

> **Исторический план:** прежние названия фаз ниже сохранены только как provenance уже
> выполненной миграции; текущий lifecycle определён §8.5/§9.1.

> **Тип:** execution plan; ненормативный
> **Область:** repository policy, build identity, BUILD/TRANSFER/INSTALL/START tooling, evidence lifecycle, документация
> **Начало:** 2026-09-08

## Цель

Убрать циклическую зависимость `results/** → Git state/commit → build_id → повторная сборка`.
Сборка и установка явно выбранного артефакта должны выполняться без чтения предыдущих
локальных отчётов. Safety/qualification evidence остаётся привязанным к точным artifact
hashes, но хранится как локальный или внешний артефакт, а не как постоянно растущие данные
основной истории Git.

Одновременно удалить из репозитория адаптеры, agent-specific зеркала и устаревшую
документацию, а также очистить уже накопленные локальные результаты.

## Границы

- Не ослаблять EV3 motor authority, `LOCAL_STOP`, zero-output и qualification gates.
- INSTALL только размещает проверяемые bytes и оставляет runtime остановленным; физический
  допуск по-прежнему создаётся отдельным qualification workflow.
- `git_commit` может оставаться provenance-полем manifest/report, но не является входом
  content-addressed `build_id` и не является prerequisite BUILD/INSTALL.
- Удаление ограничено `results/**`, явно agent-specific файлами и подтверждёнными
  obsolete mirrors; secrets, ключи, пользовательские build artifacts и внешние каталоги не
  затрагиваются.
- Real-device/HIL проверки в этой задаче не выполняются; их статус остаётся `NOT_RUN`.

## Этапы работы

- [x] M1 — инвентаризировать policy/code/docs зависимости и точно определить удаляемые файлы.
- [x] M2 — сделать `build_id` content-addressed по реальным входам без commit/dirty coupling.
- [x] M3 — убрать зависимость TRANSFER/INSTALL/START от ранее сохранённых result-файлов;
  сохранить byte/hash validation и безопасные terminal states.
- [x] M4 — перевести `results/**` в локальное игнорируемое хранилище и удалить старые результаты.
- [x] M5 — удалить agent-specific adapters/mirrors и все их упоминания.
- [x] M6 — синхронизировать нормативные спеки, generated документацию и regression tests.

## Журнал прогресса

- Обнаружено 19 tracked файлов в `results/**`, но локально каталог содержит 818 файлов и
  около 249 MB.
- Текущий `PHANTOM-BUILD-V1` включает `git_commit`; build/package/PRE-INSTALL используют
  repository-wide `git status`, а Quest/EV3 INSTALL читают предыдущий PRE-INSTALL report.
- Обнаружены корневой agent-specific adapter, пять зеркал canonical skills, утилита их
  синхронизации и ссылки на них в правилах и документации.
- Удалены 818 старых файлов `results/**` общим размером 249377167 bytes; tracked evidence и
  summaries удалены из дерева, каталог целиком добавлен в `.gitignore`.
- Удалены agent-specific adapter/mirror, obsolete audit snapshot и его remediation status;
  repository-wide case-insensitive поиск запрещённых названий не находит совпадений.
- BUILD-V2, TRANSFER/INSTALL/START и DEVICE qualification boundaries реализованы и отражены
  в `ENGINEERING.md`, `TEST_PLAN.md`, safety/product requirements и governance.

## Решения

- Долговечная связь qualification с candidate обеспечивается artifact/build hashes и
  публикуемым release/qualification manifest, а не обязательным коммитом каждого локального
  runner output.
- Локальный каталог `results/` полностью игнорируется Git и может безопасно пересоздаваться
  runners.

## Проверка

- `python tools/test_build_identity.py` — PASS, 2/2.
- `python tools/test_artifact_check.py` — PASS, 3/3.
- `python tools/test_ev3_device_auto.py` — PASS, 26/26, включая regression независимости
  BUILD/INSTALL/START от repository result state.
- PowerShell parser изменённых scripts — PASS; POSIX `sh -n` deploy scripts — PASS.
- `specgen --check`, `docindex --check`, `configgen --check`, `doclint`,
  `implementation_map_check`, `spec_contract_check` — PASS.
- `test_configgen.py` — PASS, 20/20; `security_scan.py` и `test_security_scan.py` — PASS.
- Quest Unity-free compile/smoke — PASS: pure core 81 checks и 21 golden vectors.
- Real-device/HIL: `NOT_RUN`.

## Оставшаяся работа / blockers

- Собрать новые Quest/EV3 artifacts с V2 manifests и выполнить полный PRE-INSTALL exact bytes.
- Установку и hardware gates запускать отдельной следующей задачей; в этой правке они `NOT_RUN`.
