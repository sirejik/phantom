using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace Phantom.Logging
{
    [Serializable]
    public sealed class QuestLogEvent
    {
        public long monotonic_time_us; public string run_id; public string session_id; public string test_id; public string event_name; public string state; public string payload_json;
    }

    /// <summary>
    /// Bounded JSONL run log.
    ///
    /// Two properties matter beyond writing lines. First, retention: a new run
    /// file per launch with no ceiling would grow app-private storage without
    /// bound (ENGINEERING 8.13). Second, isolation: a storage failure must never
    /// propagate out of the caller, because this logger is driven from the Unity
    /// update loop and an exception there would take the network client down with
    /// it. A degraded logger reports itself once and keeps the app running.
    /// </summary>
    public sealed class QuestJsonlLogger : IDisposable
    {
        const double FlushIntervalSeconds = 1.0;

        StreamWriter _writer;
        double _nextFlush;
        public string RunId { get; }
        public string Path { get; }
        public string Directory { get; }
        /// <summary>True once a write or rotation failed; the app keeps running.</summary>
        public bool Degraded { get; private set; }
        public string DegradedReason { get; private set; }
        public int DroppedEvents { get; private set; }
        public int RetainedRuns { get; private set; }

        public QuestJsonlLogger(string runId = null, int retentionDays = 7, int maxMegabytes = 250, int maxRuns = 64)
        {
            RunId = runId ?? Guid.NewGuid().ToString("N");
            Directory = System.IO.Path.Combine(Application.persistentDataPath, "phantom-runs");
            Path = System.IO.Path.Combine(Directory, RunId + ".jsonl");
            try
            {
                System.IO.Directory.CreateDirectory(Directory);
                RetainedRuns = EnforceRetention(Directory, retentionDays, maxMegabytes, maxRuns, DateTime.UtcNow);
                _writer = new StreamWriter(Path, true) { AutoFlush = false };
            }
            catch (Exception error) when (error is IOException || error is UnauthorizedAccessException || error is SystemException)
            {
                Degrade("open:" + error.GetType().Name);
            }
        }

        /// <summary>
        /// Age, size and count bounded retention. Oldest runs go first; the file of
        /// the current run is never a candidate because it does not exist yet.
        /// </summary>
        public static int EnforceRetention(string directory, int retentionDays, int maxMegabytes, int maxRuns, DateTime utcNow)
        {
            var files = new List<FileInfo>();
            var info = new DirectoryInfo(directory);
            if (!info.Exists) return 0;
            foreach (var file in info.GetFiles("*.jsonl")) files.Add(file);
            files.Sort((a, b) => a.LastWriteTimeUtc.CompareTo(b.LastWriteTimeUtc));
            long total = 0;
            foreach (var file in files) total += file.Length;
            var ceiling = (long)maxMegabytes * 1024L * 1024L;
            var horizon = TimeSpan.FromDays(Math.Max(0, retentionDays));
            var remaining = files.Count;
            foreach (var file in files)
            {
                var tooOld = utcNow - file.LastWriteTimeUtc > horizon;
                var tooMany = remaining > maxRuns;
                if (!tooOld && total <= ceiling && !tooMany) continue;
                try { var length = file.Length; file.Delete(); total -= length; remaining--; }
                catch (Exception error) when (error is IOException || error is UnauthorizedAccessException) { }
            }
            return remaining;
        }

        public void Log(string testId, string eventName, string state, string sessionId, string payloadJson = "{}")
        {
            if (_writer == null) { DroppedEvents++; return; }
            var e = new QuestLogEvent
            {
                monotonic_time_us = (long)(Time.realtimeSinceStartupAsDouble * 1000000),
                run_id = RunId, session_id = sessionId ?? "", test_id = testId ?? "",
                event_name = eventName ?? "", state = state ?? "", payload_json = payloadJson ?? "{}"
            };
            try
            {
                _writer.WriteLine(JsonUtility.ToJson(e));
                var now = Time.realtimeSinceStartupAsDouble;
                if (now >= _nextFlush) { _writer.Flush(); _nextFlush = now + FlushIntervalSeconds; }
            }
            catch (Exception error) when (error is IOException || error is ObjectDisposedException || error is SystemException)
            {
                // Storage is full, revoked or gone. Losing diagnostics is acceptable;
                // throwing into the frame loop is not.
                Degrade("write:" + error.GetType().Name);
            }
        }

        void Degrade(string reason)
        {
            DroppedEvents++;
            if (Degraded) return;
            Degraded = true;
            DegradedReason = reason;
            try { _writer?.Dispose(); } catch (Exception) { }
            _writer = null;
            // Single, bounded report; never a per-frame exception storm.
            UnityEngine.Debug.LogWarning("LOG_STORAGE_DEGRADED " + reason);
        }

        public void Dispose()
        {
            try { _writer?.Dispose(); } catch (Exception) { }
            _writer = null;
        }
    }
}
