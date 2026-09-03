# PHANTOM mechanics gate

The BOM mirrors §6.18 and the LDraw file fixes the required module hierarchy.
It is deliberately marked **DESIGN PLACEHOLDER / UNQUALIFIED**: the repository
does not contain measurements proving coaxiality, counterweight, cable range,
hard stops, swept volume, QR mount transforms, passive power-loss behaviour or
the independent POWER_CUT. Those values must not be invented in software.

Before any powered HIL movement, complete the Studio/LDraw pin-accurate model,
record its SHA-256 in the commissioning bundle, and sign
`safety-inspection.md` on the physical assembly. Until then the generated
configuration keeps `READY` blocked and EV3 duty at zero.
