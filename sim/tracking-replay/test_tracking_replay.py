import importlib.util,json,pathlib,tempfile,unittest
P=pathlib.Path(__file__).with_name("tracking_replay.py");S=importlib.util.spec_from_file_location("tracking_replay",str(P));m=importlib.util.module_from_spec(S);S.loader.exec_module(m)
class ReplayTests(unittest.TestCase):
 def record(self):
  pose=lambda p:{"position_local_floor":p,"valid":True,"sample_or_query_us":1,"receive_us":2,"uncertainty_ms":1,"quality":"VALID"}
  return {"frame_id":1,"receive_us":2,"head":pose([0,1,0]),"shoulder":pose([0,1.4,0]),"wrist":pose([.4,1.4,0]),"grasp":{"ready":True,"valid":True,"value":.2},"left_grip":{"valid":True,"value":0}}
 def test_pure_path_independent_vector(self):
  r=self.record();self.assertEqual(m.pure_vector(r),[.4,0,0]);r["head"]["position_local_floor"]=[9,9,9];self.assertEqual(m.pure_vector(r),[.4,0,0])
 def test_replay(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/"r.jsonl";p.write_text(json.dumps(self.record())+"\n");self.assertEqual(m.replay(p)["aligned_candidates"],1)
if __name__=="__main__":unittest.main()
