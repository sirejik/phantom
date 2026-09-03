# EV3 legacy platform risk record

ev3dev Stretch and its ARMv5/armel userspace are EOL. The control core is
isolated from sysfs by `MotorBackend`, SSH automation uses keys, and deployment
is limited to an isolated LAN. Release remains blocked until the exact brick
image and cross-toolchain artifacts are archived with SHA-256 and an SBOM plus
known-vulnerability review is attached. This is an explicit §3.2.7/§8.5 gate;
the host tests do not waive it.
