using System;using System.Security.Cryptography;using NUnit.Framework;using Phantom.Kinematics;using Phantom.Mapping;using Phantom.Networking;using Phantom.Networking.Generated;
namespace Phantom.Tests
{
 public sealed class ProtocolAndStateTests
 {
  static byte[] Key(){var k=new byte[32];for(var i=0;i<32;i++)k[i]=(byte)i;return k;}static byte[] Id(byte start){var b=new byte[16];for(var i=0;i<16;i++)b[i]=(byte)(start+i);return b;}
  [Test]public void Protocol_HmacRoundTripAndCorruption(){var payload=ProtocolCodec.EncodeCommand(new CommandPayload{Flags=MotionFlags.MotionEnable|MotionFlags.TrackingValid,Target=new JointAngles(1,-2,.5),GripIntent=.25f});var bytes=ProtocolCodec.Encode(WireV1.MessageType.Command,payload,Key(),Id(16),Id(32),1,123);Assert.That(bytes.Length,Is.EqualTo(120));Assert.That(ProtocolCodec.TryDecode(bytes,Key(),out var decoded),Is.True);Assert.That(ProtocolCodec.TryDecodeCommand(decoded.Payload,out var command),Is.True);Assert.That(command.Target.Shoulder,Is.EqualTo(-2));bytes[70]^=1;Assert.That(ProtocolCodec.TryDecode(bytes,Key(),out _),Is.False);}
  [Test]public void Protocol_RejectsWrongLengthReservedAndNonFinite(){var payload=ProtocolCodec.EncodeCommand(new CommandPayload{Flags=MotionFlags.HoldRequest,Target=new JointAngles(0,0,0),GripIntent=0});payload[23]=1;Assert.That(ProtocolCodec.TryDecodeCommand(payload,out _),Is.False);payload[23]=0;var nan=BitConverter.GetBytes(float.NaN);Buffer.BlockCopy(nan,0,payload,4,4);Assert.That(ProtocolCodec.TryDecodeCommand(payload,out _),Is.False);Assert.Throws<ArgumentException>(()=>ProtocolCodec.Encode(WireV1.MessageType.Command,new byte[23],Key(),Id(1),Id(2),1,0));}
  [Test]public void Protocol_RejectsAuthenticatedNonHandshakeWithZeroSequence(){var payload=ProtocolCodec.EncodeCommand(new CommandPayload{Flags=MotionFlags.HoldRequest,Target=new JointAngles(),GripIntent=0});var bytes=ProtocolCodec.Encode(WireV1.MessageType.Command,payload,Key(),Id(1),Id(2),1,0);Array.Clear(bytes,48,8);using(var h=new HMACSHA256(Key()))Buffer.BlockCopy(h.ComputeHash(bytes,0,bytes.Length-32),0,bytes,bytes.Length-32,32);Assert.False(ProtocolCodec.TryDecode(bytes,Key(),out _));}
  [Test]public void HelloAckDecoderExposesEchoedNonceAndProtocolContractHash(){var payload=new byte[364];var nonce=Id(9);Buffer.BlockCopy(nonce,0,payload,0,16);WriteId(payload,16,"phantom01");WriteId(payload,48,"test-build");var protocol=Hex(WireV1.ProtocolContractSha256);Buffer.BlockCopy(protocol,0,payload,116,32);var datagram=new DecodedDatagram{Header=new WireHeader{MessageType=WireV1.MessageType.HelloAck},Payload=payload};Assert.True(ServerProtocol.TryDecodeHelloAck(datagram,out var ack));CollectionAssert.AreEqual(nonce,ack.ClientNonce);CollectionAssert.AreEqual(protocol,ack.ProtocolContractHash);}
  static SafetyPredicates ReadyPredicates()=>new SafetyPredicates{AppFocused=true,XrReady=true,WristValid=true,ShoulderValid=true,LeftControllerValid=true,UserCalibrationValid=true,NetworkDiscovered=true,Connected=true,RobotReferenceValid=true};

  // Performs the whole SAFETY S9 sequence: release, canonical OFF/HOLD, EV3
  // acceptance visible in fresh telemetry, then a new rising edge.
  static bool ConfirmedRearm(PhantomStateMachine sm,ref SafetyPredicates p,ref ulong offSequence)
  {
   p.EnableHeld=false;sm.Update(p);
   offSequence++;sm.NoteReleaseCommandSent(offSequence);
   p.TelemetryFresh=true;p.LastAcceptedCommandSequence=offSequence;
   if(sm.Update(p)!=PhantomState.Hold||!sm.Armed)return false;
   p.EnableHeld=true;return sm.Update(p)==PhantomState.Tracking;
  }

  [Test]public void StateMachine_ArmsOnlyAfterEv3ConfirmedReleaseAndNewRisingEdge()
  {
   var sm=new PhantomStateMachine();var p=ReadyPredicates();ulong offSequence=0;
   Assert.That(sm.Update(p),Is.EqualTo(PhantomState.Ready));
   Assert.That(sm.Armed,Is.False,"READY must not arm before an EV3-confirmed release");
   // A local rising edge without confirmation must not reach TRACKING.
   p.EnableHeld=true;Assert.That(sm.Update(p),Is.Not.EqualTo(PhantomState.Tracking));
   p.EnableHeld=false;sm.Update(p);
   Assert.That(ConfirmedRearm(sm,ref p,ref offSequence),Is.True);
  }

