# PHANTOM mechanics gate

The BOM mirrors [the mechanical specification §18](mechanical-specification.md#sec-6-18)
and the LDraw file fixes the required module hierarchy.
It is deliberately marked **DESIGN PLACEHOLDER / UNQUALIFIED**: the repository
does not contain measurements proving coaxiality, counterweight, cable range,
hard stops, swept volume, QR mount transforms, passive power-loss behaviour or
the independent POWER_CUT. Those values must not be invented in software.

Before powered movement, complete the Studio/LDraw pin-accurate model,
record its SHA-256 in the commissioning bundle, and inspect the physical assembly
using [the mechanical inspection checklist](mechanical-safety-inspection.md).
No manual report form is required. Until then the generated
configuration keeps `READY` blocked and EV3 duty at zero.
