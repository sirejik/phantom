using System;
using System.Collections.Generic;
using Phantom.Kinematics;

namespace Phantom.RobotLocalization
{
    public struct RobotCalibrationQuality
    {
        public int SampleCount; public double WindowSeconds; public double MaxPositionStdMeters; public bool Valid; public string Reason;
    }

    public sealed class RobotCalibrationSession
    {
        readonly double _requiredWindowSeconds; readonly Dictionary<RobotMarkerId,List<Vec3>> _samples=new Dictionary<RobotMarkerId,List<Vec3>>();
        double _start=-1; RobotBaseFrame _latestBase;
        public RobotCalibrationQuality Quality{get;private set;}
        public RobotCalibrationSession(double requiredWindowSeconds=1.0){_requiredWindowSeconds=requiredWindowSeconds;foreach(RobotMarkerId id in Enum.GetValues(typeof(RobotMarkerId)))_samples[id]=new List<Vec3>();}
        public void Reset(){foreach(var list in _samples.Values)list.Clear();_start=-1;Quality=default;}
        public void Add(double monotonicSeconds,RobotMarkerSnapshot snapshot)
        {
            if(snapshot==null||!snapshot.HasAllTenPoses||!snapshot.BaseFrame.IsValid){Reset();return;}if(_start<0)_start=monotonicSeconds;_latestBase=snapshot.BaseFrame;
            foreach(var pair in snapshot.Positions)if(pair.Value.IsFinite)_samples[pair.Key].Add(pair.Value);
            Quality=new RobotCalibrationQuality{SampleCount=_samples[RobotMarkerId.ShoulderLeft].Count,WindowSeconds=monotonicSeconds-_start,Reason="collecting"};
        }
        public bool TryFinish(double monotonicSeconds,out RobotGeometry geometry)
        {
            geometry=default;if(_start<0||monotonicSeconds-_start<_requiredWindowSeconds||_samples[RobotMarkerId.ShoulderLeft].Count<30)return false;
            var means=new Dictionary<RobotMarkerId,Vec3>();double maxStd=0;
            foreach(var pair in _samples)
            {
                var mean=RobustMean(pair.Value);means[pair.Key]=mean;double sum=0;var accepted=0;
                foreach(var p in pair.Value){var d=(p-mean).Magnitude;if(d>.03)continue;sum+=d*d;accepted++;}
                if(accepted<20){Quality=new RobotCalibrationQuality{SampleCount=accepted,WindowSeconds=monotonicSeconds-_start,Valid=false,Reason="marker_outliers"};return false;}
                maxStd=Math.Max(maxStd,Math.Sqrt(sum/accepted));
            }
            geometry=new RobotGeometryEstimator().Estimate(means,_latestBase);var valid=geometry.Valid&&maxStd<=.01;
            Quality=new RobotCalibrationQuality{SampleCount=_samples[RobotMarkerId.ShoulderLeft].Count,WindowSeconds=monotonicSeconds-_start,MaxPositionStdMeters=maxStd,Valid=valid,Reason=valid?"locked":"pose_variance_or_geometry"};
            if(!valid)geometry.Valid=false;return valid;
        }
        static Vec3 RobustMean(List<Vec3> values)
        {
            var xs=new double[values.Count];var ys=new double[values.Count];var zs=new double[values.Count];for(var i=0;i<values.Count;i++){xs[i]=values[i].X;ys[i]=values[i].Y;zs[i]=values[i].Z;}Array.Sort(xs);Array.Sort(ys);Array.Sort(zs);var median=new Vec3(xs[xs.Length/2],ys[ys.Length/2],zs[zs.Length/2]);var sum=Vec3.Zero;var n=0;foreach(var p in values)if((p-median).Magnitude<=.03){sum+=p;n++;}return n>0?sum/n:median;
        }
    }
}
