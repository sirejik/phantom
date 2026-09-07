using Phantom.Networking.Generated;

namespace Phantom.Mapping
{
    /// <summary>
    /// Product-visible state. The numeric values are taken from the generated wire
    /// enum so a schema change cannot leave a hand-maintained copy behind.
    /// `FAULT` is deliberately absent: SYSTEM_ARCHITECTURE 4.3 makes a latched
    /// fault a `STOPPED` wire state plus a non-zero fault code, never its own
    /// state, so the fault condition is carried separately in
    /// <see cref="PhantomStateMachine.FaultLatched"/>.
    /// </summary>
    public enum PhantomState : ushort
    {
        Boot = (ushort)WireV1.State.Boot,
        UserCalibration = (ushort)WireV1.State.UserCalibration,
        Discovery = (ushort)WireV1.State.Discovery,
        ConnectedUnreferenced = (ushort)WireV1.State.ConnectedUnreferenced,
        RobotCalibration = (ushort)WireV1.State.RobotCalibration,
        Ready = (ushort)WireV1.State.Ready,
        Hold = (ushort)WireV1.State.Hold,
        Tracking = (ushort)WireV1.State.Tracking,
        SafeHold = (ushort)WireV1.State.SafeHold,
        Stopped = (ushort)WireV1.State.Stopped,
        Commissioning = (ushort)WireV1.State.Commissioning
    }

    public enum PhantomFault : ushort
    {
        None = (ushort)WireV1.Fault.None,
        Timeout = (ushort)WireV1.Fault.FaultTimeout,
        Config = (ushort)WireV1.Fault.FaultConfig,
        Limit = (ushort)WireV1.Fault.FaultLimit,
        JointStall = (ushort)WireV1.Fault.FaultJointStall,
        Gripper = (ushort)WireV1.Fault.FaultGripper,
        Reference = (ushort)WireV1.Fault.FaultReference,
        Localization = (ushort)WireV1.Fault.FaultLocalization,
        ControllerProcess = (ushort)WireV1.Fault.FaultControllerProcess,
        LoopOverrun = (ushort)WireV1.Fault.FaultLoopOverrun,
        Security = (ushort)WireV1.Fault.FaultSecurity,
        MotorOverload = (ushort)WireV1.Fault.FaultMotorOverload,
        Space = (ushort)WireV1.Fault.FaultSpace,
        GripperHome = (ushort)WireV1.Fault.FaultGripperHome,
        CollisionSet = (ushort)WireV1.Fault.FaultCollisionSet,
        PayloadProfile = (ushort)WireV1.Fault.FaultPayloadProfile,
        HoldOverload = (ushort)WireV1.Fault.FaultHoldOverload,
        BatteryLow = (ushort)WireV1.Fault.FaultBatteryLow
    }

    public struct SafetyPredicates
    {
        public bool AppFocused, XrReady, WristValid, ShoulderValid, LeftControllerValid;
        public bool UserCalibrationValid, NetworkDiscovered, Connected, RobotReferenceValid;
        public bool EnableHeld, Fault, LocalStop;

        /// <summary>Fresh TELEMETRY of the current session and controller boot.</summary>
        public bool TelemetryFresh;
        /// <summary>`TELEMETRY.last_accepted_command_sequence` from that telemetry.</summary>
        public ulong LastAcceptedCommandSequence;

        public bool TrackingValid => AppFocused && XrReady && WristValid && ShoulderValid && LeftControllerValid;
        public bool AllReady => TrackingValid && UserCalibrationValid && Connected && RobotReferenceValid && !Fault && !LocalStop;
    }

    public sealed class PhantomStateMachine
    {
        bool _armed, _previousGrip, _safeHoldLatched, _releaseConfirmed, _releasePending;
        ulong _releaseOffSequence;

        public PhantomState State { get; private set; } = PhantomState.Boot;
        public PhantomFault FaultCode { get; private set; } = PhantomFault.None;
        /// <summary>A latched fault is reported on the wire as STOPPED + fault code.</summary>
        public bool FaultLatched { get; private set; }
        public bool Armed => _armed;
        public bool ReleaseConfirmed => _releaseConfirmed;
        public ulong ReleaseOffSequence => _releaseOffSequence;

