namespace Phantom.Mapping
{
    public enum PhantomState { Disconnected, Initializing, RoomRequired, RobotCalibration, UserCalibration, Ready, ArmedHold, Tracking, SafeHold, Fault }

    public struct SafetyPredicates
    {
        public bool AppFocused, RightHandValid, LeftControllerValid, EnableHeld, UserCalibrationValid, RobotGeometryValid, RoomValid, NetworkReady, Fault;
        public bool TrackingValid => AppFocused && RightHandValid && LeftControllerValid;
        public bool AllReady => TrackingValid && UserCalibrationValid && RobotGeometryValid && RoomValid && NetworkReady && !Fault;
    }

    public sealed class PhantomStateMachine
    {
        bool _requireRelease;
        public PhantomState State { get; private set; } = PhantomState.Disconnected;

        public PhantomState Update(SafetyPredicates p)
        {
            if (p.Fault) { State=PhantomState.Fault;_requireRelease=true;return State; }
            if(State==PhantomState.Tracking&&!p.AllReady){State=PhantomState.SafeHold;_requireRelease=true;return State;}
            if (!p.RoomValid) { State=PhantomState.RoomRequired;return State; }
            if (!p.NetworkReady) { if(State==PhantomState.Tracking){State=PhantomState.SafeHold;_requireRelease=true;}else if(State!=PhantomState.SafeHold)State=PhantomState.Disconnected; return State; }
            if (!p.RobotGeometryValid) { State=PhantomState.RobotCalibration;return State; }
            if (!p.UserCalibrationValid) { State=PhantomState.UserCalibration;return State; }
            if (!p.TrackingValid)
            {
                if(State==PhantomState.Tracking||State==PhantomState.ArmedHold||State==PhantomState.SafeHold){State=PhantomState.SafeHold;_requireRelease=true;}else State=PhantomState.Ready;
                return State;
            }
            if (_requireRelease)
            {
                State=PhantomState.SafeHold;
                if(!p.EnableHeld){_requireRelease=false;State=PhantomState.ArmedHold;}
                return State;
            }
            if (!p.EnableHeld) { State=PhantomState.ArmedHold;return State; }
            State=PhantomState.Tracking;return State;
        }
    }

    public sealed class EnableHysteresis
    {
        readonly float _engage,_release; public bool Held{get;private set;}
        public EnableHysteresis(float engage,float release){if(release>=engage)throw new System.ArgumentException("release must be below engage");_engage=engage;_release=release;}
        public bool Update(float value){if(float.IsNaN(value)||float.IsInfinity(value))return Held;if(Held&&value<=_release)Held=false;else if(!Held&&value>=_engage)Held=true;return Held;}
    }
}
