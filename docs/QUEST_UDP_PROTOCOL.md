# Quest↔EV3 protocol status

Этот документ больше не является отдельной спецификацией wire-формата. Старый
48-байтный CRC32-прототип удалён из актуальной архитектуры и не совместим с
PHANTOM protocol v1.

Нормативные источники:

- требования и семантика сессии: `docs/PHANTOM_SPECIFICATION.md`, §4 и §11.8;
- machine-readable wire source: `protocol/wire_schema.yaml`;
- generated C++ constants: `protocol/generated/protocol_constants.hpp`;
- generated C# constants: `PhantomQuest/Assets/Phantom/Networking/GeneratedProtocol.g.cs`;
- межъязыковые эталонные пакеты: `protocol/golden_vectors/v1.json`.

Актуальный datagram использует 64-байтный little-endian header, exact
type-specific payload length и 32-байтный HMAC-SHA-256. Максимальный размер —
1024 байта. Session ID создаётся EV3 после authenticated `HELLO`; sequence,
reserved fields, finite floating-point values, transaction ordering и HMAC
проверяются до изменения actuator state.

После изменения `protocol/wire_schema.yaml` необходимо выполнить:

```powershell
python tools/protocolgen.py
python tools/protocolgen.py --check
python tools/test_protocol.py
```

Ручное дублирование offsets и packet sizes в этом документе запрещено.
