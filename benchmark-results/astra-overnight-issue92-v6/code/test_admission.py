import unittest
from candidate_admission import admit
from frame_text import rerank_frames,projection

class AdmissionTests(unittest.TestCase):
    def test_budget_duplicates_protected_prefix(self):
        base=[{'frame_id':f'v#{i}','video_id':'v','rank':i+1} for i in range(100)]
        sem=[{'frame_id':f'v#{i}','video_id':'v','rank':i+1} for i in range(70,120)]
        result=admit(base,sem)
        self.assertEqual(len(result),100)
        self.assertEqual(result[:80],base[:80])
        self.assertEqual(len({f['frame_id'] for f in result}),100)

    def test_empty_provider_recovers_control(self):
        base=[{'frame_id':f'v#{i}','video_id':'v','rank':i+1} for i in range(100)]
        self.assertEqual(admit(base,[]),base)
        self.assertEqual(rerank_frames(projection(base),{}),projection(base))

if __name__=='__main__':unittest.main()
