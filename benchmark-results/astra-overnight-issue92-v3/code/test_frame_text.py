import unittest
from frame_text import rerank_frames,projection

class FrameTextTests(unittest.TestCase):
    def test_only_covered_top30_slots_change(self):
        base=projection([{'frame_id':f'v{i%12}#{i}','video_id':f'v{i%12}','rank':i+1,'score':100-i} for i in range(100)])
        covered=[base['frames'][i]['frame_id'] for i in (0,4,8,15,29)]
        result=rerank_frames(base,dict(zip(covered,range(5))))
        for i in range(100):
            if i not in (0,4,8,15,29):self.assertEqual(result['frames'][i]['frame_id'],base['frames'][i]['frame_id'])
        self.assertEqual({f['frame_id'] for f in base['frames']},{f['frame_id'] for f in result['frames']})

    def test_empty_and_tied_scores_preserve_order(self):
        base=projection([{'frame_id':f'v#{i}','video_id':'v','rank':i+1,'score':10-i} for i in range(5)])
        self.assertEqual(rerank_frames(base,{}),base)
        self.assertEqual(rerank_frames(base,{f['frame_id']:0 for f in base['frames']}),base)

if __name__=='__main__':unittest.main()