        /// <summary>
        /// Records the wire sequence of the canonical OFF/HOLD release COMMAND
        /// (`MOTION_ENABLE=0 &amp;&amp; HOLD_REQUEST=1`) the client just sent.
        /// SAFETY S9: the local observation that the grip was released is not
        /// enough; arming waits for EV3 to confirm acceptance of this exact
        /// sequence through fresh telemetry of the same session.
        /// </summary>
        public void NoteReleaseCommandSent(ulong offSequence)
        {
            _releaseOffSequence = offSequence;
            _releasePending = true;
            _releaseConfirmed = false;
            _armed = false;
        }

        public PhantomState Update(SafetyPredicates p)
        {
            var rising = p.EnableHeld && !_previousGrip;
            _previousGrip = p.EnableHeld;

            // A deliberate release is confirmed only by fresh telemetry of the
            // current session showing EV3 accepted the OFF/HOLD sequence.
            if (_releasePending && p.TelemetryFresh && p.LastAcceptedCommandSequence >= _releaseOffSequence)
            {
                _releasePending = false;
                _releaseConfirmed = true;
            }
            if (!p.TelemetryFresh) _releaseConfirmed = false;

            if (p.LocalStop) { Disarm(); _safeHoldLatched = true; FaultLatched = false; return State = PhantomState.Stopped; }
            if (p.Fault)
            {
                Disarm(); _safeHoldLatched = true; FaultLatched = true;
                if (FaultCode == PhantomFault.None) FaultCode = PhantomFault.Limit;
                return State = PhantomState.Stopped;
            }
            FaultLatched = false; FaultCode = PhantomFault.None;

            if (State == PhantomState.Tracking && !p.AllReady) { Disarm(); _safeHoldLatched = true; return State = PhantomState.SafeHold; }
            if (!p.XrReady || !p.TrackingValid)
            {
                if (State == PhantomState.SafeHold || State == PhantomState.Tracking) _safeHoldLatched = true;
                return State = State == PhantomState.Boot ? PhantomState.Boot : PhantomState.SafeHold;
            }
            if (!p.UserCalibrationValid) return State = PhantomState.UserCalibration;
            if (!p.NetworkDiscovered || !p.Connected) return State = PhantomState.Discovery;
            if (!p.RobotReferenceValid) return State = PhantomState.ConnectedUnreferenced;

            if (_safeHoldLatched)
            {
                if (p.EnableHeld) return State = PhantomState.SafeHold;
                _safeHoldLatched = false;
                _armed = _releaseConfirmed;
                return State = PhantomState.Hold;
            }
            if (State != PhantomState.Ready && State != PhantomState.Hold && State != PhantomState.Tracking)
            {
                State = PhantomState.Ready;
                _armed = !p.EnableHeld && _releaseConfirmed;
                return State;
            }
            if (!p.EnableHeld) { _armed = _releaseConfirmed; return State = PhantomState.Hold; }
            if (_armed && rising) { _armed = false; return State = PhantomState.Tracking; }
            return State == PhantomState.Tracking ? PhantomState.Tracking : PhantomState.Hold;
        }

        /// <summary>Reference-space change or resume: S36 removes motion permission.</summary>
        public void OnReferenceSpaceChange()
        {
            Disarm(); _safeHoldLatched = true; State = PhantomState.SafeHold;
        }

        /// <summary>Any arm-invalidating event also invalidates the release latch (S9).</summary>
        void Disarm()
        {
            _armed = false;
            _releaseConfirmed = false;
            _releasePending = false;
            _releaseOffSequence = 0;
        }
    }

    public sealed class EnableHysteresis
    {
        readonly float _engage, _release;
        public bool Held { get; private set; }
        public EnableHysteresis(float engage = .60f, float release = .45f)
        {
            if (release >= engage) throw new System.ArgumentException("release < engage");
            _engage = engage; _release = release;
        }
        public bool Update(float value, bool valid = true)
        {
            if (!valid || float.IsNaN(value) || float.IsInfinity(value)) { Held = false; return false; }
            if (Held && value <= _release) Held = false;
            else if (!Held && value >= _engage) Held = true;
            return Held;
        }
    }
}
