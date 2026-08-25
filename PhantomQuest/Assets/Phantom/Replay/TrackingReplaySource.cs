using System.Collections.Generic;
using Phantom.Tracking;

namespace Phantom.Replay
{
    public sealed class TrackingRecording
    {
        public readonly List<TrackingFrame> Frames=new List<TrackingFrame>();
    }

    public sealed class TrackingReplaySource : IPhantomTrackingSource
    {
        readonly IReadOnlyList<TrackingFrame> _frames; int _index;
        public TrackingReplaySource(IReadOnlyList<TrackingFrame> frames){_frames=frames;}
        public bool TryGetFrame(out TrackingFrame frame)
        {
            if(_frames==null||_index>=_frames.Count){frame=default;return false;}frame=_frames[_index++];return true;
        }
        public void Rewind()=>_index=0;
    }
}
