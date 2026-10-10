# Pre-motion mechanical safety inspection

Preparation for [manual tests](test-plan.md#sec-9-1-6), not a report form.
Inspect the actual assembly before powered movement; if any condition fails,
keep motion disabled and correct the problem.

- [ ] Shoulder and Elbow axes are coaxial.
- [ ] Full passive travel is free of binding.
- [ ] Gears mesh correctly; frames, axles and QR mounts are locked.
- [ ] Motor cables retain slack through the intended range.
- [ ] Physical Base and pitch stops are installed and measured.
- [ ] Base is fixed and the swept volume is clear.
- [ ] LOCAL_STOP on in4 is proven with automatic motion still disabled.
- [ ] GRIPPER_HOME on in3 is detected at the physical closed endpoint.
- [ ] Independent POWER_CUT removes motor energy.
- [ ] Counterweight/passive power-loss behaviour is acceptable.

Every applicable item must be physically checked; this checklist does not
assert that an inspection has already been performed.
