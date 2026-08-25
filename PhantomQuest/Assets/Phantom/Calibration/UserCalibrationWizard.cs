using System.Collections.Generic;
using Phantom.Kinematics;
using Phantom.Room;
using Phantom.Tracking;

namespace Phantom.Calibration
{
    public sealed class UserCalibrationWizard
    {
        readonly List<Vec3> _wristSamples=new List<Vec3>(); readonly CalibrationZone _zone;
        Vec3 _headStart; bool _started;
        public string Status { get; private set; }="not_started";
        public int SampleCount=>_wristSamples.Count;
        public UserCalibrationWizard(CalibrationZone zone){_zone=zone;}
        public void Start(TrackingFrame frame){_wristSamples.Clear();_headStart=frame.Head.Position;_started=true;Status="trace_horizontal_vertical_diagonal";}
        public bool Add(TrackingFrame frame)
        {
            if(!_started||!frame.RightHand.Wrist.Valid||!frame.Head.Valid)return false;
            var translation=(frame.Head.Position-_headStart).Magnitude;
            if(translation>_zone.RadiusMeters||!_zone.Contains(frame.Head.Position)){Status="body_motion_detected";return false;}
            _wristSamples.Add(frame.RightHand.Wrist.Position);return true;
        }
        public UserCalibration Finish(TrackingFrame frame)
        {
            _started=false;var fit=new ShoulderSphereFit().Fit(_wristSamples);Status=fit.Quality.Valid?"complete":fit.Quality.FailureReason;
            return new UserCalibration{ShoulderCenterRoom0=fit.Center,ArmLengthWristMeters=fit.Quality.ArmLengthMeters,HeadRoomAtCalibration=frame.Head.Position,Quality=fit.Quality};
        }
    }
}
