import unittest
from frame_text import rerank_frames,projection

class ProtectedTests(unittest.TestCase):
    def test_top1_empty_slots_and_membership_preserved(self):
        base=projection([{'frame_id':f'v{i%12}#{i}','video_id':f'v{i%12}','rank':i+1,'score':100-i} for i in range(100)])
        scores={f['frame_id']:float(i) for i,f in enumerate(base['frames']) if i%3}
        result=rerank_frames(base,scores)
        self.assertEqual(result['frames'][0],base['frames'][0])
        for i in range(100):
            if i%3==0:self.assertEqual(result['frames'][i]['frame_id'],base['frames'][i]['frame_id'])
        self.assertEqual({f['frame_id'] for f in result['frames']},{f['frame_id'] for f in base['frames']})
        self.assertNotEqual(result['frames'],base['frames'])

    def test_empty_scores_preserve_exact_control(self):
        base=projection([{'frame_id':'v#1','video_id':'v','rank':1,'score':1}])
        self.assertEqual(rerank_frames(base,{}),base)

if __name__=='__main__':unittest.main()
