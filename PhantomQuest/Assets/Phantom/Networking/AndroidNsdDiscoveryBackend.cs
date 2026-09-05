using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.Net;
using System.Threading;

#if UNITY_ANDROID && !UNITY_EDITOR
using UnityEngine;
#endif

namespace Phantom.Networking
{
    public sealed class AndroidNsdDiscoveryBackend:IServiceDiscoveryBackend
    {
        readonly Dictionary<string,DiscoveredRobot> _resolved=new Dictionary<string,DiscoveredRobot>(StringComparer.Ordinal);
        readonly ConcurrentQueue<DiscoveryChange> _callbacks=new ConcurrentQueue<DiscoveryChange>();
        readonly object _callbackGate=new object();
        string _requestedServiceType;
        int _callbackDepth;
        public event Action<DiscoveryChange> Changed;
        public bool IsRunning{get;private set;}
#if UNITY_ANDROID && !UNITY_EDITOR
        AndroidJavaObject _bridge;ListenerProxy _listener;
#endif

        public void Start(string serviceType)
        {
            if(IsRunning)return;if(string.IsNullOrWhiteSpace(serviceType))throw new ArgumentException("service type");_requestedServiceType=serviceType;IsRunning=true;
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                using(var unityPlayer=new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                using(var activity=unityPlayer.GetStatic<AndroidJavaObject>("currentActivity"))
                {
                    _listener=new ListenerProxy(this);_bridge=new AndroidJavaObject("dev.phantom.nsd.PhantomNsdBridge",activity,_listener);_bridge.Call("start",AndroidServiceType(serviceType));
                }
            }
            catch(Exception){Stop();Changed?.Invoke(new DiscoveryChange{Kind=DiscoveryChangeKind.Error,ErrorCategory="android_nsd_start_failed"});}
#else
            PublishError("android_nsd_not_available_on_host");
#endif
        }

        public void Stop()
        {
            if(!IsRunning)return;IsRunning=false;
#if UNITY_ANDROID && !UNITY_EDITOR
            try{_bridge?.Call("stop");}catch(Exception){}
            _bridge?.Dispose();_bridge=null;_listener=null;
#endif
            _resolved.Clear();_requestedServiceType=null;
            lock(_callbackGate){DiscoveryChange ignored;while(_callbacks.TryDequeue(out ignored)){}Interlocked.Exchange(ref _callbackDepth,0);}
        }

        public void Poll()
        {
            DiscoveryChange change;
            for(var i=0;i<64&&_callbacks.TryDequeue(out change);i++)
            {
                Interlocked.Decrement(ref _callbackDepth);
                if(!IsRunning)continue;
                if(change.Kind==DiscoveryChangeKind.Added||change.Kind==DiscoveryChangeKind.Updated)_resolved[change.ServiceKey]=change.Service.Clone();
                else if(change.Kind==DiscoveryChangeKind.Removed)_resolved.Remove(change.ServiceKey);
                Changed?.Invoke(change);
            }
        }

        public bool TryResolve(string serviceKey,out DiscoveredRobot service)
        {DiscoveredRobot value;if(IsRunning&&_resolved.TryGetValue(serviceKey,out value)){service=value.Clone();return true;}service=null;return false;}
        public void Dispose(){Stop();Changed=null;}

        void OnResolved(string instance,string serviceType,string host,int port,string robotId,string protocolMajor,string bootHex,string buildId)
        {
            if(!IsRunning)return;
            IPAddress address;int major;byte[] boot;
            if(!IPAddress.TryParse(host,out address)||port<1||port>65535||!int.TryParse(protocolMajor,out major)||!TryHex16(bootHex,out boot))
            {PublishError("android_nsd_malformed_metadata");return;}
            var canonical=_requestedServiceType??serviceType;var key=Key(instance,canonical);var service=new DiscoveredRobot{ServiceKey=key,InstanceName=instance,ServiceType=canonical,RobotId=robotId,ProtocolMajor=major,ControllerBootId=boot,BuildId=buildId,Endpoint=new IPEndPoint(address,port)};
            Enqueue(new DiscoveryChange{Kind=DiscoveryChangeKind.Updated,Service=service,ServiceKey=key});
        }
        void OnLost(string instance,string serviceType)
        {var key=Key(instance,_requestedServiceType??serviceType);Enqueue(new DiscoveryChange{Kind=DiscoveryChangeKind.Removed,ServiceKey=key});}
        void PublishError(string category)=>Enqueue(new DiscoveryChange{Kind=DiscoveryChangeKind.Error,ErrorCategory=category});
        void Enqueue(DiscoveryChange change){lock(_callbackGate){if(!IsRunning)return;if(Interlocked.Increment(ref _callbackDepth)>128){Interlocked.Decrement(ref _callbackDepth);return;}_callbacks.Enqueue(change);}}
        static string Key(string instance,string serviceType)=>(serviceType??"")+"|"+(instance??"");
        static string AndroidServiceType(string canonical)=>canonical.EndsWith(".local",StringComparison.Ordinal)?canonical.Substring(0,canonical.Length-6):canonical;
        static bool TryHex16(string value,out byte[] bytes)
        {
            bytes=null;if(value==null||value.Length!=32)return false;var result=new byte[16];
            for(var i=0;i<16;i++){int hi=Nibble(value[i*2]),lo=Nibble(value[i*2+1]);if(hi<0||lo<0)return false;result[i]=(byte)((hi<<4)|lo);}bytes=result;return true;
        }
        static int Nibble(char c)=>c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;

#if UNITY_ANDROID && !UNITY_EDITOR
        sealed class ListenerProxy:AndroidJavaProxy
        {
            readonly AndroidNsdDiscoveryBackend _owner;
            public ListenerProxy(AndroidNsdDiscoveryBackend owner):base("dev.phantom.nsd.PhantomNsdBridge$Listener"){_owner=owner;}
            public void onResolved(string instance,string serviceType,string host,int port,string robotId,string protocolMajor,string bootHex,string buildId)=>_owner.OnResolved(instance,serviceType,host,port,robotId,protocolMajor,bootHex,buildId);
            public void onLost(string instance,string serviceType)=>_owner.OnLost(instance,serviceType);
            public void onError(string category)=>_owner.PublishError(category);
        }
#endif
    }
}
