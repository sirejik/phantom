using System;
using Phantom.Networking;

namespace Phantom.Logging
{
    public sealed class QuestNetworkEventSink:INetworkEventSink
    {
        readonly QuestJsonlLogger _logger;readonly BoundedNetworkFlightRecorder _flight;
        public QuestNetworkEventSink(QuestJsonlLogger logger,BoundedNetworkFlightRecorder flight){_logger=logger??throw new ArgumentNullException(nameof(logger));_flight=flight??throw new ArgumentNullException(nameof(flight));}
        public void Record(NetworkEvent value)
        {
            _flight.Record(value);if(value==null)return;
            var payload="{\"robot_id\":\""+Escape(value.RobotId)+"\",\"boot_id\":\""+Escape(value.BootId)+"\",\"endpoint\":\""+Escape(value.Endpoint)+"\",\"detail\":\""+Escape(value.Detail)+"\",\"rtt_ms\":"+value.RttMilliseconds.ToString(System.Globalization.CultureInfo.InvariantCulture)+",\"telemetry_age_ms\":"+value.TelemetryAgeMilliseconds+"}";
            _logger.Log("stage3-network",value.Name,value.State,value.SessionId,payload);
        }
        static string Escape(string value)=>(value??"").Replace("\\","\\\\").Replace("\"","\\\"").Replace("\r","").Replace("\n"," ");
    }
}
