using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Net;
using System.Security.Cryptography;
using Phantom.Networking.Generated;

namespace Phantom.Networking
{
    public enum NetworkState { Idle,Discovering,Resolving,Handshaking,Connected,TelemetryFresh,TelemetryStale,Reconnecting,ConfigurationMismatch,AuthenticationFailure,ProtocolMismatch }
    public enum TelemetryFreshness { NoTelemetry,Fresh,Stale,Invalid }

    public interface IMonotonicClock { long NowMilliseconds{get;}ulong NowMicroseconds{get;} }
    public sealed class StopwatchMonotonicClock:IMonotonicClock
    {
        readonly Stopwatch _watch=Stopwatch.StartNew();
        public long NowMilliseconds=>_watch.ElapsedMilliseconds;
        public ulong NowMicroseconds=>(ulong)(_watch.Elapsed.TotalMilliseconds*1000.0);
    }

    public sealed class ManualMonotonicClock:IMonotonicClock
    {
        public long NowMilliseconds{get;private set;}public ulong NowMicroseconds=>(ulong)Math.Max(0,NowMilliseconds)*1000;
        public void Advance(long milliseconds){if(milliseconds<0)throw new ArgumentOutOfRangeException(nameof(milliseconds));NowMilliseconds+=milliseconds;}
    }

    public sealed class NetworkClientOptions
    {
        public string RobotId="phantom01",ServiceType="_phantom-ev3._udp",ControlKeyId="phantom01-control";
        public int ProtocolMajor=1,ProtocolMinor=0,ControlKeySlot=0,TelemetryMaxAgeMs=100,HelloRetryMs=250,HelloMaxAttempts=5,PingIntervalMs=500,PingTimeoutMs=750,MaxMissedPongs=3,ReconnectDelayMs=250;
        public byte ExpectedBuildProfile=1;
        public byte[] ExpectedBundleHash,ExpectedSpecificationHash;
        public void Validate()
        {
            if(string.IsNullOrWhiteSpace(RobotId)||RobotId.Length>32||!string.Equals(ServiceType,"_phantom-ev3._udp",StringComparison.Ordinal)||string.IsNullOrWhiteSpace(ControlKeyId))throw new ArgumentException("network identity");
            if(ProtocolMajor!=1||ProtocolMinor!=0||ControlKeySlot!=(int)WireV1.KeySlot.Control||TelemetryMaxAgeMs<1||HelloRetryMs<10||HelloMaxAttempts<1||HelloMaxAttempts>20||PingIntervalMs<10||PingTimeoutMs<10||MaxMissedPongs<1||ReconnectDelayMs<10)throw new ArgumentException("network bounds");
            if(ExpectedBundleHash==null||ExpectedBundleHash.Length!=32)throw new ArgumentException("expected bundle hash");
            if(ExpectedSpecificationHash!=null&&ExpectedSpecificationHash.Length!=32)throw new ArgumentException("expected specification hash");
            if(ExpectedBuildProfile>1)throw new ArgumentException("build profile");
        }
    }

    public sealed class NetworkEvent
    {
        public long MonotonicMilliseconds;public string Name,State,RobotId,SessionId,BootId,Endpoint,Detail,IncidentId;public double RttMilliseconds;public long TelemetryAgeMilliseconds;
    }
    public interface INetworkEventSink { void Record(NetworkEvent value); }

    public sealed class BoundedNetworkFlightRecorder:INetworkEventSink
    {
        readonly NetworkEvent[] _items;int _next,_count;
        public BoundedNetworkFlightRecorder(int capacity=256){if(capacity<1||capacity>4096)throw new ArgumentOutOfRangeException(nameof(capacity));_items=new NetworkEvent[capacity];}
        public int Count=>_count;
        public void Record(NetworkEvent value){if(value==null)return;_items[_next]=value;_next=(_next+1)%_items.Length;if(_count<_items.Length)_count++;}
        public NetworkEvent[] Snapshot(){var result=new NetworkEvent[_count];var start=(_next-_count+_items.Length)%_items.Length;for(var i=0;i<_count;i++)result[i]=_items[(start+i)%_items.Length];return result;}
    }

