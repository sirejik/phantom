using System;
using System.Net;

namespace Phantom.Networking
{
    public sealed class SessionState
    {
        public byte[] SessionId { get; }
        public byte[] ControllerBootId { get; }
        public IPEndPoint Endpoint { get; }
        public ulong NextSequence { get; private set; }=1;
        public ulong LastReceivedSequence { get; private set; }
        public SessionState(byte[] serverSessionId,byte[] controllerBootId,IPEndPoint endpoint)
        {
            if(serverSessionId==null||serverSessionId.Length!=16||IsZero(serverSessionId))throw new ArgumentException("server session id");
            if(controllerBootId==null||controllerBootId.Length!=16||IsZero(controllerBootId))throw new ArgumentException("controller boot id");
            Endpoint=endpoint??throw new ArgumentNullException(nameof(endpoint));SessionId=(byte[])serverSessionId.Clone();ControllerBootId=(byte[])controllerBootId.Clone();
        }
        public ulong AllocateSequence(){if(NextSequence==ulong.MaxValue)throw new InvalidOperationException("sequence exhausted");return NextSequence++;}
        public bool TryAccept(ulong sequence){if(sequence==0||sequence<=LastReceivedSequence)return false;LastReceivedSequence=sequence;return true;}
        static bool IsZero(byte[] value){var any=0;for(var i=0;i<value.Length;i++)any|=value[i];return any==0;}
    }
}
