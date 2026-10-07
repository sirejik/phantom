# C++14 и Python на EV3

## C++

`ev3/CMakeLists.txt` задаёт C++14 без extensions. ARMv5/soft-float ABI и compiler берутся из
pinned toolchain; host compiler не доказывает их совместимость. C++17/20 concepts, ranges,
`std::span`, `std::byte` и coroutine-примеры нельзя переносить в этот target.

Используй RAII для file/socket handles и явное ownership; shared ownership вводится только
при реальной необходимости. Bounded fixed-capacity storage предпочтительно для critical loop.
Не добавляй allocations, exception-based control flow и blocking work в tick без проверки
его нормативного бюджета. Startup/setup и background work имеют отдельные ограничения.

Для binary I/O проверяй length до чтения, overflow/narrowing и alignment. Не кастуй wire
buffer к native struct и не полагайся на host endianness; codec сверяется с shared vectors.
`volatile` не синхронизирует Linux threads. Используй уже принятые synchronization primitives;
на ARMv5 нельзя предполагать lock-free реализацию любой `std::atomic<T>`.

При изменении memory/concurrency path запускай применимые host sanitizers, а performance
выводы связывай с измерением на целевой системе. Host microbenchmark не доказывает EV3 deadline.

## Python/device services

Системный Python 3.5 и systemd baseline заданы в EV3 spec. Проверяй синтаксис и используемые
stdlib APIs, включая shared `protocol/` модули. Современный host `py_compile` сам по себе
не подтверждает Python 3.5 compatibility; нужен target-compatible TEST/BUILD check.

Network service работает через IPC, не читает motor/power sysfs для обхода controller snapshot.
При bounded socket/IPC failure сохраняй различие malformed, timeout и session invalidation.
Readiness наступает после открытия реального endpoint, а не сразу после старта процесса.

Драйверный источник: [ev3dev tacho-motor](https://www.ev3dev.org/docs/tutorials/tacho-motors/).
Его учебные motor-write примеры не являются production control path PHANTOM.
