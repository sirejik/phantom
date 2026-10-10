# Stub Quest3 для тестов

Подмена входов Quest выполняется в C# через
[TrackingReplaySource](../PhantomQuest/Assets/Phantom/Replay/TrackingReplaySource.cs),
реализующий `IPhantomTrackingSource`. Он последовательно выдаёт подготовленные
`TrackingFrame` и поддерживает возврат к началу через `Rewind`.

Frames подаются в настоящий код приложения, чтобы проверять обработку входов,
mapping и другие реализованные алгоритмы. Отдельная Python-модель вычислений
для этого не нужна. Формат и требования к подменяемым данным —
[engineering.md](engineering.md#sec-8-4).

Загрузка записанных JSONL и полный автоматизированный путь от replay source
до алгоритмов пока не подтверждены; незакрытые проверки — в
[текущем статусе](current-status.md).
