using System;
using System.Collections.Generic;
using NUnit.Framework;
using Phantom.Calibration;
using Phantom.Kinematics;

namespace Phantom.Tests
{
    public sealed class CalibrationTests
    {
        [Test]
        public void RobustSphereFit_RejectsBentElbowInnerSamples()
        {
            var random=new Random(91);var center=new Vec3(0.12,1.33,-0.08);const double radius=0.62;var samples=new List<Vec3>();
            for(var i=0;i<600;i++){var a=2*Math.PI*random.NextDouble();var z=-0.8+1.6*random.NextDouble();var radial=Math.Sqrt(1-z*z);var noise=(random.NextDouble()-0.5)*0.006;samples.Add(center+(radius+noise)*new Vec3(radial*Math.Cos(a),radial*Math.Sin(a),z));}
            for(var i=0;i<80;i++){var a=2*Math.PI*random.NextDouble();samples.Add(center+0.48*new Vec3(Math.Cos(a),Math.Sin(a),0.1));}
            var result=new ShoulderSphereFit().Fit(samples);Assert.That(result.Quality.Valid,Is.True,result.Quality.FailureReason);Assert.That((result.Center-center).Magnitude,Is.LessThan(0.015));Assert.That(Math.Abs(result.Quality.ArmLengthMeters-radius),Is.LessThan(0.015));
        }

        [Test]
        public void SphereFit_RejectsInsufficientSamplesAndCoverage()
        {
            Assert.That(new ShoulderSphereFit().Fit(new List<Vec3>{Vec3.Zero}).Quality.FailureReason,Is.EqualTo("insufficient_samples"));
            var line=new List<Vec3>();for(var i=0;i<100;i++)line.Add(new Vec3(i*0.001,0,0));Assert.That(new ShoulderSphereFit().Fit(line).Quality.Valid,Is.False);
        }

        [Test]
        public void RuntimeShoulderUsesHeadTranslationNotRotation()
        {
            var calibration=new UserCalibration{ShoulderCenterRoom0=new Vec3(0,1.4,0),HeadRoomAtCalibration=new Vec3(0,1.7,0)};
            Assert.That(calibration.RuntimeShoulder(new Vec3(0.1,1.7,-0.2)),Is.EqualTo(new Vec3(0.1,1.4,-0.2)));
        }
    }
}
