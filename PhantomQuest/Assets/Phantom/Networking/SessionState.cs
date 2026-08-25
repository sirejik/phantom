using System;

namespace Phantom.Networking
{
    public static class SequenceMath
    {
        public static bool IsNewer(uint candidate, uint reference) => candidate != reference && unchecked((int)(candidate - reference)) > 0;
    }

    public sealed class SessionState
    {
        public ulong SessionId { get; }
        public uint NextSequence { get; private set; }
        public SessionState()
        {
            var bytes = Guid.NewGuid().ToByteArray();
            SessionId = BitConverter.ToUInt64(bytes, 0);
            if (SessionId == 0) SessionId = 1;
        }
        public uint AllocateSequence() => NextSequence++;
    }
}
