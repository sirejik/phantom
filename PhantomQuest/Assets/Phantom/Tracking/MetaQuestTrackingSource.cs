using System;
using System.Collections.Generic;
using Phantom.Kinematics;
using UnityEngine;
using UnityEngine.XR;
using UnityEngine.XR.Hands;

namespace Phantom.Tracking
{
    // SDK boundary: all Unity left-handed coordinates are converted here to the
    // canonical robot convention (+X forward, +Y left, +Z up).
    public sealed class MetaQuestTrackingSource : MonoBehaviour, IPhantomTrackingSource
    {
        static readonly List<XRHandSubsystem> HandSubsystems = new List<XRHandSubsystem>();
        static readonly List<InputDevice> LeftControllerDevices = new List<InputDevice>();
        XRHandSubsystem _hands;
        InputDevice _leftController;
        InputDevice _head;
        float _nextControllerScan;
        bool _multimodalConfigured;
        float _nextMultimodalAttempt;
        string _multimodalStatus = "waiting_for_openxr_session";

        public bool MultimodalConfigured => _multimodalConfigured;
        public string MultimodalStatus => _multimodalStatus;

        public static Vec3 UnityToCanonical(Vector3 value) => new Vec3(value.z, -value.x, value.y);

        void UpdateDevices()
        {
            TryEnableMultimodal();
            if (_hands == null || !_hands.running) { HandSubsystems.Clear(); SubsystemManager.GetSubsystems(HandSubsystems); _hands = HandSubsystems.Find(s => s.running); }
            if (!IsPhysicalLeftController(_leftController) || Time.unscaledTime >= _nextControllerScan) SelectPhysicalLeftController();
            if (!_head.isValid) _head = InputDevices.GetDeviceAtXRNode(XRNode.Head);
        }

        void SelectPhysicalLeftController()
        {
            _nextControllerScan = Time.unscaledTime + 1f;
            LeftControllerDevices.Clear();
            InputDevices.GetDevicesWithCharacteristics(InputDeviceCharacteristics.Left | InputDeviceCharacteristics.Controller, LeftControllerDevices);
            var selected = default(InputDevice);
            foreach (var candidate in LeftControllerDevices)
            {
                if (!IsPhysicalLeftController(candidate)) continue;
                if (!selected.isValid || candidate.name.IndexOf("Touch", StringComparison.OrdinalIgnoreCase) >= 0) selected = candidate;
            }
            if (!selected.Equals(_leftController))
            {
                _leftController = selected;
                Debug.Log($"PHANTOM left_controller_source={(_leftController.isValid ? _leftController.name : "none")} characteristics={(_leftController.isValid ? _leftController.characteristics.ToString() : "none")}");
            }
        }

        static bool IsPhysicalLeftController(InputDevice device)
        {
            if (!device.isValid) return false;
            var required = InputDeviceCharacteristics.Left | InputDeviceCharacteristics.Controller;
            if ((device.characteristics & required) != required) return false;
            if (device.name.IndexOf("Hand Interaction", StringComparison.OrdinalIgnoreCase) >= 0) return false;
            return device.TryGetFeatureValue(CommonUsages.primaryButton, out _) || device.TryGetFeatureValue(CommonUsages.secondaryButton, out _);
        }

        void TryEnableMultimodal()
        {
            if (_multimodalConfigured || Time.unscaledTime < _nextMultimodalAttempt) return;
            _nextMultimodalAttempt = Time.unscaledTime + 1f;
            if (!OVRPlugin.initialized)
            {
                SetMultimodalStatus("waiting_for_ovrplugin", false);
                return;
            }

            bool enabled;
            try { enabled = OVRInput.EnableSimultaneousHandsAndControllers(); }
            catch (Exception exception)
            {
                SetMultimodalStatus("enable_exception_" + exception.GetType().Name, false);
                return;
            }
            SetMultimodalStatus(enabled ? "enabled" : "enable_rejected_retrying", enabled);
        }

