---
name: phantom-tooling
description: "Писать и исправлять Python, PowerShell и POSIX shell tooling PHANTOM: generators, тестовые runners, сборка, packaging и lifecycle scripts. Различает host и EV3 runtimes; не запускает device-фазы только ради проверки скрипта."
license: MIT
---

# Python, PowerShell и shell tooling

Определи, где выполняется изменяемый файл: host/CI, EV3 или shared code. Device/shared Python
совместим с Python 3.5 из EV3 baseline; host code следует реально объявленному CI/toolchain
и соседним модулям. Не вводи Python 3.11+, новый formatter/test framework или пакетный
менеджер только потому, что так устроен внешний пример.

## Python

Используй существующий test runner (`unittest` в `tools/test_*.py`) и stdlib там, где этого
достаточно. На границах проверяй тип, длину и диапазон, сохраняй исходную причину ошибки.
Ограничивай subprocess/network timeout; закрывай handles через context managers.
Encoding и LF задавай явно для hash-bound artifacts. Canonical JSON создаётся существующим
`protocol/jcs.py`; generated manifest редактируется через source/generator.
В device Python нет f-strings, dataclasses, `list[str]` и нового pathlib API.

## PowerShell и POSIX shell

- Host tools разрешаются через `tools/toolchain.ps1`; не вшивай личные пути и версии.
- Перед изменением проверь shell/version вызывающего runner. Для Windows PowerShell не
  предполагай доступность PowerShell 7 syntax/API. Аргументы передавай массивом; проверяй
  native exit code отдельно от диагностического stderr.
- Не используй `$PID`, `$HOME` и другие системные переменные для локального состояния.
  Пути обрабатывай через `-LiteralPath`; stdout с JSON отделяй от human diagnostics.
- Device `/bin/sh` не предполагает Bash arrays/`[[ ]]`/`pipefail`. Сохраняй quoting,
  проверку return status и bounded cleanup; `trap` не должен скрывать первичный failure.
- Для INSTALL/TRANSFER/RECOVERY сохрани границы из
  [Разработка и развёртывание](../../../docs/engineering.md#sec-8-5-1), path containment,
  staged/atomic writes и separation private pair state от disposable outputs.

## Проверка

Выбери профильный `tools/test_*.py` по изменённому runner/generator; используй временные
fixtures для subprocess, файловой системы и malformed inputs. PowerShell проверяй Parser API,
POSIX — `sh -n` в совместимой среде; это syntax checks, а не execution evidence.
Lifecycle behavior проверяется `tools/test_lifecycle.py` и соответствующими runner tests
без устройств. Не запускай SSH/ADB/PROVISION как побочный эффект syntax/unit проверки.

[Upstream и отклонённые defaults](SOURCE.md) нужны при обновлении этого skill.