    public sealed class NetworkSnapshot
    {
        public NetworkState State;public TelemetryFreshness Freshness;public bool ServiceFound,SessionActive;
        public string RobotId,BuildId,Endpoint,ControllerBootId,SessionId,SpecificationHash,ProtocolHash,BundleHash,RobotGeometryHash,DriveCalibrationHash,ActiveJointSafeSetHash,PayloadProfilesHash,IncidentId;
        public RobotRuntimeState RemoteState;public ushort Fault,BatteryMv;public uint CommandAgeMs,StatusFlags,LoopHealthFlags;
        public double RttMilliseconds;public long TelemetryAgeMilliseconds;public ulong ReceivedSequence,SentSequence;
        public long AcceptedPackets,RejectedPackets,AuthenticationFailures,ReplayDrops,UnexpectedEndpointDrops;
        public long TransportSendDrops,TransportReceiveDrops;
    }

    public sealed class Stage3NetworkClient:IDisposable
    {
        readonly IServiceDiscoveryBackend _discovery;readonly IDatagramTransport _transport;readonly IControlCredentialStore _credentials;readonly NetworkClientOptions _options;readonly IMonotonicClock _clock;readonly INetworkEventSink _events;
        readonly Dictionary<string,DiscoveredRobot> _visible=new Dictionary<string,DiscoveredRobot>(StringComparer.Ordinal);
        byte[] _key,_nonce,_session,_safeSetHash;DiscoveredRobot _active;long _nextHello,_lastTelemetry=-1,_nextPing,_pingSentAt,_nextReconnect;int _helloAttempts,_missedPongs;ulong _txSequence,_rxSequence,_pingId,_pingToken;bool _running,_paused,_disposed,_pingOutstanding;
        public NetworkSnapshot Snapshot{get;}=new NetworkSnapshot{State=NetworkState.Idle,Freshness=TelemetryFreshness.NoTelemetry,RttMilliseconds=-1,TelemetryAgeMilliseconds=-1};
        public int VisibleServiceCount=>_visible.Count;

        public Stage3NetworkClient(IServiceDiscoveryBackend discovery,IDatagramTransport transport,IControlCredentialStore credentials,NetworkClientOptions options,IMonotonicClock clock=null,INetworkEventSink events=null)
        {
            _discovery=discovery??throw new ArgumentNullException(nameof(discovery));_transport=transport??throw new ArgumentNullException(nameof(transport));_credentials=credentials??throw new ArgumentNullException(nameof(credentials));_options=options??throw new ArgumentNullException(nameof(options));_options.Validate();_clock=clock??new StopwatchMonotonicClock();_events=events;Snapshot.RobotId=options.RobotId;
        }

        public void Start()
        {
            ThrowIfDisposed();if(_running&&!_paused)return;_paused=false;_running=true;
            ClearKey();if(!_credentials.TryLoad(_options.ControlKeyId,out _key)||_key==null||_key.Length<32){ClearKey();SetState(NetworkState.AuthenticationFailure);Emit("authentication_failed","credential_unavailable");}
            _discovery.Changed-=OnDiscoveryChanged;_discovery.Changed+=OnDiscoveryChanged;_discovery.Start(_options.ServiceType);Emit("discovery_started","");
            if(Snapshot.State!=NetworkState.AuthenticationFailure)SetState(NetworkState.Discovering);
        }

        public void Pause(){if(!_running||_paused)return;_paused=true;StopNetwork("pause",false);}
        public void Resume(){if(!_running||!_paused)return;Start();}
        public void Stop(){if(!_running)return;StopNetwork("stop",true);}

