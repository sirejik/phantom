using System;
using System.Collections.Generic;
using Phantom.Calibration;
using Phantom.Kinematics;
using Phantom.Mapping;
using Phantom.Networking;

internal static class CoreSmoke
{
    static void Check(bool condition,string message){if(!condition)throw new Exception(message);}
    public static int Main()
    {
        var random=new Random(7341);var fk=new PhantomForwardKinematics();var ik=new PhantomInverseKinematics(1,0.001);
        var checkedPoints=0;for(var i=0;i<10000;i++){var q=new JointAngles(-2.5+5*random.NextDouble(),-1+2*random.NextDouble(),0.05+2.7*random.NextDouble());var p=fk.Solve(q,.21,.22);if(Math.Sqrt(p.X*p.X+p.Y*p.Y)<.001)continue;var solved=ik.Solve(p,.21,.22);Check(solved.Success&&((solved.SolvedTarget-p).Magnitude<1e-9),$"IK/FK round trip i={i} status={solved.Status} p={p} error={(solved.SolvedTarget-p).Magnitude}");checkedPoints++;}Check(checkedPoints>9900,"random coverage");
        var mapper=new HumanToRobotMapper(.32);var start=new Vec3(.3,0,.1);Check(mapper.Engage(new Vec3(.6,0,0),Vec3.Zero,.6,start),"engage");Vec3 target=default;
        for(var i=0;i<=100000;i++){var phase=2*Math.PI*i/100000;Check(mapper.TryMap(new Vec3(.6,.05*Math.Sin(phase),.03*Math.Sin(2*phase)),Vec3.Zero,.6,out target),"mapping");}
        Check((target-start).Magnitude<1e-12,"absolute mapping drift");
        var bytes=ProtocolCodec.EncodeTarget(new TargetPacket{Flags=CommandFlags.Tracking,SessionId=0x0102030405060708,Sequence=0x0a0b0c0d,ClientTimeUs=0x1112131415161718,Target=new JointAngles(1,-2,.5),GripIntent=.25f});
        Check(BitConverter.ToString(bytes).Replace("-","").ToLowerInvariant()=="50484e540100020008070605040302010d0c0b0a18171615141312110000803f000000c00000003f0000803e6230dfde","protocol golden vector");
        var samples=new List<Vec3>();var center=new Vec3(.12,1.33,-.08);for(var i=0;i<600;i++){var a=2*Math.PI*random.NextDouble();var z=-.8+1.6*random.NextDouble();var r=Math.Sqrt(1-z*z);samples.Add(center+.62*new Vec3(r*Math.Cos(a),r*Math.Sin(a),z));}var fit=new ShoulderSphereFit().Fit(samples);Check(fit.Quality.Valid&&(fit.Center-center).Magnitude<.01,"sphere fit");
        var sm=new PhantomStateMachine();var ready=new SafetyPredicates{AppFocused=true,RightHandValid=true,LeftControllerValid=true,RoomValid=true,RobotGeometryValid=true,UserCalibrationValid=true,NetworkReady=true};Check(sm.Update(ready)==PhantomState.ArmedHold,"armed hold");ready.EnableHeld=true;Check(sm.Update(ready)==PhantomState.Tracking,"tracking");ready.RightHandValid=false;Check(sm.Update(ready)==PhantomState.SafeHold,"safe hold");ready.RightHandValid=true;Check(sm.Update(ready)==PhantomState.SafeHold,"no auto resume");
        Console.WriteLine("PASS: 10k IK/FK, 100001-frame drift, protocol golden vector, sphere fit, safety recovery latch");return 0;
    }
}
