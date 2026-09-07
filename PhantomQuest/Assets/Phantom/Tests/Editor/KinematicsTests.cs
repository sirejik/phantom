using System;
using NUnit.Framework;
using Phantom.Kinematics;
using Phantom.Mapping;
using Phantom.Workspace;

namespace Phantom.Tests
{
    public sealed class KinematicsTests
    {
    // Synthetic mapping profile for pure-logic tests. Real values are MEASURED
    // parameters from RobotGeometry / quest human_mapping and are unresolved.
    static MappingProfile TestProfile(double reach,double scale=4.0)=>new MappingProfile{RobotNominalReachM=reach,MaxMappingScale=scale,HumanVectorMinM=.05};

        [Test]
        public void IkFk_RoundTripsRandomReachablePoints()
        {
            var random=new Random(7341);var fk=new PhantomForwardKinematics();var ik=new PhantomInverseKinematics(0.001);
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
            var ik=new PhantomInverseKinematics(0.05);
            Assert.That(ik.Solve(new Vec3(0.01,0,0.2),0.2,0.2).Status,Is.EqualTo(IkStatus.NearAxis));
            Assert.That(ik.Solve(new Vec3(1,0,0),0.2,0.2).Status,Is.EqualTo(IkStatus.Unreachable));
            Assert.That(ik.Solve(new Vec3(double.NaN,0,0),0.2,0.2).Status,Is.EqualTo(IkStatus.Invalid));
        }

        [Test]
        public void CoordinateAdapter_DoesNotMirrorYaw()
        {
            var basis=Tracking.XrSpaceBridge.FromShoulderPair(new Vec3(0,1,1),new Vec3(0,1,-1));
            Assert.That(basis.ZFloor,Is.EqualTo(new Vec3(0,1,0)));Assert.That(Vec3.Dot(Vec3.Cross(basis.XFloor,basis.YFloor),basis.ZFloor),Is.EqualTo(1).Within(1e-12));
        }

        [Test]
        public void Workspace_ProjectsOuterAndNearYaw()
        {
            var projector=new WorkspaceProjector(WorkspaceConfig.UnqualifiedTestFixture);
            var outer=projector.Project(new Vec3(1,0,0.1));Assert.That(outer.Projected.Magnitude,Is.LessThanOrEqualTo(0.4300001));
            var axis=projector.Project(new Vec3(0,0,0.2));Assert.That(Math.Sqrt(axis.Projected.X*axis.Projected.X+axis.Projected.Y*axis.Projected.Y),Is.GreaterThanOrEqualTo(0.049999));
        }

        [Test]
        public void AbsoluteMapping_HasNoCumulativeDriftOverOneHundredThousandFrames()
        {
            var mapper=new HumanToRobotMapper(TestProfile(.35));var input=new Vec3(.6,.1,.2);Assert.True(mapper.TryMapVector(input,.65,out var first));for(var i=0;i<100000;i++)Assert.True(mapper.TryMapVector(input,.65,out _));Assert.True(mapper.TryMapVector(input,.65,out var last));Assert.That((last-first).Magnitude,Is.LessThan(1e-12));
        }

        [Test]
        public void MappingDoesNotUsePhysicalPoseOrEngagementAnchor()
        {
            var mapper=new HumanToRobotMapper(TestProfile(.3));Assert.True(mapper.TryMapVector(new Vec3(.5,0,0),.5,out var target));Assert.That(target,Is.EqualTo(new Vec3(.3,0,0)));Assert.False(mapper.TryMapVector(new Vec3(.001,0,0),.5,out _));
        }
    }
}