        public void Tick()
        {
            if(!_running||_paused||_disposed)return;
            _discovery.Poll();
            Snapshot.TransportSendDrops=_transport.SendDropCount;Snapshot.TransportReceiveDrops=_transport.ReceiveDropCount;
            ReceivedDatagram received;for(var i=0;i<64&&_transport.TryReceive(out received);i++)HandleDatagram(received);
            var now=_clock.NowMilliseconds;
            if(Snapshot.SessionActive)
            {
                UpdateFreshness(now);
                if(_pingOutstanding&&now-_pingSentAt>=_options.PingTimeoutMs)
                {
                    _pingOutstanding=false;_missedPongs++;Emit("ping_timeout","missed="+_missedPongs);
                    if(_missedPongs>=_options.MaxMissedPongs){InvalidateSession("ping_timeout");SetState(NetworkState.Reconnecting);_nextReconnect=now+_options.ReconnectDelayMs;}
                    else _nextPing=now+_options.PingIntervalMs;
                }
                if(Snapshot.SessionActive&&!_pingOutstanding&&now>=_nextPing)SendPing();
            }
            else if(Snapshot.State==NetworkState.Handshaking&&now>=_nextHello)
            {
                if(_helloAttempts>=_options.HelloMaxAttempts){InvalidateSession("handshake_timeout");SetState(NetworkState.Reconnecting);_nextReconnect=now+_options.ReconnectDelayMs;}
                else SendHello(true);
            }
            else if(Snapshot.State==NetworkState.Reconnecting&&now>=_nextReconnect&&_active!=null)ResolveAndHandshake(_active.ServiceKey);
        }

        public void Dispose()
        {
            if(_disposed)return;StopNetwork("dispose",true);_disposed=true;_transport.Dispose();_discovery.Dispose();_credentials.Dispose();
        }

        void OnDiscoveryChanged(DiscoveryChange change)
        {
            if(!_running||_paused||change==null)return;
            if(change.Kind==DiscoveryChangeKind.Error){Emit("service_ignored",change.ErrorCategory??"discovery_error");return;}
            var service=change.Service;
            var key=change.ServiceKey??service?.ServiceKey;
            if(change.Kind==DiscoveryChangeKind.Removed)
            {
                if(key!=null)_visible.Remove(key);Emit("service_lost",key??"");
                if(_active!=null&&string.Equals(_active.ServiceKey,key,StringComparison.Ordinal)){InvalidateSession("service_lost");_active=null;Snapshot.ServiceFound=false;Snapshot.Endpoint="";SetState(NetworkState.Discovering);}
                return;
            }
            if(service==null||string.IsNullOrEmpty(service.ServiceKey))return;
            _visible[service.ServiceKey]=service.Clone();Emit("service_found",service.RobotId??"");
            if(!string.Equals(service.ServiceType,_options.ServiceType,StringComparison.Ordinal)||!string.Equals(service.RobotId,_options.RobotId,StringComparison.Ordinal)||service.Endpoint==null||service.Endpoint.AddressFamily!=System.Net.Sockets.AddressFamily.InterNetwork){Emit("service_ignored","identity_or_ip_family");return;}
            if(service.ProtocolMajor!=_options.ProtocolMajor){InvalidateSession("protocol_mismatch");_active=service.Clone();Snapshot.ServiceFound=true;SetState(NetworkState.ProtocolMismatch);Emit("protocol_mismatch","discovery_protocol_major");return;}
            if(!service.HasValidBootId){Emit("service_ignored","invalid_boot_id");return;}
            if(_active!=null&&string.Equals(_active.ServiceKey,service.ServiceKey,StringComparison.Ordinal))
            {
                var endpointChanged=!EndpointsEqual(_active.Endpoint,service.Endpoint);var bootChanged=!Equal(_active.ControllerBootId,service.ControllerBootId);
                _active=service.Clone();
                if(endpointChanged||bootChanged){Emit(endpointChanged?"endpoint_changed":"boot_id_changed","");InvalidateSession(endpointChanged?"endpoint_changed":"boot_id_changed");ResolveAndHandshake(service.ServiceKey);}
                return;
            }
            if(_active==null){_active=service.Clone();Snapshot.ServiceFound=true;ResolveAndHandshake(service.ServiceKey);}
        }

