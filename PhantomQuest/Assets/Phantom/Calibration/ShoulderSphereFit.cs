using System;
using System.Collections.Generic;
using Phantom.Kinematics;

namespace Phantom.Calibration
{
    [Serializable]
    public struct CalibrationQuality
    {
        public bool Valid;
        public int AcceptedSamples;
        public double ArmLengthMeters;
        public double RmsResidualMeters;
        public double P95ResidualMeters;
        public double AngularCoverage;
        public string FailureReason;
    }

    public struct ShoulderFitResult
    {
        public Vec3 Center;
        public CalibrationQuality Quality;
    }

    public sealed class ShoulderSphereFit
    {
        public ShoulderFitResult Fit(IReadOnlyList<Vec3> samples, double huberDelta = 0.015)
        {
            var valid = new List<Vec3>();
            if (samples != null)
                for (var i = 0; i < samples.Count; ++i) if (samples[i].IsFinite) valid.Add(samples[i]);
            if (valid.Count < 20) return Failure(valid.Count, "insufficient_samples");

            var weights = new double[valid.Count];
            for (var i = 0; i < weights.Length; ++i) weights[i] = 1;
            Vec3 center = Vec3.Zero;
            double radius = 0;
            for (var iteration = 0; iteration < 12; ++iteration)
            {
                if (!SolveWeightedSphere(valid, weights, out center, out radius)) return Failure(valid.Count, "degenerate_fit");
                var distances = new double[valid.Count];
                for (var i = 0; i < valid.Count; ++i) distances[i] = (valid[i] - center).Magnitude;
                var outerReference = Percentile(distances, 0.75);
                for (var i = 0; i < valid.Count; ++i)
                {
                    var residual = distances[i] - radius;
                    var abs = Math.Abs(residual);
                    var huber = abs <= huberDelta ? 1.0 : huberDelta / abs;
                    var innerPenalty = distances[i] < outerReference - 0.04 ? 0.15 : 1.0;
                    weights[i] = huber * innerPenalty;
                }
            }

            var residuals = new double[valid.Count];
            double sumSq = 0;
            for (var i = 0; i < valid.Count; ++i) { residuals[i] = Math.Abs((valid[i] - center).Magnitude - radius); sumSq += residuals[i] * residuals[i]; }
            var coverage = Coverage(valid, center);
            var quality = new CalibrationQuality
            {
                Valid = radius >= 0.35 && radius <= 0.95 && coverage >= 0.12,
                AcceptedSamples = valid.Count,
                ArmLengthMeters = radius,
                RmsResidualMeters = Math.Sqrt(sumSq / valid.Count),
                P95ResidualMeters = Percentile(residuals, 0.95),
                AngularCoverage = coverage,
                FailureReason = ""
            };
            if (radius < 0.35 || radius > 0.95) quality.FailureReason = "implausible_arm_length_provisional";
            else if (coverage < 0.12) quality.FailureReason = "insufficient_3d_coverage_provisional";
            return new ShoulderFitResult { Center = center, Quality = quality };
        }

        static ShoulderFitResult Failure(int count, string reason) => new ShoulderFitResult { Quality = new CalibrationQuality { Valid = false, AcceptedSamples = count, FailureReason = reason } };

        static bool SolveWeightedSphere(List<Vec3> points, double[] weights, out Vec3 center, out double radius)
        {
            var normal = new double[4, 5];
            for (var i = 0; i < points.Count; ++i)
            {
                var p = points[i]; var row = new[] { 2 * p.X, 2 * p.Y, 2 * p.Z, 1.0 }; var b = p.SqrMagnitude; var w = weights[i];
                for (var r = 0; r < 4; ++r) { for (var c = 0; c < 4; ++c) normal[r, c] += w * row[r] * row[c]; normal[r, 4] += w * row[r] * b; }
            }
            for (var pivot = 0; pivot < 4; ++pivot)
            {
                var best = pivot; for (var r = pivot + 1; r < 4; ++r) if (Math.Abs(normal[r, pivot]) > Math.Abs(normal[best, pivot])) best = r;
                if (Math.Abs(normal[best, pivot]) < 1e-12) { center = Vec3.Zero; radius = 0; return false; }
                if (best != pivot) for (var c = pivot; c < 5; ++c) { var t = normal[pivot, c]; normal[pivot, c] = normal[best, c]; normal[best, c] = t; }
                var divisor = normal[pivot, pivot]; for (var c = pivot; c < 5; ++c) normal[pivot, c] /= divisor;
                for (var r = 0; r < 4; ++r) if (r != pivot) { var factor = normal[r, pivot]; for (var c = pivot; c < 5; ++c) normal[r, c] -= factor * normal[pivot, c]; }
            }
            center = new Vec3(normal[0, 4], normal[1, 4], normal[2, 4]);
            radius = Math.Sqrt(Math.Max(0, center.SqrMagnitude + normal[3, 4]));
            return center.IsFinite && Vec3.IsFiniteNumber(radius);
        }

        static double Coverage(List<Vec3> points, Vec3 center)
        {
            double xx = 0, yy = 0, zz = 0, xy = 0, xz = 0, yz = 0;
            foreach (var point in points) { var u = (point - center).Normalized; xx += u.X*u.X; yy += u.Y*u.Y; zz += u.Z*u.Z; xy += u.X*u.Y; xz += u.X*u.Z; yz += u.Y*u.Z; }
            var n = points.Count; xx/=n; yy/=n; zz/=n; xy/=n; xz/=n; yz/=n;
            var determinant = xx*(yy*zz-yz*yz)-xy*(xy*zz-yz*xz)+xz*(xy*yz-yy*xz);
            return Math.Max(0, Math.Min(1, 27 * determinant));
        }

        static double Percentile(double[] values, double fraction)
        {
            var copy = (double[])values.Clone(); Array.Sort(copy);
            var index = Math.Max(0, Math.Min(copy.Length - 1, (int)Math.Ceiling(fraction * copy.Length) - 1));
            return copy[index];
        }
    }

    [Serializable]
    public struct UserCalibration
    {
        public Vec3 ShoulderCenterRoom0;
        public double ArmLengthWristMeters;
        public Vec3 HeadRoomAtCalibration;
        public CalibrationQuality Quality;
        public Vec3 RuntimeShoulder(Vec3 currentHeadRoom) => ShoulderCenterRoom0 + (currentHeadRoom - HeadRoomAtCalibration);
    }
}
