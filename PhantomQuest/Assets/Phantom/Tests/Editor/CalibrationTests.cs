using NUnit.Framework;using Phantom.Calibration;using Phantom.Kinematics;using Phantom.RobotLocalization;
namespace Phantom.Tests
{
 public sealed class CalibrationTests
 {
  [Test]public void ArmReach_UsesExactlyThreeStableShoulderWristPoses(){var c=new ArmReachCalibration();for(var pose=0;pose<3;pose++)for(var i=0;i<30;i++)Assert.True(c.Add(pose,Vec3.Zero,new Vec3(.600+(i%3-1)*.001,0,0)));var r=c.Finish();Assert.True(r.Valid,r.Reason);Assert.That(r.ValidSamples,Is.EqualTo(90));Assert.That(r.ArmReachMeters,Is.EqualTo(.600).Within(.002));}
  [Test]public void ArmReach_RejectsMissingOrInconsistentPose(){var c=new ArmReachCalibration();for(var pose=0;pose<3;pose++)for(var i=0;i<30;i++)c.Add(pose,Vec3.Zero,new Vec3(.5+pose*.03,0,0));Assert.False(c.Finish().Valid);}
  [Test]public void SyntheticTenQrPose_ProducesStableGeometry()
  {
   var snapshot=TenQrPose();var session=new RobotCalibrationSession();for(var i=0;i<31;i++)session.Add(i/30.0,snapshot);
   Assert.True(session.TryFinish(1.01,out var geometry),session.Quality.Reason);Assert.That(geometry.L1,Is.EqualTo(.20).Within(1e-6));Assert.That(geometry.L2,Is.EqualTo(.18).Within(1e-6));Assert.That(geometry.TurretYawRad,Is.Zero.Within(1e-9));
  }
  [Test]public void GripperPairDefinesForearmIndependentlyOfJawOpening()
  {
   var closed=TenQrPose();var open=TenQrPose();open.Positions[RobotMarkerId.JawLeft]=new Vec3(.42,.04,0);open.Positions[RobotMarkerId.JawRight]=new Vec3(.42,-.04,0);
   var estimator=new RobotGeometryEstimator();var a=estimator.Estimate(closed.Positions,closed.BaseFrame);var b=estimator.Estimate(open.Positions,open.BaseFrame);
   Assert.True(a.Valid&&b.Valid);Assert.That((a.GripperRoom-b.GripperRoom).Magnitude,Is.Zero.Within(1e-12));Assert.That(a.L2,Is.EqualTo(b.L2).Within(1e-12));
  }
  [Test]public void TurretPairDefinesBaseYawIndependentlyOfArmLinks()
  {
   var snapshot=TenQrPose();snapshot.Positions[RobotMarkerId.TurretLeft]=new Vec3(-.05,0,-.03);snapshot.Positions[RobotMarkerId.TurretRight]=new Vec3(.05,0,-.03);
   var geometry=new RobotGeometryEstimator().Estimate(snapshot.Positions,snapshot.BaseFrame);Assert.True(geometry.Valid);Assert.That(geometry.TurretYawRad,Is.EqualTo(System.Math.PI/2).Within(1e-9));
  }
  [Test]public void TenQrCaptureRequiresFullPoseForEveryMarker(){var snapshot=TenQrPose();snapshot.Rotations.Remove(RobotMarkerId.JawLeft);Assert.False(snapshot.HasAllTenPoses);}
  static RobotMarkerSnapshot TenQrPose()
  {
   var snapshot=new RobotMarkerSnapshot{BaseFrame=new RobotBaseFrame{OriginRoom=Vec3.Zero,ForwardRoom=new Vec3(1,0,0),LeftRoom=new Vec3(0,1,0),UpRoom=new Vec3(0,0,1)}};
   snapshot.Positions[RobotMarkerId.ShoulderLeft]=new Vec3(0,.05,0);snapshot.Positions[RobotMarkerId.ShoulderRight]=new Vec3(0,-.05,0);
   snapshot.Positions[RobotMarkerId.TurretLeft]=new Vec3(.03,.05,-.03);snapshot.Positions[RobotMarkerId.TurretRight]=new Vec3(.03,-.05,-.03);
   snapshot.Positions[RobotMarkerId.ElbowLeft]=new Vec3(.20,.04,0);snapshot.Positions[RobotMarkerId.ElbowRight]=new Vec3(.20,-.04,0);
   snapshot.Positions[RobotMarkerId.GripperLeft]=new Vec3(.38,.035,0);snapshot.Positions[RobotMarkerId.GripperRight]=new Vec3(.38,-.035,0);
   snapshot.Positions[RobotMarkerId.JawLeft]=new Vec3(.42,.02,0);snapshot.Positions[RobotMarkerId.JawRight]=new Vec3(.42,-.02,0);
   foreach(RobotMarkerId id in System.Enum.GetValues(typeof(RobotMarkerId)))snapshot.Rotations[id]=MarkerRotation.Identity;return snapshot;
  }
 }
}