        void ResolveAndHandshake(string serviceKey)
        {
            if(_key==null){SetState(NetworkState.AuthenticationFailure);return;}
            SetState(NetworkState.Resolving);DiscoveredRobot resolved;
            if(!_discovery.TryResolve(serviceKey,out resolved)||resolved==null||resolved.Endpoint==null||resolved.Endpoint.AddressFamily!=System.Net.Sockets.AddressFamily.InterNetwork||!resolved.HasValidBootId){SetState(NetworkState.Discovering);return;}
            if(!string.Equals(resolved.RobotId,_options.RobotId,StringComparison.Ordinal)||resolved.ProtocolMajor!=_options.ProtocolMajor){SetState(NetworkState.ProtocolMismatch);Emit("protocol_mismatch","resolved_identity");return;}
            _active=resolved.Clone();Snapshot.ServiceFound=true;Snapshot.Endpoint=EndpointText(resolved.Endpoint);Snapshot.ControllerBootId=ShortHex(resolved.ControllerBootId);Emit("service_resolved",Snapshot.Endpoint);
            _transport.Start(resolved.Endpoint);_nonce=new byte[16];using(var rng=RandomNumberGenerator.Create())rng.GetBytes(_nonce);_session=null;_txSequence=_rxSequence=0;_helloAttempts=0;_lastTelemetry=-1;Snapshot.Freshness=TelemetryFreshness.NoTelemetry;Snapshot.TelemetryAgeMilliseconds=-1;Snapshot.SessionActive=false;SetState(NetworkState.Handshaking);Emit("handshake_started","");SendHello(false);
        }

        void SendHello(bool retry)
        {
            if(_active==null||_nonce==null||_key==null)return;
            var payload=new byte[56];WriteId(payload,0,_options.RobotId);var o=32;ProtocolCodec.WriteU16(payload,ref o,(ushort)_options.ProtocolMinor);payload[o++]=(byte)_options.ControlKeySlot;payload[o++]=0;Buffer.BlockCopy(_nonce,0,payload,o,16);o+=16;ProtocolCodec.WriteU32(payload,ref o,0);
            var bytes=ProtocolCodec.Encode(WireV1.MessageType.Hello,payload,_key,new byte[16],_active.ControllerBootId,0,_clock.NowMicroseconds);
            _transport.TrySend(bytes);_helloAttempts++;_nextHello=_clock.NowMilliseconds+_options.HelloRetryMs;if(retry)Emit("handshake_retry","attempt="+_helloAttempts);
        }

        void HandleDatagram(ReceivedDatagram received)
        {
            if(_active==null||!EndpointsEqual(received.Remote,_active.Endpoint)){Snapshot.UnexpectedEndpointDrops++;return;}
            DecodedDatagram decoded;DecodeFailure failure;
            if(!ProtocolCodec.TryDecode(received.Bytes,_key,out decoded,out failure))
            {
                Snapshot.RejectedPackets++;if(failure==DecodeFailure.Authentication){Snapshot.AuthenticationFailures++;Emit("authentication_failed","packet_hmac");}return;
            }
            if(!Equal(decoded.Header.ControllerBootId,_active.ControllerBootId)){Snapshot.RejectedPackets++;return;}
            if(decoded.Header.MessageType==WireV1.MessageType.HelloAck&&Snapshot.State==NetworkState.Handshaking){HandleHelloAck(decoded);return;}
            if(!Snapshot.SessionActive||!Equal(decoded.Header.SessionId,_session)){Snapshot.RejectedPackets++;return;}
            if(decoded.Header.Sequence<=_rxSequence){Snapshot.ReplayDrops++;Snapshot.RejectedPackets++;return;}
            if(decoded.Header.MessageType==WireV1.MessageType.Telemetry){if(!HandleTelemetry(decoded))return;}
            else if(decoded.Header.MessageType==WireV1.MessageType.Pong){if(!HandlePong(decoded))return;}
            else {Snapshot.RejectedPackets++;return;}
            _rxSequence=decoded.Header.Sequence;Snapshot.ReceivedSequence=_rxSequence;Snapshot.AcceptedPackets++;
        }

