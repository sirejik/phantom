using System;
using NUnit.Framework;
using Phantom.Kinematics;
using Phantom.Mapping;
using Phantom.Networking;

namespace Phantom.Tests
{
    public sealed class ProtocolAndStateTests
    {
        [Test]
        public void Protocol_GoldenVectorAndRoundTrip()
        {
            var packet=new TargetPacket{Flags=CommandFlags.Tracking,SessionId=0x0102030405060708,Sequence=0x0a0b0c0d,ClientTimeUs=0x1112131415161718,Target=new JointAngles(1,-2,0.5),GripIntent=0.25f};
            var bytes=ProtocolCodec.EncodeTarget(packet);var hex=BitConverter.ToString(bytes).Replace("-","").ToLowerInvariant();
            Assert.That(hex,Is.EqualTo("50484e540100020008070605040302010d0c0b0a18171615141312110000803f000000c00000003f0000803e6230dfde"));
            Assert.That(ProtocolCodec.TryDecodeTarget(bytes,out var decoded),Is.True);Assert.That(decoded.SessionId,Is.EqualTo(packet.SessionId));Assert.That(decoded.Target.Shoulder,Is.EqualTo(-2));
            bytes[12]^=0x80;Assert.That(ProtocolCodec.TryDecodeTarget(bytes,out _),Is.False);
        }

        [Test]
        public void SequenceComparison_HandlesWrapAndRejectsStale()
        {
            Assert.That(SequenceMath.IsNewer(11,10),Is.True);Assert.That(SequenceMath.IsNewer(9,10),Is.False);Assert.That(SequenceMath.IsNewer(0,uint.MaxValue),Is.True);Assert.That(SequenceMath.IsNewer(10,10),Is.False);
        }

        [Test]
        public void StateMachine_RequiresExplicitReleaseAfterLoss()
        {
            var sm=new PhantomStateMachine();var p=new SafetyPredicates{AppFocused=true,RightHandValid=true,LeftControllerValid=true,RoomValid=true,RobotGeometryValid=true,UserCalibrationValid=true,NetworkReady=true};
            Assert.That(sm.Update(p),Is.EqualTo(PhantomState.ArmedHold));p.EnableHeld=true;Assert.That(sm.Update(p),Is.EqualTo(PhantomState.Tracking));
            p.RightHandValid=false;Assert.That(sm.Update(p),Is.EqualTo(PhantomState.SafeHold));p.RightHandValid=true;Assert.That(sm.Update(p),Is.EqualTo(PhantomState.SafeHold));
            p.EnableHeld=false;Assert.That(sm.Update(p),Is.EqualTo(PhantomState.ArmedHold));p.EnableHeld=true;Assert.That(sm.Update(p),Is.EqualTo(PhantomState.Tracking));
        }

        [Test]
        public void EnableUsesHysteresis()
        {
            var h=new EnableHysteresis(0.75f,0.55f);Assert.That(h.Update(0.7f),Is.False);Assert.That(h.Update(0.8f),Is.True);Assert.That(h.Update(0.6f),Is.True);Assert.That(h.Update(0.5f),Is.False);
        }

        [Test]
        public void StateMachine_RequiresRoomBeforeNetwork()
        {
            var sm=new PhantomStateMachine();
            var p=new SafetyPredicates{RoomValid=false,NetworkReady=false};
            Assert.That(sm.Update(p),Is.EqualTo(PhantomState.RoomRequired));
            p.RoomValid=true;
            Assert.That(sm.Update(p),Is.EqualTo(PhantomState.Disconnected));
        }
    }
}
