using System;
using System.IO;
using UnityEngine;

namespace Phantom.Logging
{
    [Serializable]
    public sealed class QuestLogEvent
    {
        public long monotonic_time_us; public string run_id; public string session_id; public string test_id; public string event_name; public string state; public string payload_json;
    }

    public sealed class QuestJsonlLogger : IDisposable
    {
        const double FlushIntervalSeconds=1.0;
        readonly StreamWriter _writer; double _nextFlush;
        public string RunId{get;} public string Path{get;}
        public QuestJsonlLogger(string runId=null)
        {
            RunId=runId??Guid.NewGuid().ToString("N");var dir=System.IO.Path.Combine(Application.persistentDataPath,"phantom-runs");Directory.CreateDirectory(dir);Path=System.IO.Path.Combine(dir,RunId+".jsonl");_writer=new StreamWriter(Path,true){AutoFlush=false};
        }
        public void Log(string testId,string eventName,string state,string sessionId,string payloadJson="{}")
        {
            var e=new QuestLogEvent{monotonic_time_us=(long)(Time.realtimeSinceStartupAsDouble*1000000),run_id=RunId,session_id=sessionId??"",test_id=testId??"",event_name=eventName??"",state=state??"",payload_json=payloadJson??"{}"};
            _writer.WriteLine(JsonUtility.ToJson(e));
            var now=Time.realtimeSinceStartupAsDouble;
            if(now>=_nextFlush){_writer.Flush();_nextFlush=now+FlushIntervalSeconds;}
        }
        public void Dispose()=>_writer.Dispose();
    }
}