        void HandleHelloAck(DecodedDatagram decoded)
        {
            HelloAckPacket ack;
            if(!ServerProtocol.TryDecodeHelloAck(decoded,out ack)){RejectHandshake(NetworkState.ProtocolMismatch,"malformed_ack");return;}
            if(!Equal(ack.ClientNonce,_nonce)||!string.Equals(ack.RobotId,_options.RobotId,StringComparison.Ordinal)){RejectHandshake(NetworkState.ProtocolMismatch,"ack_identity");return;}
            if(ack.ProtocolMinor!=_options.ProtocolMinor||ack.KeySlot!=_options.ControlKeySlot||ack.Role!=0||!Equal(ack.ProtocolHash,ProtocolHash())||_options.ExpectedSpecificationHash!=null&&!Equal(ack.SpecificationHash,_options.ExpectedSpecificationHash)||!string.IsNullOrEmpty(_active.BuildId)&&!string.Equals(ack.BuildId,_active.BuildId,StringComparison.Ordinal)){RejectHandshake(NetworkState.ProtocolMismatch,"ack_protocol_or_build_identity");return;}
            if(!Equal(ack.BundleHash,_options.ExpectedBundleHash)||ack.BuildProfile!=_options.ExpectedBuildProfile){RejectHandshake(NetworkState.ConfigurationMismatch,"ack_configuration");return;}
            if(ack.State!=RobotRuntimeState.ConnectedUnreferenced||ack.ReferenceFlags!=0||ack.GripperCapabilities!=0||!Zero(ack.Capabilities.Limits.Min)||!Zero(ack.Capabilities.Limits.Max)||!Zero(ack.Capabilities.MaxVelocity)||!Zero(ack.Capabilities.MaxAcceleration)){RejectHandshake(NetworkState.ConfigurationMismatch,"ack_not_network_only");return;}
            if(ack.ResultCode!=0||IsZero(decoded.Header.SessionId)){var detail="hello_rejected_"+ack.ResultCode;Emit("handshake_rejected",detail);InvalidateSession(detail);SetState(ack.ResultCode==12?NetworkState.Reconnecting:ack.ResultCode==2?NetworkState.AuthenticationFailure:NetworkState.ProtocolMismatch);if(Snapshot.State==NetworkState.Reconnecting)_nextReconnect=_clock.NowMilliseconds+_options.ReconnectDelayMs;return;}
            _session=(byte[])decoded.Header.SessionId.Clone();_safeSetHash=(byte[])ack.ActiveJointSafeSetHash.Clone();_txSequence=_rxSequence=0;Snapshot.SessionActive=true;Snapshot.SessionId=ShortHex(_session);Snapshot.BuildId=ack.BuildId;Snapshot.SpecificationHash=ShortHex(ack.SpecificationHash);Snapshot.ProtocolHash=ShortHex(ack.ProtocolHash);Snapshot.BundleHash=ShortHex(ack.BundleHash);Snapshot.RobotGeometryHash=ShortHex(ack.RobotGeometryHash);Snapshot.DriveCalibrationHash=ShortHex(ack.DriveCalibrationHash);Snapshot.ActiveJointSafeSetHash=ShortHex(ack.ActiveJointSafeSetHash);Snapshot.PayloadProfilesHash=ShortHex(ack.PayloadProfilesHash);Snapshot.RemoteState=ack.State;Snapshot.Freshness=TelemetryFreshness.NoTelemetry;_nextPing=_clock.NowMilliseconds;_missedPongs=0;_pingOutstanding=false;SetState(NetworkState.Connected);Emit("handshake_accepted","");Emit("session_created","");
        }

        void RejectHandshake(NetworkState state,string detail){Emit("handshake_rejected",detail);InvalidateSession(detail);SetState(state);Emit(state==NetworkState.ConfigurationMismatch?"configuration_mismatch":"protocol_mismatch",detail);}