  [Test]public void StateMachine_UnconfirmedReleaseNeverArms()
  {
   var sm=new PhantomStateMachine();var p=ReadyPredicates();
   sm.Update(p);
   sm.NoteReleaseCommandSent(9);
   p.TelemetryFresh=true;p.LastAcceptedCommandSequence=8;   // EV3 has not accepted it yet
   Assert.That(sm.Update(p),Is.EqualTo(PhantomState.Hold));
   Assert.That(sm.Armed,Is.False);
   p.EnableHeld=true;Assert.That(sm.Update(p),Is.Not.EqualTo(PhantomState.Tracking));
   p.EnableHeld=false;p.LastAcceptedCommandSequence=9;      // now confirmed
   Assert.That(sm.Update(p),Is.EqualTo(PhantomState.Hold));
   Assert.That(sm.Armed,Is.True);
  }

  [Test]public void StateMachine_StaleTelemetryInvalidatesTheReleaseConfirmation()
  {
   var sm=new PhantomStateMachine();var p=ReadyPredicates();ulong offSequence=0;
   Assert.That(ConfirmedRearm(sm,ref p,ref offSequence),Is.True);
   p.EnableHeld=false;p.TelemetryFresh=false;sm.Update(p);
   Assert.That(sm.ReleaseConfirmed,Is.False,"stale telemetry must not keep a confirmation alive");
   p.EnableHeld=true;Assert.That(sm.Update(p),Is.Not.EqualTo(PhantomState.Tracking));
  }

  [Test]public void StateMachine_LossIsFailClosedAndRequiresANewConfirmedRearm()
  {
   var sm=new PhantomStateMachine();var p=ReadyPredicates();ulong offSequence=0;
   Assert.That(ConfirmedRearm(sm,ref p,ref offSequence),Is.True);
   p.WristValid=false;Assert.That(sm.Update(p),Is.EqualTo(PhantomState.SafeHold));
   Assert.That(sm.Armed,Is.False);
   p.WristValid=true;p.EnableHeld=true;Assert.That(sm.Update(p),Is.EqualTo(PhantomState.SafeHold));
   Assert.That(ConfirmedRearm(sm,ref p,ref offSequence),Is.True);
  }

  [Test]public void StateMachine_LatchedFaultIsReportedAsStoppedNotAFaultState()
  {
   var sm=new PhantomStateMachine();var p=ReadyPredicates();
   p.Fault=true;
   // SYSTEM_ARCHITECTURE 4.3: FAULT is not a wire state; it is STOPPED plus a code.
   Assert.That(sm.Update(p),Is.EqualTo(PhantomState.Stopped));
   Assert.That(sm.FaultLatched,Is.True);
   Assert.That(sm.Armed,Is.False);
   p.Fault=false;p.LocalStop=true;
   Assert.That(sm.Update(p),Is.EqualTo(PhantomState.Stopped));
   Assert.That(sm.FaultLatched,Is.False);
  }
  [Test]public void EnableUsesNormativeAsymmetricHysteresisAndInvalidReleases(){var h=new EnableHysteresis();Assert.False(h.Update(.59f));Assert.True(h.Update(.60f));Assert.True(h.Update(.50f));Assert.False(h.Update(.45f));Assert.True(h.Update(.8f));Assert.False(h.Update(.8f,false));}
  [Test]public void StateCodesAreDerivedFromTheGeneratedWireEnum()
  {
   // Every value, compared against the generated enum rather than a literal, so a
   // schema renumbering cannot leave a stale hand-written copy behind.
   Assert.That((ushort)PhantomState.Boot,Is.EqualTo((ushort)WireV1.State.Boot));
   Assert.That((ushort)PhantomState.UserCalibration,Is.EqualTo((ushort)WireV1.State.UserCalibration));
   Assert.That((ushort)PhantomState.Discovery,Is.EqualTo((ushort)WireV1.State.Discovery));
   Assert.That((ushort)PhantomState.ConnectedUnreferenced,Is.EqualTo((ushort)WireV1.State.ConnectedUnreferenced));
   Assert.That((ushort)PhantomState.RobotCalibration,Is.EqualTo((ushort)WireV1.State.RobotCalibration));
   Assert.That((ushort)PhantomState.Ready,Is.EqualTo((ushort)WireV1.State.Ready));
   Assert.That((ushort)PhantomState.Hold,Is.EqualTo((ushort)WireV1.State.Hold));
   Assert.That((ushort)PhantomState.Tracking,Is.EqualTo((ushort)WireV1.State.Tracking));
   Assert.That((ushort)PhantomState.SafeHold,Is.EqualTo((ushort)WireV1.State.SafeHold));
   Assert.That((ushort)PhantomState.Stopped,Is.EqualTo((ushort)WireV1.State.Stopped));
   Assert.That((ushort)PhantomState.Commissioning,Is.EqualTo((ushort)WireV1.State.Commissioning));
   Assert.That(Enum.GetNames(typeof(PhantomState)).Length,Is.EqualTo(Enum.GetNames(typeof(WireV1.State)).Length),
    "product state set must not add a state the wire contract does not have");
   Assert.That((ushort)PhantomFault.ControllerProcess,Is.EqualTo((ushort)WireV1.Fault.FaultControllerProcess));
  }
  static byte[] Hex(string value){var bytes=new byte[value.Length/2];for(var i=0;i<bytes.Length;i++)bytes[i]=Convert.ToByte(value.Substring(i*2,2),16);return bytes;}static void WriteId(byte[] value,int offset,string text){var bytes=System.Text.Encoding.ASCII.GetBytes(text);Buffer.BlockCopy(bytes,0,value,offset,bytes.Length);}
 }
}
