# PHANTOM — правила исходного кода

Общие правила разработки для EV3, Quest и инструментов. Стек и закреплённые версии —
в [engineering.md](engineering.md#sec-engineering-stack); поведение компонентов и
безопасность определяются их спецификациями.

<!-- BEGIN GENERATED TOC -->
<details>
<summary>Оглавление</summary>

- [1. Общие правила](#sec-code-guidelines-common)
- [2. EV3: C++](#sec-code-guidelines-ev3)
- [3. Quest: C#, Unity и Android](#sec-code-guidelines-quest)
- [4. Python, PowerShell и shell](#sec-code-guidelines-tooling)

</details>
<!-- END GENERATED TOC -->

<a id="sec-code-guidelines-common"></a>
## 1. Общие правила

- Перед собственной реализацией проверять готовые решения: стандартную библиотеку,
  используемые SDK и сторонние библиотеки. Переиспользовать подходящее решение, если
  оно совместимо с целевой платформой и лицензией проекта и удовлетворяет требованиям
  функциональности, производительности и безопасности. Собственную реализацию писать,
  когда готовые варианты не подходят; кратко фиксировать причину выбора.
- Следовать стилю существующего компонента. Отделять алгоритмы и состояния от SDK/I/O,
  чтобы тесты выполняли настоящий код с подменёнными внешними зависимостями.
- Владение wire/config данными и правила генерации — в
  [правилах спецификации](specification-governance.md#sec-specification-governance-2).
  Канонизация JSON выполняется через `protocol/jcs.py`; формат и хэши — по
  [контрактам конфигурации](engineering-contracts.md#sec-engineering-contracts-configuration).
- Ресурсы имеют явного владельца и освобождаются при ошибках и завершении работы.
  Внешние операции и очереди ограничены; ошибки сохраняют исходную причину.
- Тесты приложения EV3 пишутся на C++, Quest — на C#/Java по языку проверяемого кода.
  Python-тесты проверяют Python-код; runner может запускать suites других языков.
  Порядок проверок и обязательный охват — в [плане тестирования](test-plan.md).
- Секреты и данные сопряжения обрабатываются по
  [правилам хранения ключей](engineering-contracts.md#sec-engineering-contracts-credentials).

<a id="sec-code-guidelines-ev3"></a>
## 2. EV3: C++

- Использовать C++14 без extensions и закреплённый ARMv5/soft-float ABI.
  Host-компиляция не доказывает совместимость с target. Возможности C++17/20
  (`std::span`, `std::byte`, ranges, coroutines) не подходят этому target.
- Использовать RAII для file/socket handles; shared ownership вводить при необходимости.
  В critical loop предпочтительны структуры фиксированной вместимости. Allocations,
  blocking I/O и управление через exceptions оцениваются относительно бюджета цикла
  из [EV3-спецификации](ev3-specification.md); startup/background имеют другие ограничения.
- Для binary I/O проверять длину, overflow/narrowing и alignment. Не накладывать native
  struct на wire buffer и не полагаться на host endianness; codecs проверяются общими vectors.
- `volatile` не синхронизирует потоки. На ARMv5 нельзя предполагать, что произвольный
  `std::atomic<T>` lock-free. Для memory/concurrency изменений выполнять применимые
  host sanitizers; выводы о latency/deadline подтверждать на целевой системе.
- Использовать Linux userspace API ev3dev; MCU register/ISR примеры не являются backend.
  Границы motor/network/safety I/O принадлежат EV3-спецификации.
- Поставляемые Python-помощники проверки EV3 сохраняют совместимость с Python 3.5;
  штатные службы написаны на C++14. Host fixtures и регрессии служб принадлежат
  C++/C# тестовым проектам. Состояние реализации — [current-status.md](current-status.md).

<a id="sec-code-guidelines-quest"></a>
## 3. Quest: C#, Unity и Android

- Сохранять границы `.asmdef` и compile symbols. Editor API принадлежит Editor assembly;
  чистые алгоритмы не зависят от MonoBehaviour/prefabs.
- Возможности C#/BCL определяются выбранной Unity/IL2CPP. Возможности новых .NET,
  языковых версий и сторонних библиотек требуют проверки поддержки target.
- SDK callbacks и workers передают ограниченные snapshots. UnityEngine objects и UI
  изменяются на main thread; `.Wait()`/`.Result` не блокируют его. После disable/destroy
  или смены сессии устаревшие async результаты отменяются либо игнорируются.
- В горячем frame/control path избегать повторной discovery, LINQ materialization,
  boxing и строкового logging. Изменения производительности подтверждаются профилированием.
- `JsonUtility` не заменяет универсальный serializer. Значимые null/empty, missing field,
  array/enum случаи проверяются в Unity.
- При переносе assets сохранять `.meta` GUID. Изменять сцены через существующий scene
  builder либо Editor API; serialized properties — через `SerializedObject` и
  `ApplyModifiedProperties` с сохранением prefab/scene. Проверять значение после reload.
- Android bridge владеет JNI wrappers, thread attachment и освобождением ресурсов.
  Проверять lifecycle, permission-denied и error paths. Источник —
  `PhantomQuest/Assets/Plugins/Android`; generated Gradle outputs не редактируются.
- Использовать API установленной SDK revision. Feature/permission изменения проверяются
  по итоговому manifest штатной сборки.

Часть рекомендаций Unity адаптирована из материалов Meta Platforms, Inc.;
[лицензия Apache-2.0](../.agents/skills/phantom-quest-development/LICENSE).

<a id="sec-code-guidelines-tooling"></a>
## 4. Python, PowerShell и shell

- Проверять runtime вызывающего runner. Host-инструменты разрешаются через
  `tools/toolchain.ps1`; личные пути и версии не вшиваются в скрипты.
- Python использует существующий `unittest` и stdlib там, где их достаточно.
  Не переносить новые зависимости или host-only syntax в Python 3.5 helpers на EV3.
  File/socket handles закрываются через context managers; subprocess/network имеют timeout.
- Encoding и переводы строк задаются явно для hash-bound артефактов.
- Для PowerShell проверять поддержку установленной версии, передавать аргументы массивом,
  отдельно проверять native exit code. `$PID`, `$HOME` и другие системные переменные
  не используются как локальные; пути обрабатываются через `-LiteralPath`.
- Device `/bin/sh` не предполагает Bash arrays, `[[ ]]` или `pipefail`. Quoting,
  return status и cleanup сохраняют первичную ошибку.
- Машинный stdout с JSON отделяется от диагностических сообщений. Перед удалением,
  переносом и установкой проверяется принадлежность путей назначенному каталогу;
  credentials/pair state не входят в disposable outputs. Установка следует
  [техническим контрактам](engineering-contracts.md).
