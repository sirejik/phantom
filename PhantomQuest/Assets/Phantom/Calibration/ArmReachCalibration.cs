using System;using System.Collections.Generic;using Phantom.Kinematics;
namespace Phantom.Calibration
{
    [Serializable]public struct ArmReachResult{public bool Valid;public double ArmReachMeters,SpreadMeters;public int ValidSamples;public string Reason;}
    public sealed class ArmReachCalibration
    {
        readonly List<double>[] _poses={new List<double>(),new List<double>(),new List<double>()};
        public bool Add(int pose,Vec3 shoulder,Vec3 wrist){if(pose<0||pose>=3||!shoulder.IsFinite||!wrist.IsFinite)return false;var d=(wrist-shoulder).Magnitude;if(!Vec3.IsFiniteNumber(d)||d<=0)return false;_poses[pose].Add(d);return true;}
        public ArmReachResult Finish(){var medians=new double[3];var total=0;for(var i=0;i<3;i++){if(_poses[i].Count<30)return new ArmReachResult{Reason="insufficient_pose_samples",ValidSamples=total};_poses[i].Sort();medians[i]=Median(_poses[i]);total+=_poses[i].Count;if(Percentile(_poses[i],.95)-Percentile(_poses[i],.05)>.020)return new ArmReachResult{Reason="pose_spread",ValidSamples=total};}Array.Sort(medians);var spread=medians[2]-medians[0];return new ArmReachResult{Valid=spread<=.030,ArmReachMeters=medians[1],SpreadMeters=spread,ValidSamples=total,Reason=spread<=.030?"ok":"between_pose_spread"};}
        static double Median(List<double>x)=>Percentile(x,.5);static double Percentile(List<double>x,double p){var index=p*(x.Count-1);var lo=(int)Math.Floor(index);var hi=(int)Math.Ceiling(index);return x[lo]+(x[hi]-x[lo])*(index-lo);}
    }
}