        bool HandleTelemetry(DecodedDatagram decoded)
        {
            TelemetryPacket telemetry;
            if(!ServerProtocol.TryDecodeTelemetry(decoded,out telemetry)||!string.Equals(telemetry.RobotId,_options.RobotId,StringComparison.Ordinal)||!Equal(telemetry.BundleHash,_options.ExpectedBundleHash)||!Equal(telemetry.ActiveJointSafeSetHash,_safeSetHash)||telemetry.BuildProfile!=_options.ExpectedBuildProfile||(!string.IsNullOrEmpty(Snapshot.BuildId)&&!string.Equals(telemetry.BuildId,Snapshot.BuildId,StringComparison.Ordinal))||telemetry.State==RobotRuntimeState.Ready||telemetry.State==RobotRuntimeState.Hold||telemetry.State==RobotRuntimeState.Tracking||telemetry.State==RobotRuntimeState.RobotCalibration||telemetry.State==RobotRuntimeState.Commissioning||(telemetry.StatusFlags&0x383u)!=0||telemetry.ActivePayloadProfileId!="UNSELECTED"||telemetry.PayloadState!=2||!Zero(telemetry.Actual)||!Zero(telemetry.Speed)||telemetry.GripActual!=0)
            {Snapshot.RejectedPackets++;Snapshot.Freshness=TelemetryFreshness.Invalid;return false;}
            var recovered=Snapshot.Freshness==TelemetryFreshness.Stale||Snapshot.Freshness==TelemetryFreshness.Invalid;
            _lastTelemetry=_clock.NowMilliseconds;Snapshot.Freshness=TelemetryFreshness.Fresh;Snapshot.TelemetryAgeMilliseconds=0;Snapshot.RemoteState=telemetry.State;Snapshot.Fault=telemetry.Fault;Snapshot.BatteryMv=telemetry.BatteryMv;Snapshot.CommandAgeMs=telemetry.CommandAgeMs;Snapshot.StatusFlags=telemetry.StatusFlags;Snapshot.LoopHealthFlags=telemetry.LoopHealthFlags;Snapshot.BuildId=telemetry.BuildId;Snapshot.BundleHash=ShortHex(telemetry.BundleHash);Snapshot.ActiveJointSafeSetHash=ShortHex(telemetry.ActiveJointSafeSetHash);Snapshot.IncidentId=ShortHex(telemetry.IncidentId);SetState(NetworkState.TelemetryFresh);if(recovered)Emit("telemetry_recovered","");return true;
        }

        void SendPing()
        {
            if(!Snapshot.SessionActive||_session==null)return;
            if(_txSequence==ulong.MaxValue){InvalidateSession("sequence_exhausted");SetState(NetworkState.Reconnecting);_nextReconnect=_clock.NowMilliseconds+_options.ReconnectDelayMs;return;}
            _pingId++;_pingToken=_clock.NowMicroseconds;var payload=new byte[16];var o=0;ProtocolCodec.WriteU64(payload,ref o,_pingId);ProtocolCodec.WriteU64(payload,ref o,_pingToken);_txSequence++;var bytes=ProtocolCodec.Encode(WireV1.MessageType.Ping,payload,_key,_session,_active.ControllerBootId,_txSequence,_clock.NowMicroseconds);if(_transport.TrySend(bytes)){Snapshot.SentSequence=_txSequence;_pingOutstanding=true;_pingSentAt=_clock.NowMilliseconds;}
            _nextPing=_clock.NowMilliseconds+_options.PingIntervalMs;
        }

        bool HandlePong(DecodedDatagram decoded)
        {
            if(decoded.Payload==null||decoded.Payload.Length!=16||!_pingOutstanding){Snapshot.RejectedPackets++;return false;}
            var o=0;var id=ProtocolCodec.ReadU64(decoded.Payload,ref o);var token=ProtocolCodec.ReadU64(decoded.Payload,ref o);if(id!=_pingId||token!=_pingToken){Snapshot.RejectedPackets++;return false;}
            Snapshot.RttMilliseconds=Math.Max(0,_clock.NowMilliseconds-_pingSentAt);_pingOutstanding=false;_missedPongs=0;_nextPing=_clock.NowMilliseconds+_options.PingIntervalMs;return true;
        }

