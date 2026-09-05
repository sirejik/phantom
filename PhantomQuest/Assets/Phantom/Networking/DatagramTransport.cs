using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;

namespace Phantom.Networking
{
    public struct ReceivedDatagram { public byte[] Bytes;public IPEndPoint Remote; }

    public interface IDatagramTransport:IDisposable
    {
        bool IsRunning{get;}
        IPEndPoint Remote{get;}
        long SendDropCount{get;}
        long ReceiveDropCount{get;}
        void Start(IPEndPoint remote);
        void Stop();
        bool TrySend(byte[] bytes);
        bool TryReceive(out ReceivedDatagram datagram);
    }

    public sealed class UdpRobotTransport:IDatagramTransport
    {
        const int QueueLimit=64;
        readonly ConcurrentQueue<byte[]> _send=new ConcurrentQueue<byte[]>();
        readonly ConcurrentQueue<ReceivedDatagram> _receive=new ConcurrentQueue<ReceivedDatagram>();
        readonly object _gate=new object();
        CancellationTokenSource _cancel;Socket _socket;Task _worker;int _sendDepth,_receiveDepth,_generation;
        long _sendDrops,_receiveDrops;
        static int _activeWorkers;
        public static int ActiveWorkerCount=>Volatile.Read(ref _activeWorkers);
        public bool IsRunning{get;private set;}
        public IPEndPoint Remote{get;private set;}
        public long SendDropCount=>Interlocked.Read(ref _sendDrops);
        public long ReceiveDropCount=>Interlocked.Read(ref _receiveDrops);

        public void Start(IPEndPoint remote)
        {
            if(remote==null)throw new ArgumentNullException(nameof(remote));
            lock(_gate)
            {
                StopLocked();ClearQueues();
                Remote=new IPEndPoint(remote.Address,remote.Port);
                _socket=new Socket(Remote.AddressFamily,SocketType.Dgram,ProtocolType.Udp);
                _socket.Bind(Remote.AddressFamily==AddressFamily.InterNetworkV6
                    ?(EndPoint)new IPEndPoint(IPAddress.IPv6Any,0):new IPEndPoint(IPAddress.Any,0));
                _socket.ReceiveBufferSize=16*1024;_socket.SendBufferSize=16*1024;
                _cancel=new CancellationTokenSource();IsRunning=true;
                var socket=_socket;var endpoint=Remote;var token=_cancel.Token;var generation=Volatile.Read(ref _generation);
                Interlocked.Increment(ref _activeWorkers);_worker=Task.Run(()=>Worker(socket,endpoint,token,generation),token);
                _worker.ContinueWith(_=>Interlocked.Decrement(ref _activeWorkers),CancellationToken.None,TaskContinuationOptions.ExecuteSynchronously,TaskScheduler.Default);
            }
        }

        public bool TrySend(byte[] bytes)
        {
            if(!IsRunning||bytes==null||bytes.Length<1||bytes.Length>1024)return false;
            if(Interlocked.Increment(ref _sendDepth)>QueueLimit)
            {Interlocked.Decrement(ref _sendDepth);Interlocked.Increment(ref _sendDrops);return false;}
            var copy=(byte[])bytes.Clone();_send.Enqueue(copy);return true;
        }

        public bool TryReceive(out ReceivedDatagram datagram)
        {
            if(_receive.TryDequeue(out datagram)){Interlocked.Decrement(ref _receiveDepth);return true;}
            datagram=default;return false;
        }

        public void Stop(){lock(_gate)StopLocked();}
        public void Dispose(){Stop();ClearQueues();}

        void StopLocked()
        {
            IsRunning=false;
            Interlocked.Increment(ref _generation);
            try{_cancel?.Cancel();}catch(ObjectDisposedException){}
            try{_socket?.Close();}catch(ObjectDisposedException){}
            _cancel?.Dispose();_cancel=null;_socket=null;_worker=null;Remote=null;
        }

