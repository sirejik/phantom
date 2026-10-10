using System;using System.Linq;using Phantom.Calibration;using Phantom.Diagnostics;using Phantom.Kinematics;using Phantom.Mapping;using Phantom.Networking;using Phantom.Networking.Generated;
internal static class CoreSmoke
{
 static void Check(bool c,string m){if(!c)throw new Exception(m);}static byte[] Id(byte s){var b=new byte[16];for(var i=0;i<16;i++)b[i]=(byte)(s+i);return b;}static byte[] Key(){var b=new byte[32];for(var i=0;i<32;i++)b[i]=(byte)i;return b;}
 public static int Run(){var random=new Random(7341);var fk=new PhantomForwardKinematics();var ik=new PhantomInverseKinematics(.001);for(var i=0;i<10000;i++){var q=new JointAngles(-2.5+5*random.NextDouble(),-1+2*random.NextDouble(),.05+2.7*random.NextDouble());var p=fk.Solve(q,.21,.22);if(Math.Sqrt(p.X*p.X+p.Y*p.Y)<.001)continue;var solved=ik.Solve(p,.21,.22);Check(solved.Success&&(solved.SolvedTarget-p).Magnitude<1e-9,"IK/FK");}
  var mapper=new HumanToRobotMapper(new MappingProfile{RobotNominalReachM=.35,MaxMappingScale=4.0,HumanVectorMinM=.05});var input=new Vec3(.6,.1,.2);Check(mapper.TryMapVector(input,.65,out var first),"mapping");for(var i=0;i<100000;i++)Check(mapper.TryMapVector(input,.65,out _),"mapping");Check(mapper.TryMapVector(input,.65,out var last)&&(last-first).Magnitude<1e-12,"mapping drift");
  var payload=ProtocolCodec.EncodeCommand(new CommandPayload{Flags=MotionFlags.MotionEnable|MotionFlags.TrackingValid,Target=new JointAngles(1,-2,.5),GripIntent=.25f});var packet=ProtocolCodec.Encode(WireV1.MessageType.Command,payload,Key(),Id(16),Id(32),1,99);Check(ProtocolCodec.TryDecode(packet,Key(),out var decoded)&&ProtocolCodec.TryDecodeCommand(decoded.Payload,out _),"HMAC protocol");packet[70]^=1;Check(!ProtocolCodec.TryDecode(packet,Key(),out _),"HMAC corruption");
  var cal=new ArmReachCalibration();for(var p=0;p<3;p++)for(var i=0;i<30;i++)cal.Add(p,Vec3.Zero,new Vec3(.6+(i%3-1)*.001,0,0));Check(cal.Finish().Valid,"arm reach");var sm=new PhantomStateMachine();var ready=new SafetyPredicates{AppFocused=true,XrReady=true,WristValid=true,ShoulderValid=true,LeftControllerValid=true,UserCalibrationValid=true,NetworkDiscovered=true,Connected=true,RobotReferenceValid=true};
  // SAFETY S9: local grip release alone never arms. The client sends the canonical
  // OFF/HOLD and waits for EV3 to confirm acceptance through fresh telemetry.
  Check(sm.Update(ready)==PhantomState.Ready,"ready");Check(!sm.Armed,"armed without EV3-confirmed release");
  sm.NoteReleaseCommandSent(7);ready.TelemetryFresh=true;ready.LastAcceptedCommandSequence=6;
  Check(sm.Update(ready)==PhantomState.Hold&&!sm.Armed,"armed before EV3 accepted the release sequence");
  ready.EnableHeld=true;Check(sm.Update(ready)!=PhantomState.Tracking,"unconfirmed release allowed tracking");
  ready.EnableHeld=false;ready.LastAcceptedCommandSequence=7;
  Check(sm.Update(ready)==PhantomState.Hold&&sm.Armed,"confirmed release did not arm");
  ready.EnableHeld=true;Check(sm.Update(ready)==PhantomState.Tracking,"tracking");
  ready.WristValid=false;Check(sm.Update(ready)==PhantomState.SafeHold,"safe hold");Check(!sm.Armed,"SAFE_HOLD left the client armed");
  Check((ushort)PhantomState.Tracking==(ushort)WireV1.State.Tracking&&(ushort)PhantomState.Stopped==(ushort)WireV1.State.Stopped,"product state codes must derive from the wire enum");
  var mappingProfile=new MappingProfile{RobotNominalReachM=.40,MaxMappingScale=1.5,HumanVectorMinM=.05};
  var ceiling=new HumanToRobotMapper(mappingProfile).Map(new Vec3(.5,0,0),.20);
  Check(ceiling.Success&&Math.Abs(ceiling.MappingReachM-.30)<1e-12,"max_mapping_scale ceiling not applied");
  var unqualified=new HumanToRobotMapper(new MappingProfile{RobotNominalReachM=.40,HumanVectorMinM=.05}).Map(new Vec3(.5,0,0),.65);
  Check(unqualified.Status==MappingStatus.ProfileUnqualified,"unmeasured mapping profile produced a target");
  var inactive=new BodyProviderProbe{ApiPresent=true,ComponentPresent=true,UpperBodyConfigured=true,RightShoulderInJointSet=true};Check(BodyProviderClassifier.Classify(inactive).SoftwareCompatible,"inactive HMD classified incompatible");inactive.ExplicitMultimodalConflict=true;Check(!BodyProviderClassifier.Classify(inactive).SoftwareCompatible,"explicit provider conflict accepted");var synthetic=QuestSyntheticQualification.Run();Check(synthetic.All(x=>x.passed),"synthetic Quest qualification");
  foreach(var edge in new byte[]{9,10,13,32}){var raw=Key();raw[0]=edge;raw[31]=edge;Check(AndroidPrivateControlCredentialStore.DecodeKeyMaterial(raw).SequenceEqual(raw),"binary credential whitespace changed");}
  Check(AndroidPrivateControlCredentialStore.DecodeKeyMaterial(new byte[]{32})==null,"short credential accepted");
  var hex=System.Text.Encoding.ASCII.GetBytes(string.Concat(Key().Select(x=>x.ToString("x2"))));Check(AndroidPrivateControlCredentialStore.DecodeKeyMaterial(hex).SequenceEqual(Key()),"hex credential decode");
  Console.WriteLine("PASS: IK/FK, pure mapping, HMAC wire v1, calibration, re-arm, provider classification, credentials, Quest synthetic suite");return 0;}
}
