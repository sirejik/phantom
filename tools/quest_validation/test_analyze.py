import importlib.util
import pathlib
import tempfile
import unittest

PATH=pathlib.Path(__file__).with_name("analyze.py")
SPEC=importlib.util.spec_from_file_location("quest_analyze",str(PATH));analyze=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(analyze)

class AnalyzeTests(unittest.TestCase):
    def test_no_data_never_confirms(self):
        for test in analyze.TESTS:self.assertEqual(analyze.evaluate([],test)[0],"NOT_MEASURED")
    def test_reports_are_created(self):
        with tempfile.TemporaryDirectory() as value:
            out=pathlib.Path(value);analyze.write_reports([],out)
            self.assertTrue((out/"QUEST_VALIDATION_REPORT.md").exists());self.assertIn("NOT_MEASURED",(out/"QUEST_VALIDATION_REPORT.md").read_text(encoding="utf-8"))
    def test_old_q4_samples_remain_inconclusive(self):
        events=[{"run_id":"q4","test_id":"Q4_RoomStability","event_name":"run_start","payload":{"platform":"Android","device_model":"Oculus Quest 3"}},
                {"run_id":"q4","test_id":"Q4_RoomStability","event_name":"tracking_sample","state":"capture","payload":{"Head":{"Valid":True}}}]
        status,detail=analyze.evaluate(events,"Q4_RoomStability")
        self.assertEqual(status,"INCONCLUSIVE");self.assertIn("instrumentation is absent",detail)
    def test_complete_instrumented_q4_ignores_legacy_samples(self):
        events=[{"run_id":"legacy","test_id":"Q4_RoomStability","event_name":"tracking_sample","state":"capture","payload":{"Head":{"Valid":True}}},
                {"run_id":"guided","test_id":"Q4_RoomStability","event_name":"run_start","payload":{"platform":"Android","device_model":"Oculus Quest 3"}}]
        for index in range(1,7):
            state=f"step_{index}_of_6"
            events.append({"run_id":"guided","test_id":"Q4_RoomStability","event_name":"phase_confirmed_by_user","state":state,"payload":{}})
            for sample in range(10):
                events.append({"run_id":"guided","test_id":"Q4_RoomStability","event_name":"tracking_sample","state":state,"monotonic_time_us":index*1_000_000+sample*100_000,"payload":{"room_ready":True,"room_status":"localized current room 628a2751-81c0-5004-2365-2b6881b85ff2","floor_origin":{"X":0,"Y":0,"Z":0}}})
        events.extend([{"run_id":"guided","test_id":"Q4_RoomStability","event_name":"sequence_complete","payload":{}},
                       {"run_id":"guided","test_id":"Q4_RoomStability","event_name":"run_stop","payload":{}}])
        status,detail=analyze.evaluate(events,"Q4_RoomStability")
        self.assertEqual(status,"CONFIRMED");self.assertIn("n=60",detail)
    def test_complete_q4_accepts_localized_room_status(self):
        events=[{"run_id":"q4-ru","test_id":"Q4_RoomStability","event_name":"run_start","payload":{"platform":"Android","device_model":"Oculus Quest 3"}}]
        status_text="ГОТОВО: комната 628a2751-81c0-5004-2365-2b6881b85ff2 распознана"
        for index in range(1,7):
            state=f"step_{index}_of_6"
            events.append({"run_id":"q4-ru","test_id":"Q4_RoomStability","event_name":"phase_confirmed_by_user","state":state,"payload":{}})
            for sample in range(10):
                events.append({"run_id":"q4-ru","test_id":"Q4_RoomStability","event_name":"tracking_sample","state":state,"monotonic_time_us":index*1_000_000+sample*100_000,"payload":{"room_ready":True,"room_status":status_text,"floor_origin":{"X":0,"Y":0,"Z":0}}})
        events.extend([{"run_id":"q4-ru","test_id":"Q4_RoomStability","event_name":"sequence_complete","payload":{}},
                       {"run_id":"q4-ru","test_id":"Q4_RoomStability","event_name":"run_stop","payload":{}}])
        status,detail=analyze.evaluate(events,"Q4_RoomStability")
        self.assertEqual(status,"CONFIRMED");self.assertIn("room IDs=1",detail)
    def test_q1_excludes_intentional_loss_steps_and_requires_recovery(self):
        run="q1";events=[{"run_id":run,"test_id":"Q1_Multimodal","event_name":"run_start","payload":{"platform":"Android","device_model":"Oculus Quest 3"}}]
        for index in range(1,11):
            state=f"step_{index}_of_10"
            both=index!=9
            events.append({"run_id":run,"test_id":"Q1_Multimodal","event_name":"tracking_sample","state":state,"payload":{"RightHand":{"Valid":both},"LeftController":{"Valid":True}}})
            events.append({"run_id":run,"test_id":"Q1_Multimodal","event_name":"phase_confirmed_by_user","state":state,"payload":{"BothValid":True}})
        events.extend([{"run_id":run,"test_id":"Q1_Multimodal","event_name":"sequence_complete","payload":{}},
                       {"run_id":run,"test_id":"Q1_Multimodal","event_name":"run_stop","payload":{}}])
        status,detail=analyze.evaluate(events,"Q1_Multimodal")
        self.assertEqual(status,"CONFIRMED");self.assertIn("steady simultaneous-valid=1.000",detail)
    def test_q2_uses_confirmation_values_and_rejects_nonmonotonic_repeat(self):
        run="q2";events=[{"run_id":run,"test_id":"Q2_Grasp","event_name":"run_start","payload":{"platform":"Android","device_model":"Oculus Quest 3"}},
                          {"run_id":run,"test_id":"Q2_Grasp","event_name":"tracking_sample","payload":{}}]
        tokens=("OPEN","25","50","75","FIST","OPEN_RETURN")
        normal=(0.0,.25,.5,.75,1.0,0.0);bad=(1.0,.25,.5,.75,1.0,0.0)
        for repeat in range(1,6):
            values=bad if repeat==2 else normal
            for token,value in zip(tokens,values):
                events.append({"run_id":run,"test_id":"Q2_Grasp","event_name":"phase_confirmed_by_user","state":f"repeat_{repeat}_{token}","payload":{"RightHand":{"Grasp":{"Ready":True,"Valid":True,"Value01":value}}}})
        events.extend([{"run_id":run,"test_id":"Q2_Grasp","event_name":"sequence_complete","payload":{}},
                       {"run_id":run,"test_id":"Q2_Grasp","event_name":"run_stop","payload":{}}])
        status,detail=analyze.evaluate(events,"Q2_Grasp")
        self.assertEqual(status,"REJECTED");self.assertIn("monotonic repeats=4/5",detail)
    def test_complete_q5_is_evaluated_from_qr_pose(self):
        events=[{"run_id":"q5","test_id":"Q5_FixedQr","event_name":"run_start","payload":{"platform":"Android","device_model":"Oculus Quest 3"}},
                {"run_id":"q5","test_id":"Q5_FixedQr","event_name":"phase_start","state":"step_2_of_3","monotonic_time_us":1_000_000,"payload":{}}]
        for index in range(500):
            events.append({"run_id":"q5","test_id":"Q5_FixedQr","event_name":"tracking_sample","state":"step_2_of_3","monotonic_time_us":1_100_000+index*100_000,"payload":{"qr":{"Payload":"QR_TEST","PositionRoom":{"X":1.0+(index%3)*.0001,"Y":0,"Z":1.2},"RotationX":0,"RotationY":0,"RotationZ":0,"RotationW":1,"Valid":True}}})
        events.extend([{"run_id":"q5","test_id":"Q5_FixedQr","event_name":"sequence_complete","payload":{}},
                       {"run_id":"q5","test_id":"Q5_FixedQr","event_name":"run_stop","payload":{}}])
        status,detail=analyze.evaluate(events,"Q5_FixedQr")
        self.assertEqual(status,"CONFIRMED");self.assertIn("valid=500/500",detail)
    def test_complete_q5_four_step_capture_uses_acquisition_time(self):
        events=[{"run_id":"q5-v15","test_id":"Q5_FixedQr","event_name":"run_start","state":"step_1_of_4","monotonic_time_us":1_000_000,"payload":{"platform":"Android","device_model":"Oculus Quest 3"}},
                {"run_id":"q5-v15","test_id":"Q5_FixedQr","event_name":"qr_acquired","state":"step_2_of_4","monotonic_time_us":3_500_000,"payload":{}}]
        for index in range(500):
            events.append({"run_id":"q5-v15","test_id":"Q5_FixedQr","event_name":"tracking_sample","state":"step_3_of_4","monotonic_time_us":8_000_000+index*100_000,"payload":{"qr":{"Payload":"QR_TEST","PositionRoom":{"X":1.0+(index%3)*.0001,"Y":0,"Z":1.2},"RotationX":0,"RotationY":0,"RotationZ":0,"RotationW":1,"Valid":True}}})
        events.extend([{"run_id":"q5-v15","test_id":"Q5_FixedQr","event_name":"sequence_complete","payload":{}},
                       {"run_id":"q5-v15","test_id":"Q5_FixedQr","event_name":"run_stop","payload":{}}])
        status,detail=analyze.evaluate(events,"Q5_FixedQr")
        self.assertEqual(status,"CONFIRMED");self.assertIn("first detection=2.50s",detail)

if __name__=="__main__":unittest.main()