        void Worker(Socket socket,IPEndPoint expected,CancellationToken token,int generation)
        {
            var buffer=new byte[1025];EndPoint sender=expected.AddressFamily==AddressFamily.InterNetworkV6
                ?(EndPoint)new IPEndPoint(IPAddress.IPv6Any,0):new IPEndPoint(IPAddress.Any,0);
            while(!token.IsCancellationRequested&&generation==Volatile.Read(ref _generation))
            {
                byte[] outgoing;
                for(var i=0;i<16&&!token.IsCancellationRequested&&generation==Volatile.Read(ref _generation)&&_send.TryDequeue(out outgoing);i++)
                {
                    Interlocked.Decrement(ref _sendDepth);
                    try{socket.SendTo(outgoing,expected);}catch(SocketException){if(token.IsCancellationRequested)return;}
                    catch(ObjectDisposedException){return;}
                }
                try
                {
                    if(!socket.Poll(10*1000,SelectMode.SelectRead))continue;
                    var count=socket.ReceiveFrom(buffer,0,buffer.Length,SocketFlags.None,ref sender);
                    var from=sender as IPEndPoint;
                    if(count>1024||from==null||generation!=Volatile.Read(ref _generation))continue;
                    var bytes=new byte[count];Buffer.BlockCopy(buffer,0,bytes,0,count);
                    if(Interlocked.Increment(ref _receiveDepth)>QueueLimit)
                    {Interlocked.Decrement(ref _receiveDepth);Interlocked.Increment(ref _receiveDrops);continue;}
                    _receive.Enqueue(new ReceivedDatagram{Bytes=bytes,Remote=new IPEndPoint(from.Address,from.Port)});
                }
                catch(SocketException){if(token.IsCancellationRequested)return;}
                catch(ObjectDisposedException){return;}
            }
        }

        void ClearQueues()
        {
            byte[] sent;while(_send.TryDequeue(out sent)){}Interlocked.Exchange(ref _sendDepth,0);
            ReceivedDatagram received;while(_receive.TryDequeue(out received)){}Interlocked.Exchange(ref _receiveDepth,0);
        }
    }

    public sealed class FakeDatagramTransport:IDatagramTransport
    {
        readonly Queue<byte[]> _sent=new Queue<byte[]>();readonly Queue<ReceivedDatagram> _received=new Queue<ReceivedDatagram>();
        public bool IsRunning{get;private set;}public IPEndPoint Remote{get;private set;}public long SendDropCount{get;private set;}public long ReceiveDropCount{get;private set;}public int StartCount{get;private set;}public int StopCount{get;private set;}
        public void Start(IPEndPoint remote){if(remote==null)throw new ArgumentNullException(nameof(remote));Stop();Remote=new IPEndPoint(remote.Address,remote.Port);IsRunning=true;StartCount++;}
        public void Stop(){if(IsRunning)StopCount++;IsRunning=false;Remote=null;_sent.Clear();_received.Clear();}
        public bool TrySend(byte[] bytes){if(!IsRunning||bytes==null||bytes.Length>1024){SendDropCount++;return false;}if(_sent.Count>=64){SendDropCount++;return false;}_sent.Enqueue((byte[])bytes.Clone());return true;}
        public bool TryReceive(out ReceivedDatagram datagram){if(_received.Count>0){datagram=_received.Dequeue();return true;}datagram=default;return false;}
        public bool TryTakeSent(out byte[] bytes){if(_sent.Count>0){bytes=_sent.Dequeue();return true;}bytes=null;return false;}
        public void Inject(byte[] bytes,IPEndPoint from=null){if(!IsRunning||bytes==null||_received.Count>=64){ReceiveDropCount++;return;}_received.Enqueue(new ReceivedDatagram{Bytes=(byte[])bytes.Clone(),Remote=from??Remote});}
        public void Dispose(){Stop();}
    }
}
