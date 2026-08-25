using System;
using NUnit.Framework;
using Phantom.Kinematics;
using Phantom.Mapping;
using Phantom.Workspace;

namespace Phantom.Tests
{
    public sealed class KinematicsTests
    {
        [Test]
        public void IkFk_RoundTripsRandomReachablePoints()
        {
            var random=new Random(7341);var fk=new PhantomForwardKinematics();var ik=new PhantomInverseKinematics(1,0.001);
            for(var i=0;i<10000;i++)
            {
                var source=new JointAngles(-2.5+5*random.NextDouble(),-1+2*random.NextDouble(),0.05+2.8*random.NextDouble());
                var xyz=fk.Solve(source,0.21,0.22);if(Math.Sqrt(xyz.X*xyz.X+xyz.Y*xyz.Y)<0.001)continue;var result=ik.Solve(xyz,0.21,0.22);
                Assert.That(result.Success,Is.True);Assert.That((result.SolvedTarget-xyz).Magnitude,Is.LessThan(1e-9));Assert.That(result.Angles.Elbow,Is.GreaterThanOrEqualTo(0));
            }
        }

        [Test]
        public void Ik_RejectsNearAxisUnreachableAndNonFinite()
        {
            var ik=new PhantomInverseKinematics(1,0.05);
            Assert.That(ik.Solve(new Vec3(0.01,0,0.2),0.2,0.2).Status,Is.EqualTo(IkStatus.NearAxis));
            Assert.That(ik.Solve(new Vec3(1,0,0),0.2,0.2).Status,Is.EqualTo(IkStatus.Unreachable));
            Assert.That(ik.Solve(new Vec3(double.NaN,0,0),0.2,0.2).Status,Is.EqualTo(IkStatus.Invalid));
        }

        [Test]
        public void CoordinateAdapter_DoesNotMirrorYaw()
        {
            var forward=Tracking.MetaQuestTrackingSource.UnityToCanonical(new UnityEngine.Vector3(0,0,1));
            var unityRight=Tracking.MetaQuestTrackingSource.UnityToCanonical(new UnityEngine.Vector3(1,0,0));
            Assert.That(forward.X,Is.EqualTo(1));Assert.That(unityRight.Y,Is.EqualTo(-1));
            Assert.That(Vec3.Cross(new Vec3(1,0,0),new Vec3(0,1,0)).Z,Is.EqualTo(1));
        }

        [Test]
        public void Workspace_ProjectsOuterAndNearYaw()
        {
            var projector=new WorkspaceProjector(WorkspaceConfig.Default);
            var outer=projector.Project(new Vec3(1,0,0.1));Assert.That(outer.Projected.Magnitude,Is.LessThanOrEqualTo(0.4300001));
            var axis=projector.Project(new Vec3(0,0,0.2));Assert.That(Math.Sqrt(axis.Projected.X*axis.Projected.X+axis.Projected.Y*axis.Projected.Y),Is.GreaterThanOrEqualTo(0.049999));
        }

        [Test]
        public void AbsoluteMapping_HasNoCumulativeDriftOverOneHundredThousandFrames()
        {
            var mapper=new HumanToRobotMapper(0.32);var shoulder=Vec3.Zero;var wrist0=new Vec3(0.6,0,0);var robot0=new Vec3(0.3,0,0.1);
            Assert.That(mapper.Engage(wrist0,shoulder,0.6,robot0),Is.True);Vec3 target=Vec3.Zero;
            for(var i=0;i<=100000;i++){var phase=2*Math.PI*i/100000;var wrist=wrist0+new Vec3(0,0.05*Math.Sin(phase),0.03*Math.Sin(2*phase));Assert.That(mapper.TryMap(wrist,shoulder,0.6,out target),Is.True);}
            Assert.That((target-robot0).Magnitude,Is.LessThan(1e-12));
        }

        [Test]
        public void ReengageStartsAtCurrentTcpWithoutJump()
        {
            var mapper=new HumanToRobotMapper(0.3);mapper.Engage(new Vec3(0.5,0,0),Vec3.Zero,0.5,new Vec3(0.2,0,0));mapper.TryMap(new Vec3(0.5,0.1,0),Vec3.Zero,0.5,out var moved);
            mapper.Release();Assert.That(mapper.Engage(new Vec3(0.4,-0.1,0.1),Vec3.Zero,0.5,moved),Is.True);mapper.TryMap(new Vec3(0.4,-0.1,0.1),Vec3.Zero,0.5,out var reengaged);
            Assert.That((reengaged-moved).Magnitude,Is.LessThan(1e-12));
        }
    }
}