        void UpdateFreshness(long now)
        {
            if(_lastTelemetry<0){Snapshot.Freshness=TelemetryFreshness.NoTelemetry;Snapshot.TelemetryAgeMilliseconds=-1;return;}
            Snapshot.TelemetryAgeMilliseconds=Math.Max(0,now-_lastTelemetry);
            if(Snapshot.TelemetryAgeMilliseconds<=_options.TelemetryMaxAgeMs)return;
            if(Snapshot.Freshness!=TelemetryFreshness.Stale){Snapshot.Freshness=TelemetryFreshness.Stale;SetState(NetworkState.TelemetryStale);Emit("telemetry_stale","");}
        }

        void InvalidateSession(string reason)
        {
            var had=Snapshot.SessionActive||_session!=null;_transport.Stop();_session=null;_safeSetHash=null;_nonce=null;_txSequence=_rxSequence=0;_helloAttempts=0;_lastTelemetry=-1;_pingOutstanding=false;_missedPongs=0;Snapshot.SessionActive=false;Snapshot.SessionId="";Snapshot.SentSequence=Snapshot.ReceivedSequence=0;Snapshot.Freshness=TelemetryFreshness.NoTelemetry;Snapshot.TelemetryAgeMilliseconds=-1;if(had)Emit("session_invalidated",reason);
        }

        void StopNetwork(string reason,bool clearRunning)
        {
            _discovery.Changed-=OnDiscoveryChanged;_discovery.Stop();InvalidateSession(reason);_visible.Clear();_active=null;Snapshot.ServiceFound=false;Snapshot.Endpoint="";ClearKey();if(clearRunning)_running=false;SetState(NetworkState.Idle);
        }

        void SetState(NetworkState state){Snapshot.State=state;}
        void Emit(string name,string detail)
        {
            _events?.Record(new NetworkEvent{MonotonicMilliseconds=_clock.NowMilliseconds,Name=name,State=Snapshot.State.ToString(),RobotId=_options.RobotId,SessionId=Snapshot.SessionId??"",BootId=Snapshot.ControllerBootId??"",Endpoint=Snapshot.Endpoint??"",Detail=detail??"",IncidentId=Snapshot.IncidentId??"",RttMilliseconds=Snapshot.RttMilliseconds,TelemetryAgeMilliseconds=Snapshot.TelemetryAgeMilliseconds});
        }
        void ClearKey(){if(_key!=null){Array.Clear(_key,0,_key.Length);_key=null;}}
        void ThrowIfDisposed(){if(_disposed)throw new ObjectDisposedException(nameof(Stage3NetworkClient));}
        static bool EndpointsEqual(IPEndPoint a,IPEndPoint b)=>a!=null&&b!=null&&a.Port==b.Port&&Equals(a.Address,b.Address);
        static string EndpointText(IPEndPoint value)=>value==null?"":value.Address+":"+value.Port;
        static bool Equal(byte[] a,byte[] b){if(a==null||b==null||a.Length!=b.Length)return false;var d=0;for(var i=0;i<a.Length;i++)d|=a[i]^b[i];return d==0;}
        static bool IsZero(byte[] value){if(value==null)return true;var d=0;for(var i=0;i<value.Length;i++)d|=value[i];return d==0;}
        static bool Zero(Phantom.Kinematics.JointAngles value)=>value.Base==0&&value.Shoulder==0&&value.Elbow==0;
        static void WriteId(byte[] value,int offset,string text){var bytes=System.Text.Encoding.UTF8.GetBytes(text);if(bytes.Length>32)throw new ArgumentException("id32");Buffer.BlockCopy(bytes,0,value,offset,bytes.Length);}
        static byte[] ProtocolHash(){var value=WireV1.ProtocolSchemaSha256;var bytes=new byte[value.Length/2];for(var i=0;i<bytes.Length;i++)bytes[i]=Convert.ToByte(value.Substring(i*2,2),16);return bytes;}
        static string ShortHex(byte[] value){if(value==null)return "";var count=Math.Min(value.Length,8);var chars=new char[count*2];const string hex="0123456789abcdef";for(var i=0;i<count;i++){chars[i*2]=hex[value[i]>>4];chars[i*2+1]=hex[value[i]&15];}return new string(chars);}
    }
}
