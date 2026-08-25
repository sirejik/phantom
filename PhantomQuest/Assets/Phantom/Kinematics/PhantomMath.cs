using System;

namespace Phantom.Kinematics
{
    [Serializable]
    public struct Vec3 : IEquatable<Vec3>
    {
        public double X;
        public double Y;
        public double Z;

        public Vec3(double x, double y, double z) { X = x; Y = y; Z = z; }
        public static Vec3 Zero => new Vec3(0, 0, 0);
        public double SqrMagnitude => X * X + Y * Y + Z * Z;
        public double Magnitude => Math.Sqrt(SqrMagnitude);
        public bool IsFinite => IsFiniteNumber(X) && IsFiniteNumber(Y) && IsFiniteNumber(Z);
        public Vec3 Normalized => Magnitude > 1e-12 ? this / Magnitude : Zero;
        public static bool IsFiniteNumber(double value) => !double.IsNaN(value) && !double.IsInfinity(value);
        public static double Dot(Vec3 a, Vec3 b) => a.X * b.X + a.Y * b.Y + a.Z * b.Z;
        public static Vec3 Cross(Vec3 a, Vec3 b) => new Vec3(a.Y * b.Z - a.Z * b.Y, a.Z * b.X - a.X * b.Z, a.X * b.Y - a.Y * b.X);
        public static Vec3 operator +(Vec3 a, Vec3 b) => new Vec3(a.X + b.X, a.Y + b.Y, a.Z + b.Z);
        public static Vec3 operator -(Vec3 a, Vec3 b) => new Vec3(a.X - b.X, a.Y - b.Y, a.Z - b.Z);
        public static Vec3 operator -(Vec3 value) => new Vec3(-value.X, -value.Y, -value.Z);
        public static Vec3 operator *(Vec3 value, double scale) => new Vec3(value.X * scale, value.Y * scale, value.Z * scale);
        public static Vec3 operator *(double scale, Vec3 value) => value * scale;
        public static Vec3 operator /(Vec3 value, double scale) => value * (1.0 / scale);
        public bool Equals(Vec3 other) => X.Equals(other.X) && Y.Equals(other.Y) && Z.Equals(other.Z);
        public override bool Equals(object obj) => obj is Vec3 other && Equals(other);
        public override int GetHashCode() => X.GetHashCode() ^ (Y.GetHashCode() << 1) ^ (Z.GetHashCode() << 2);
        public override string ToString() => $"({X:F5}, {Y:F5}, {Z:F5})";
    }

    [Serializable]
    public struct JointAngles
    {
        public double Base;
        public double Shoulder;
        public double Elbow;
        public JointAngles(double qBase, double qShoulder, double qElbow) { Base = qBase; Shoulder = qShoulder; Elbow = qElbow; }
        public bool IsFinite => Vec3.IsFiniteNumber(Base) && Vec3.IsFiniteNumber(Shoulder) && Vec3.IsFiniteNumber(Elbow);
    }

    [Serializable]
    public struct JointLimits
    {
        public JointAngles Min;
        public JointAngles Max;
        public JointLimits(JointAngles min, JointAngles max) { Min = min; Max = max; }
        public JointAngles Clamp(JointAngles q) => new JointAngles(
            Math.Max(Min.Base, Math.Min(Max.Base, q.Base)),
            Math.Max(Min.Shoulder, Math.Min(Max.Shoulder, q.Shoulder)),
            Math.Max(Min.Elbow, Math.Min(Max.Elbow, q.Elbow)));
        public bool Contains(JointAngles q) => q.IsFinite && q.Base >= Min.Base && q.Base <= Max.Base && q.Shoulder >= Min.Shoulder && q.Shoulder <= Max.Shoulder && q.Elbow >= Min.Elbow && q.Elbow <= Max.Elbow;
    }
}
