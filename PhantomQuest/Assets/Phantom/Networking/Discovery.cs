using System;
using System.Collections.Generic;
using System.Net;

namespace Phantom.Networking
{
    public enum DiscoveryChangeKind { Added, Updated, Removed, Error }

    public sealed class DiscoveredRobot
    {
        public string ServiceKey;
        public string InstanceName;
        public string ServiceType;
        public string RobotId;
        public int ProtocolMajor;
        public byte[] ControllerBootId;
        public string BuildId;
        public IPEndPoint Endpoint;

        public DiscoveredRobot Clone()=>new DiscoveredRobot
        {
            ServiceKey=ServiceKey,InstanceName=InstanceName,ServiceType=ServiceType,RobotId=RobotId,
            ProtocolMajor=ProtocolMajor,ControllerBootId=ControllerBootId==null?null:(byte[])ControllerBootId.Clone(),
            BuildId=BuildId,Endpoint=Endpoint==null?null:new IPEndPoint(Endpoint.Address,Endpoint.Port)
        };

        public bool HasValidBootId
        {
            get
            {
                if(ControllerBootId==null||ControllerBootId.Length!=16)return false;
                var any=0;for(var i=0;i<ControllerBootId.Length;i++)any|=ControllerBootId[i];return any!=0;
            }
        }
    }

    public sealed class DiscoveryChange
    {
        public DiscoveryChangeKind Kind;
        public DiscoveredRobot Service;
        public string ServiceKey;
        public string ErrorCategory;
    }

    public interface IServiceDiscoveryBackend:IDisposable
    {
        event Action<DiscoveryChange> Changed;
        bool IsRunning{get;}
        void Start(string serviceType);
        void Poll();
        void Stop();
        bool TryResolve(string serviceKey,out DiscoveredRobot service);
    }

    public sealed class FakeDiscoveryBackend:IServiceDiscoveryBackend
    {
        readonly Dictionary<string,DiscoveredRobot> _services=new Dictionary<string,DiscoveredRobot>(StringComparer.Ordinal);
        string _serviceType;
        public event Action<DiscoveryChange> Changed;
        public bool IsRunning{get;private set;}
        public int StartCount{get;private set;}
        public int StopCount{get;private set;}

        public void Start(string serviceType)
        {
            if(IsRunning)return;
            if(string.IsNullOrWhiteSpace(serviceType))throw new ArgumentException("service type");
            _serviceType=serviceType;IsRunning=true;StartCount++;
            foreach(var service in _services.Values)Publish(DiscoveryChangeKind.Added,service,null);
        }

        public void Stop(){if(!IsRunning)return;IsRunning=false;StopCount++;}
        public void Poll(){}

        public void Add(DiscoveredRobot service)
        {
            ValidateKey(service);var copy=service.Clone();_services[copy.ServiceKey]=copy;
            if(IsRunning)Publish(DiscoveryChangeKind.Added,copy,null);
        }

        public void Update(DiscoveredRobot service)
        {
            ValidateKey(service);var copy=service.Clone();_services[copy.ServiceKey]=copy;
            if(IsRunning)Publish(DiscoveryChangeKind.Updated,copy,null);
        }

        public void Remove(string serviceKey)
        {
            if(string.IsNullOrEmpty(serviceKey))return;
            DiscoveredRobot existing;if(!_services.TryGetValue(serviceKey,out existing))return;
            _services.Remove(serviceKey);if(IsRunning)Publish(DiscoveryChangeKind.Removed,existing,serviceKey);
        }

        public void Fail(string category){if(IsRunning)Publish(DiscoveryChangeKind.Error,null,category??"discovery_error");}

        public bool TryResolve(string serviceKey,out DiscoveredRobot service)
        {
            DiscoveredRobot value;
            if(IsRunning&&_services.TryGetValue(serviceKey,out value)&&
               string.Equals(value.ServiceType,_serviceType,StringComparison.Ordinal))
            {service=value.Clone();return true;}
            service=null;return false;
        }

        public void Dispose(){Stop();_services.Clear();Changed=null;}
        void Publish(DiscoveryChangeKind kind,DiscoveredRobot service,string error)
            =>Changed?.Invoke(new DiscoveryChange{Kind=kind,Service=service?.Clone(),ServiceKey=service?.ServiceKey,ErrorCategory=error});
        static void ValidateKey(DiscoveredRobot service)
        {if(service==null||string.IsNullOrWhiteSpace(service.ServiceKey))throw new ArgumentException("service key");}
    }
}