        void SetMultimodalStatus(string status, bool configured)
        {
            if (_multimodalStatus == status && _multimodalConfigured == configured) return;
            _multimodalStatus = status;
            _multimodalConfigured = configured;
            Debug.Log($"PHANTOM multimodal_configured={configured} status={status}");
        }

        void ResetMultimodal(string reason)
        {
            _multimodalConfigured = false;
            _multimodalStatus = reason;
            _nextMultimodalAttempt = 0f;
            Debug.Log($"PHANTOM multimodal_configured=false status={reason}");
        }

        void OnApplicationFocus(bool focused) { if (focused) ResetMultimodal("focus_resume_retry"); }
        void OnApplicationPause(bool paused) { if (!paused) ResetMultimodal("app_resume_retry"); }

        public bool TryGetFrame(out TrackingFrame frame)
        {
            UpdateDevices(); frame = new TrackingFrame { MonotonicTimeUs = (long)(Time.realtimeSinceStartupAsDouble * 1000000), AppFocused = Application.isFocused, MultimodalConfigured = _multimodalConfigured };
            if (_head.isValid && _head.TryGetFeatureValue(CommonUsages.devicePosition, out var headPosition)) frame.Head = new PoseObservation { Position=UnityToCanonical(headPosition),Valid=true };
            frame.LeftController = ReadController(); frame.RightHand = ReadRightHand();
            frame.BothValid = frame.RightHand.Valid && frame.LeftController.Valid;
            frame.InteractionMode = frame.BothValid ? "simultaneous" : frame.RightHand.Valid ? "hand_only" : frame.LeftController.Valid ? "controller_only" : "none";
            var handSource = _hands != null && _hands.running ? _hands.subsystemDescriptor.id : "no_hand_subsystem";
            var controllerSource = _leftController.isValid ? _leftController.name : "no_left_controller";
            frame.InteractionSource = handSource + " + " + controllerSource;
            return frame.Head.Valid || frame.RightHand.Valid || frame.LeftController.Valid;
        }

        HandState ReadRightHand()
        {
            var state = new HandState(); if (_hands == null || !_hands.running) return state;
            var hand = _hands.rightHand; state.Valid = hand.isTracked;
            if (hand.GetJoint(XRHandJointID.Wrist).TryGetPose(out var wrist)) state.Wrist = new PoseObservation { Position=UnityToCanonical(wrist.position),Valid=true };
            if (hand.GetJoint(XRHandJointID.Palm).TryGetPose(out var palm)) state.Palm = new PoseObservation { Position=UnityToCanonical(palm.position),Valid=true };
            var gestures = _hands.rightHandCommonGestures;
            var ready = gestures.TryGetGraspValue(out var grasp);
            state.Grasp = new GripObservation { Value01=grasp,Ready=ready,Valid=state.Valid };
            return state;
        }

        ControllerState ReadController()
        {
            var state = new ControllerState();
            if (!_leftController.isValid) return state;
            var poseReady=_leftController.TryGetFeatureValue(CommonUsages.devicePosition,out var p);
            var trackingKnown=_leftController.TryGetFeatureValue(CommonUsages.isTracked,out var isTracked);
            state.Valid=poseReady&&(!trackingKnown||isTracked);
            if (poseReady) state.Pose=new PoseObservation{Position=UnityToCanonical(p),Valid=state.Valid};
            _leftController.TryGetFeatureValue(CommonUsages.grip,out state.GripAnalog);
            _leftController.TryGetFeatureValue(CommonUsages.gripButton,out state.GripHeld);
            _leftController.TryGetFeatureValue(CommonUsages.trigger,out state.Trigger);
            _leftController.TryGetFeatureValue(CommonUsages.primaryButton,out state.X);
            _leftController.TryGetFeatureValue(CommonUsages.secondaryButton,out state.Y);
            return state;
        }

        public void Haptic(float amplitude,float duration)
        {
            UpdateDevices(); if(_leftController.isValid)_leftController.SendHapticImpulse(0,Mathf.Clamp01(amplitude),Mathf.Max(0,duration));
        }
    }
}
