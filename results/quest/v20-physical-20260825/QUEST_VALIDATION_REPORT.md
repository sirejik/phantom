# Quest Validation Report

Analyzed run IDs: 0b14d23ee6d0476fa2aad84b4bbed130, 28c449cfbac74ee2956c8874e8723335, 316917c2d91b4ecab4a0aa3969b81c17, 45948f58b7814f6483e405904fcf3910, 4c6698a3073f442387f933e4bf5d33ac, 58a4d6346bb94d70910562128b69fe7b, 5cdc512d8ffb484a8d52c9ddf8606167, 65d88f79f74f4ee78e694ae1013933dd, b2fabd693007445bbcd5a2439e2973c4, b62249a729054e0bbfbc1187526e9abc, bc83bb91812a46398e87a80bb60abe7c, c1954f1d8d1045bb8f52f1f39a697d16, cbef88c520f24198a9b3c433180614b6, cd1ae3f1c71f4ce083b2d717cc6c8628, e4bb50b88e904764b7b997f33b85b318, e52522df0b984ec480570157c124d92d, f13620f18756469c8eec84166df691ca, f465316fcdfc48cfa57cda36df4d669c, f9583aed09e64108ac531a03fe9fe819, fa012115dab24434873aea76f668c783
Input events: 22101

No `CONFIRMED` verdict is emitted without Android device metadata and relevant samples.

| Test | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| Q0_Environment | Pinned Unity/OpenXR environment is available on device | **CONFIRMED** | guided MR/visual-stability sequence completed; 4/4 user confirmations, n=268 |
| Q1_Multimodal | Right hand and left Touch Plus remain valid simultaneously | **CONFIRMED** | steady simultaneous-valid=0.989, n=563; recovery confirmations=10/10; expected loss observed=True |
| Q2_Grasp | XR common grasp is stable and monotonic across requested closure | **REJECTED** | monotonic repeats=4/5; open range=0.051-1.000; fist range=1.000-1.000 |
| Q3_WristVsPalm | Wrist is more position-stable than Palm during wrist rotation/grasp | **CONFIRMED** | wrist RMS/p95=0.06829/0.21330 m; palm=0.06849/0.21528 m; n=213 |
| Q4_RoomStability | The recognized room frame remains stable across pause/recenter | **CONFIRMED** | room-ready=1.000, max recovery=0.00s, room IDs=1, stationary floor p95=0.00009m, n=388 |
| Q5_FixedQr | A fixed QR has sufficient pose stability | **REJECTED** | payload=PHANTOM:phantom01:SHOULDER_L, valid=500/521 (0.960), first detection=1.11s, position p95=0.01776m, orientation p95=15.518deg |
| Q6_QrMatrix | Marker detection is sufficient across size/distance/angle matrix | **INCONCLUSIVE** | 1421 device samples; required scenario-specific completion markers/ground truth absent |
| Q7_MarkerRig | Startup marker rig measures L1/L2 accurately | **INCONCLUSIVE** | 257 device samples; required scenario-specific completion markers/ground truth absent |
| Q8_UserShoulderFit | Robust multi-arc fit produces repeatable shoulder/arm calibration | **INCONCLUSIVE** | 611 device samples; required scenario-specific completion markers/ground truth absent |
| Q9_Drift | Absolute mapping has no cycle-dependent live drift | **INCONCLUSIVE** | 328 device samples; required scenario-specific completion markers/ground truth absent |
| Q10_TrackingPauseLoss | Tracking loss/pause enters SAFE_HOLD and requires re-engage | **INCONCLUSIVE** | 969 device samples; required scenario-specific completion markers/ground truth absent |
| Q11_UdpSimulator | Quest handles simulator network fault scenarios safely | **INCONCLUSIVE** | 345 device samples; required scenario-specific completion markers/ground truth absent |
| Q12_FullStartupDryRun | Full room-to-simulator startup works end-to-end | **INCONCLUSIVE** | 518 device samples; required scenario-specific completion markers/ground truth absent |
| Q13_QrAbsoluteJointReference | Rigid QR references provide repeatable absolute joint angles | **NOT_MEASURED** | 0 samples |
| Q14_QrEncoderCrossCheck | QR references and encoder zeroing agree across repeated cycles | **NOT_MEASURED** | 0 samples |
