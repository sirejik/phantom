namespace Phantom.Mapping
{
    public enum PhantomState:ushort { Boot=0,UserCalibration=1,Discovery=2,ConnectedUnreferenced=3,RobotCalibration=4,Ready=5,Hold=6,Tracking=7,SafeHold=8,Stopped=9,Commissioning=10,Fault=100 }
    public enum PhantomFault:ushort { None=0,Timeout=100,Config=101,Limit=102,JointStall=103,Gripper=104,Reference=105,Localization=106,ControllerProcess=107,LoopOverrun=108,Security=109,MotorOverload=110,Space=111,GripperHome=112,CollisionSet=113,PayloadProfile=114,HoldOverload=115,BatteryLow=116 }
    public struct SafetyPredicates
    {
        public bool AppFocused,XrReady,WristValid,ShoulderValid,LeftControllerValid,UserCalibrationValid,NetworkDiscovered,Connected,RobotReferenceValid,EnableHeld,Fault,LocalStop;
        public bool TrackingValid=>AppFocused&&XrReady&&WristValid&&ShoulderValid&&LeftControllerValid;
        public bool AllReady=>TrackingValid&&UserCalibrationValid&&Connected&&RobotReferenceValid&&!Fault&&!LocalStop;
    }
    public sealed class PhantomStateMachine
    {
        bool _armed,_previousGrip,_safeHoldLatched;public PhantomState State{get;private set;}=PhantomState.Boot;
        public PhantomState Update(SafetyPredicates p)
        {
            var rising=p.EnableHeld&&!_previousGrip;_previousGrip=p.EnableHeld;
            if(p.LocalStop){_armed=false;_safeHoldLatched=true;return State=PhantomState.Stopped;}
            if(p.Fault){_armed=false;_safeHoldLatched=true;return State=PhantomState.Fault;}
            if(State==PhantomState.Tracking&&!p.AllReady){_armed=false;_safeHoldLatched=true;return State=PhantomState.SafeHold;}
            if(!p.XrReady||!p.TrackingValid){if(State==PhantomState.SafeHold||State==PhantomState.Tracking)_safeHoldLatched=true;return State=State==PhantomState.Boot?PhantomState.Boot:PhantomState.SafeHold;}
            if(!p.UserCalibrationValid)return State=PhantomState.UserCalibration;
            if(!p.NetworkDiscovered)return State=PhantomState.Discovery;
            if(!p.Connected)return State=PhantomState.Discovery;
            if(!p.RobotReferenceValid)return State=PhantomState.ConnectedUnreferenced;
            if(_safeHoldLatched){if(p.EnableHeld)return State=PhantomState.SafeHold;_safeHoldLatched=false;_armed=true;return State=PhantomState.Hold;}
            if(State!=PhantomState.Ready&&State!=PhantomState.Hold&&State!=PhantomState.Tracking){State=PhantomState.Ready;_armed=!p.EnableHeld;return State;}
            if(!p.EnableHeld){_armed=true;return State=PhantomState.Hold;}
            if(_armed&&rising){_armed=false;return State=PhantomState.Tracking;}
            return State==PhantomState.Tracking?PhantomState.Tracking:PhantomState.Hold;
        }
        public void OnReferenceSpaceChange(){_armed=false;_safeHoldLatched=true;State=PhantomState.SafeHold;}
    }
    public sealed class EnableHysteresis
    {
        readonly float _engage,_release;public bool Held{get;private set;}public EnableHysteresis(float engage=.60f,float release=.45f){if(release>=engage)throw new System.ArgumentException("release < engage");_engage=engage;_release=release;}
        public bool Update(float value,bool valid=true){if(!valid||float.IsNaN(value)||float.IsInfinity(value)){Held=false;return false;}if(Held&&value<=_release)Held=false;else if(!Held&&value>=_engage)Held=true;return Held;}
    }
}
